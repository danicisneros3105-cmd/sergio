"""Long-term memory: a vector store of tasks, verdicts and feedback.

chromadb keeps it on disk (``~/.openjarvis/memoria``). Texts are embedded
with Gemini (``gemini-embedding-001``) when a key is set, and always with a
local hashing embedder too, so recall works offline and costs nothing.
Without chromadb a small JSON-lines store with the same API is used.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Callable

FOLDER = Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis") / "memoria"
RELEVANT = {"semantic": 0.62, "local": 0.12}  # the score that means "about the same thing" in each space


def _folder() -> Path:
    """Where memories live (read at use time, so OPENJARVIS_HOME set later counts)."""
    home = os.environ.get("OPENJARVIS_HOME")
    return Path(home) / "memoria" if home else FOLDER
DIMS = 1024  # wide enough that unrelated words rarely collide
KINDS = ("task", "feedback", "lesson", "blender", "video", "preference")
STOP = set("""a al algo con como de del el ella en es esa ese esta este haz hazme la las le lo los me mi mas muy
no o para pero por que quiero se sin su sus te tu un una uno unos unas y ya the of and to in on for with""".split())


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def hash_embed(text: str, dims: int = DIMS) -> list[float]:
    """A local embedding: hashed words and word pairs (+ 4-letter stems),
    signed, L2-normalised. No network, stable across runs."""
    words = [w for w in re.findall(r"[a-z0-9]+", _plain(text)) if w not in STOP]
    feats = words + [w[:4] for w in words if len(w) > 5] + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    vec = [0.0] * dims
    for f in feats:
        h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
        vec[h % dims] += 1.0 if (h >> 32) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _unit(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def gemini_embedder() -> Callable[..., list[list[float]]] | None:
    """Gemini embeddings (semantic, multilingual), or None without a key.

    Stored texts are embedded as RETRIEVAL_DOCUMENT and searches as
    RETRIEVAL_QUERY (Gemini ranks better that way). 768-d Gemini vectors
    are not unit length, so they are normalised here."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None

    def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        from google import genai

        client = genai.Client(api_key=key)
        resp = client.models.embed_content(model="gemini-embedding-001", contents=texts,
                                           config={"output_dimensionality": 768, "task_type": task})
        return [_unit(list(e.values)) for e in resp.embeddings]

    embed.takes_task = True  # type: ignore[attr-defined]
    return embed


SEM_COOLDOWN = 300.0  # seconds to leave the semantic model alone after it fails (quota, offline)
BACKFILL = 64         # memories copied into the semantic store per recall


class LongTermMemory:
    """remember / recall / lessons_for / feedback over a persistent store.

    Every memory always lands in the local store. The semantic (Gemini)
    store can miss some — written while offline, out of quota, or before a
    key existed — so recall backfills it and, while it is incomplete, also
    searches the local store, so nothing is ever lost from recall."""

    def __init__(self, folder: Path | None = None, semantic: Callable[..., list[list[float]]] | None = None,
                 use_gemini: bool = True) -> None:
        self.folder = folder or _folder()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.semantic = semantic if semantic is not None else (gemini_embedder() if use_gemini else None)
        self._sem = None
        self._sem_retry_at = 0.0
        try:
            import chromadb

            self._client = chromadb.PersistentClient(path=str(self.folder / "chroma"))
            self._local = self._client.get_or_create_collection("sergio_local", metadata={"hnsw:space": "cosine"})
            self.engine = "chromadb"
            if self.semantic is not None:
                self._open_semantic()
        except ImportError:
            self._client = None
            self.engine = "json"
            self._file = self.folder / "memoria.jsonl"

    # -- the semantic store ----------------------------------------------------
    def _embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        if getattr(self.semantic, "takes_task", False):
            return self.semantic(texts, task="RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT")
        return self.semantic(texts)

    def _semantic_ready(self) -> bool:
        return self.semantic is not None and self._client is not None and time.time() >= self._sem_retry_at

    def _semantic_failed(self) -> None:
        self._sem_retry_at = time.time() + SEM_COOLDOWN

    def _open_semantic(self, dims: int | None = None) -> None:
        """Open the semantic collection for vectors of *dims* (or the one used
        last time). Each size has its own collection, so a model with other
        dimensions never collides with old vectors."""
        marker = self.folder / "semantic.json"
        if dims is None:
            try:
                dims = int(json.loads(marker.read_text(encoding="utf-8"))["dims"])
            except (OSError, ValueError, KeyError, TypeError):
                return
        if self._sem is not None and self._sem.metadata.get("dims") == dims:
            return
        self._sem = self._client.get_or_create_collection(
            f"sergio_semantic_{dims}", metadata={"hnsw:space": "cosine", "dims": dims})
        marker.write_text(json.dumps({"dims": dims}), encoding="utf-8")

    def _sem_add(self, ids: list[str], docs: list[str], metas: list[dict]) -> bool:
        """Embed and store in the semantic collection that fits the vectors."""
        try:
            vecs = self._embed(docs)
            self._open_semantic(len(vecs[0]))
            self._sem.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)
            return True
        except Exception:  # noqa: BLE001 — the local copy is enough for now
            self._semantic_failed()
            return False

    def _backfill(self, limit: int = BACKFILL) -> None:
        """Copy local memories the semantic store is missing (bounded)."""
        if not self._semantic_ready() or self._local.count() == 0:
            return
        have = set(self._sem.get(include=[])["ids"]) if self._sem is not None else set()
        if self._sem is not None and len(have) >= self._local.count():
            return
        local = self._local.get(include=["documents", "metadatas"])
        missing = [(i, d, m) for i, d, m in zip(local["ids"], local["documents"], local["metadatas"]) if i not in have]
        missing = missing[-limit:]  # the newest first matter most
        if missing:
            ids, docs, metas = (list(x) for x in zip(*missing))
            self._sem_add(ids, docs, metas)

    def _sem_complete(self) -> bool:
        return self._sem is not None and self._sem.count() >= self._local.count()

    # -- writing --------------------------------------------------------------
    def remember(self, kind: str, text: str, **meta: Any) -> str:
        """Keep *text* (a task, a verdict, feedback...) for later recall."""
        text = " ".join(str(text).split())[:4000]
        if not text:
            return ""
        meta = {k: (v if isinstance(v, (str, int, float, bool)) else json.dumps(v, ensure_ascii=False))
                for k, v in meta.items() if v is not None}
        meta.update({"kind": kind if kind in KINDS else "task", "time": time.time()})
        rid = uuid.uuid4().hex
        if self._client is None:
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": rid, "text": text, "meta": meta, "vec": hash_embed(text)}) + "\n")
            return rid
        self._local.add(ids=[rid], documents=[text], metadatas=[meta], embeddings=[hash_embed(text)])
        if self._semantic_ready():
            self._sem_add([rid], [text], [meta])
        return rid

    # -- reading ---------------------------------------------------------------
    def recall(self, query: str, k: int = 5, kinds: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        """The *k* memories closest in meaning to *query* (optionally of some kinds)."""
        if not query.strip():
            return []
        where = {"kind": {"$in": list(kinds)}} if kinds else None
        if self._client is None:
            return self._recall_json(query, k, kinds)
        self._backfill()
        found: dict[str, dict[str, Any]] = {}
        stores = []
        if self._sem is not None and self._sem.count() and self._semantic_ready():
            stores.append((self._sem, "semantic"))
        if not stores or not self._sem_complete():
            stores.append((self._local, "local"))  # never let a gap in the semantic store hide a memory
        for coll, space in stores:
            if coll.count() == 0:
                continue
            try:
                vec = self._embed([query], query=True) if space == "semantic" else [hash_embed(query)]
                if space == "semantic" and len(vec[0]) != coll.metadata.get("dims"):
                    raise ValueError("the semantic model changed size; backfill will rebuild")
                res = coll.query(query_embeddings=vec, n_results=min(k, coll.count()), where=where)
            except Exception:  # noqa: BLE001 — next store
                if space == "semantic":
                    self._semantic_failed()
                    if (self._local, "local") not in stores:
                        stores.append((self._local, "local"))
                continue
            for rid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                                            res["distances"][0]):
                if rid not in found:  # the semantic hit wins over the local copy of the same memory
                    found[rid] = {"text": doc, "kind": meta.get("kind"), "meta": meta,
                                  "score": round(1 - float(dist), 3), "space": space}
        # each space has its own scale, so rank by how far above its own relevance bar a hit is
        ranked = sorted(found.values(), key=lambda m: -(m["score"] - RELEVANT[m["space"]]))
        return ranked[:k]

    def _recall_json(self, query: str, k: int, kinds: tuple[str, ...] | None) -> list[dict[str, Any]]:
        if not self._file.exists():
            return []
        q = hash_embed(query)
        rows = []
        for line in self._file.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if kinds and row["meta"].get("kind") not in kinds:
                continue
            score = sum(a * b for a, b in zip(q, row["vec"]))
            rows.append({"text": row["text"], "kind": row["meta"].get("kind"), "meta": row["meta"], "score": round(score, 3),
                         "space": "local"})
        return sorted(rows, key=lambda r: -r["score"])[:k]

    def lessons_for(self, query: str, kinds: tuple[str, ...] = ("lesson", "feedback", "blender", "video"),
                    k: int = 4, min_score: float | None = None) -> str:
        """The closest lessons as a prompt block ("" when nothing relevant).
        Relevance: Gemini embeddings put unrelated texts around 0.5, the
        local ones around 0, so each has its own bar."""
        found = [m for m in self.recall(query, k, kinds)
                 if m["score"] >= (min_score if min_score is not None else RELEVANT[m["space"]])]
        if not found:
            return ""
        lines = [f"- ({m['kind']}) {m['text'][:400]}" for m in found]
        return ("LESSONS FROM YOUR LONG-TERM MEMORY (past results and the user's feedback on similar work — "
                "apply them, do not repeat those mistakes):\n" + "\n".join(lines) + "\n")

    def feedback(self, text: str, rating: int = 0, about: str = "") -> str:
        """The user's opinion of a result (rating -1 bad, 0 note, +1 good),
        kept with what it was about, so it shapes the next similar job."""
        mood = {1: "LE GUSTÓ", -1: "NO LE GUSTÓ"}.get(rating, "NOTA")
        line = f"{mood} al usuario: «{text}»" + (f" — sobre: {about}" if about else "")
        return self.remember("feedback", line, rating=rating, about=about[:300])

    def stats(self) -> dict[str, Any]:
        if self._client is None:
            total = len(self._file.read_text(encoding="utf-8").splitlines()) if self._file.exists() else 0
        else:
            total = self._local.count()
        semantic = self._sem.count() if self._client is not None and self._sem is not None else 0
        return {"engine": self.engine, "memories": total, "semantic": bool(self.semantic),
                "semantic_memories": semantic}


_shared: list[LongTermMemory] = []


def shared() -> LongTermMemory:
    """The server's one memory (created on first use)."""
    if not _shared:
        _shared.append(LongTermMemory())
    return _shared[0]


def lessons(query: str, kinds: tuple[str, ...] = ("lesson", "feedback", "blender", "video")) -> str:
    """Lessons for a prompt; never fails (memory is a bonus)."""
    try:
        return shared().lessons_for(query, kinds)
    except Exception:  # noqa: BLE001
        return ""


__all__ = ["LongTermMemory", "hash_embed", "lessons", "shared"]

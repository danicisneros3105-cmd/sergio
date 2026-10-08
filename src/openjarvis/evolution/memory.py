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


def gemini_embedder() -> Callable[[list[str]], list[list[float]]] | None:
    """Gemini embeddings (semantic, multilingual), or None without a key."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None

    def embed(texts: list[str]) -> list[list[float]]:
        from google import genai

        client = genai.Client(api_key=key)
        resp = client.models.embed_content(model="gemini-embedding-001", contents=texts,
                                           config={"output_dimensionality": 768})
        return [list(e.values) for e in resp.embeddings]

    return embed


class LongTermMemory:
    """remember / recall / lessons_for / feedback over a persistent store."""

    def __init__(self, folder: Path | None = None, semantic: Callable[[list[str]], list[list[float]]] | None = None,
                 use_gemini: bool = True) -> None:
        self.folder = folder or FOLDER
        self.folder.mkdir(parents=True, exist_ok=True)
        self.semantic = semantic if semantic is not None else (gemini_embedder() if use_gemini else None)
        try:
            import chromadb

            self._client = chromadb.PersistentClient(path=str(self.folder / "chroma"))
            self._local = self._client.get_or_create_collection("sergio_local", metadata={"hnsw:space": "cosine"})
            self._sem = (self._client.get_or_create_collection("sergio_gemini", metadata={"hnsw:space": "cosine"})
                         if self.semantic else None)
            self.engine = "chromadb"
        except ImportError:
            self._client = None
            self.engine = "json"
            self._file = self.folder / "memoria.jsonl"

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
        if self._sem is not None:
            try:
                self._sem.add(ids=[rid], documents=[text], metadatas=[meta], embeddings=self.semantic([text]))
            except Exception:  # noqa: BLE001 — the local copy is enough
                pass
        return rid

    # -- reading ---------------------------------------------------------------
    def recall(self, query: str, k: int = 5, kinds: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        """The *k* memories closest in meaning to *query* (optionally of some kinds)."""
        if not query.strip():
            return []
        where = {"kind": {"$in": list(kinds)}} if kinds else None
        if self._client is None:
            return self._recall_json(query, k, kinds)
        for coll, embed in ((self._sem, self.semantic), (self._local, None)):
            if coll is None or coll.count() == 0:
                continue
            try:
                vec = embed([query]) if embed else [hash_embed(query)]
                res = coll.query(query_embeddings=vec, n_results=min(k, coll.count()), where=where)
            except Exception:  # noqa: BLE001 — next store
                continue
            out = []
            space = "semantic" if embed else "local"
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
                out.append({"text": doc, "kind": meta.get("kind"), "meta": meta, "score": round(1 - float(dist), 3),
                            "space": space})
            if out:
                return out
        return []

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
                 if m["score"] >= (min_score if min_score is not None else (0.62 if m["space"] == "semantic" else 0.12))]
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
        return {"engine": self.engine, "memories": total, "semantic": bool(self.semantic)}


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

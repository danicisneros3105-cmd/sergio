"""The receptors: how a request becomes something the fly brain can smell.

A fly's olfactory receptors respond to the chemistry of an odour, not to its
name, so similar odours excite overlapping glomeruli and what was learned for
one generalises to the other. Here the "chemistry" of a request is its
meaning: a sentence embedding. Each projection neuron has a fixed random
tuning over that meaning space (like a receptor type), and the antennal
lobe's adaptation removes what every request has in common (language, tone),
so only what is distinctive reaches the Kenyon cells.

Where the meaning comes from, the first that works:

1. **on this device**: multilingual-e5-small (MIT, 118 MB, ONNX), downloaded
   once to ``~/.openjarvis/modelos/e5-small`` (``sergio cerebro descargar``);
2. **Gemini embeddings** with the owner's key, kept in a local cache so the
   same sentence is never sent twice;
3. nothing: the words alone still work (lexical channel).

``SERGIO_RECEPTORES=0`` turns the meaning channel off.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Optional

import numpy as np

E5_REPO = "Xenova/multilingual-e5-small"
E5_FILES = ("onnx/model_quantized.onnx", "tokenizer.json")
GEMINI_MODEL = "gemini-embedding-001"
GEMINI_DIMS = 256
ALPHA = 4.0  # weight of meaning against words at the projection neurons
FRACTION = 0.3  # share of projection neurons a meaning excites
ADAPT = 0.02  # how fast the background (what all requests share) is learned
COOL_S = (
    60.0  # after a failed call (no internet, free-tier limit): words alone a minute
)

_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get("SERGIO_RECEPTORES", "1").strip() not in (
        "0",
        "no",
        "off",
        "false",
    )


def models_dir() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "modelos" / "e5-small"


class _Local:
    """multilingual-e5-small with onnxruntime (no internet, ~20 ms)."""

    def __init__(self, folder: Path) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.tok = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tok.enable_truncation(max_length=256)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.sess = ort.InferenceSession(
            str(folder / "model_quantized.onnx"),
            opts,
            providers=["CPUExecutionProvider"],
        )
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.space = "e5-small"

    def __call__(self, texts: List[str]) -> np.ndarray:
        enc = [self.tok.encode("query: " + t) for t in texts]
        n = max(len(e.ids) for e in enc)
        ids = np.zeros((len(enc), n), dtype=np.int64)
        mask = np.zeros((len(enc), n), dtype=np.int64)
        for i, e in enumerate(enc):
            ids[i, : len(e.ids)] = e.ids
            mask[i, : len(e.ids)] = 1
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self.sess.run(None, feed)[0]
        pooled = (hidden * mask[..., None]).sum(1) / mask.sum(1, keepdims=True)
        return (pooled / np.linalg.norm(pooled, axis=1, keepdims=True)).astype(
            np.float32
        )


class _Gemini:
    """Gemini embeddings with a cache on this computer."""

    def __init__(self, cache: Path) -> None:
        from openjarvis.creator.llm import gemini_key

        gemini_key()  # raises when there is no key
        self.cache = cache
        self.space = f"gemini-{GEMINI_DIMS}"
        cache.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(cache) as db:
            db.execute("CREATE TABLE IF NOT EXISTS emb (h TEXT PRIMARY KEY, v BLOB)")

    def __call__(self, texts: List[str]) -> np.ndarray:
        keys = [
            hashlib.sha1(t.encode(), usedforsecurity=False).hexdigest() for t in texts
        ]
        out: List[Optional[np.ndarray]] = [None] * len(texts)
        with sqlite3.connect(self.cache) as db:
            for i, k in enumerate(keys):
                row = db.execute("SELECT v FROM emb WHERE h = ?", (k,)).fetchone()
                if row:
                    out[i] = np.frombuffer(row[0], dtype=np.float32)
        missing = [i for i, v in enumerate(out) if v is None]
        if missing:
            from google.genai import types

            from openjarvis.creator.llm import gemini_key
            from openjarvis.engine.google_client import SwitchingClient

            resp = SwitchingClient(gemini_key()).models.embed_content(
                model=GEMINI_MODEL,
                contents=[texts[i][:2000] for i in missing],
                config=types.EmbedContentConfig(
                    output_dimensionality=GEMINI_DIMS, task_type="SEMANTIC_SIMILARITY"
                ),
            )
            with sqlite3.connect(self.cache) as db:
                for i, e in zip(missing, resp.embeddings):
                    v = np.array(e.values, dtype=np.float32)
                    v /= np.linalg.norm(v) or 1.0
                    out[i] = v
                    db.execute(
                        "INSERT OR REPLACE INTO emb VALUES (?, ?)",
                        (keys[i], v.tobytes()),
                    )
        return np.stack(out)  # type: ignore[arg-type]


class Receptors:
    """Meaning -> projection-neuron activity, with background adaptation."""

    def __init__(self, folder: Path, n_pn: int, embedder=None) -> None:
        self.folder = Path(folder)
        self.n_pn = n_pn
        self._embedder = embedder
        self._tried = embedder is not None
        self._tuning: Optional[np.ndarray] = None
        self._mu: Optional[np.ndarray] = None
        self._state = self.folder / "receptores.json"
        self._recent: dict = {}  # the same request reaches several brains
        self._cool_until = 0.0

    @property
    def embedder(self):
        if not self._tried:
            self._tried = True
            if enabled():
                for make in (
                    lambda: _Local(models_dir()),
                    lambda: _Gemini(self.folder / "receptores.db"),
                ):
                    try:
                        self._embedder = make()
                        break
                    except Exception:  # noqa: BLE001 — the next source, or words alone
                        continue
        return self._embedder

    @property
    def space(self) -> str:
        e = self.embedder
        return getattr(e, "space", "") if e is not None else ""

    def _load_state(self, dims: int) -> None:
        if self._mu is not None and len(self._mu) == dims:
            return
        self._mu = np.zeros(dims, dtype=np.float32)
        try:
            data = json.loads(self._state.read_text("utf-8"))
            if data.get("space") == self.space and len(data.get("mu", [])) == dims:
                self._mu = np.array(data["mu"], dtype=np.float32)
        except (OSError, ValueError):
            pass
        rng = np.random.default_rng(
            1729
        )  # one fixed tuning: the receptors never change
        self._tuning = rng.standard_normal((self.n_pn, dims)).astype(np.float32)

    def save(self) -> None:
        if self._mu is None:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        self._state.write_text(
            json.dumps({"space": self.space, "mu": self._mu.round(5).tolist()}), "utf-8"
        )

    def activity(self, text: str, *, adapt: bool = True) -> Optional[np.ndarray]:
        """Projection-neuron drive from the meaning of *text* (None: no meaning)."""
        emb = self.embedder
        if emb is None or not text.strip():
            return None
        key = text.strip()[:2000]
        v = self._recent.get(key)
        if v is None:
            if time.time() < self._cool_until:
                return None
            try:
                v = emb([key])[0]
            except Exception:  # noqa: BLE001 — a lost connection: words alone this time
                self._cool_until = time.time() + COOL_S
                return None
            self._recent[key] = v
            while len(self._recent) > 128:
                self._recent.pop(next(iter(self._recent)))
        with _lock:
            self._load_state(len(v))
            assert self._mu is not None and self._tuning is not None
            if adapt:
                self._mu = (
                    (1 - ADAPT) * self._mu + ADAPT * v if self._mu.any() else v.copy()
                )
            x = v - self._mu
            norm = float(np.linalg.norm(x))
            if norm < 1e-6:
                return None
            a = self._tuning @ (x / norm)
        thr = np.quantile(a, 1 - FRACTION)
        s = np.where(a >= thr, a - thr, 0.0)
        return (ALPHA * s / (s.max() + 1e-9)).astype(np.float32)

    def warm(self, texts: List[str], batch: int = 90) -> int:
        """Embed many texts at once ahead of training (a few calls instead of
        one per text; Gemini keeps them in its cache). Returns how many are
        still missing (0: all ready)."""
        emb = self.embedder
        if emb is None or not hasattr(emb, "cache"):
            return 0  # on this device every text is fast anyway
        todo = [t.strip()[:2000] for t in dict.fromkeys(texts) if t.strip()]
        done = 0
        for i in range(0, len(todo), batch):
            if time.time() < self._cool_until:
                break
            try:
                emb(todo[i : i + batch])
            except Exception:  # noqa: BLE001 — the rest waits for the next try
                self._cool_until = time.time() + COOL_S
                break
            done += len(todo[i : i + batch])
        return len(todo) - done


def download_local(dest: Optional[Path] = None, fetch=None) -> Path:
    """Fetch multilingual-e5-small for meaning on this device."""
    dest = dest or models_dir()
    dest.mkdir(parents=True, exist_ok=True)
    if fetch is None:
        import httpx

        def fetch(path: str) -> bytes:
            url = f"https://huggingface.co/{E5_REPO}/resolve/main/{path}"
            with httpx.Client(timeout=900, follow_redirects=True) as c:
                r = c.get(url)
                r.raise_for_status()
                return r.content

    for path in E5_FILES:
        target = dest / Path(path).name
        if not target.exists():
            data = fetch(path)
            tmp = target.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(target)
    return dest


__all__ = ["Receptors", "download_local", "enabled", "models_dir"]

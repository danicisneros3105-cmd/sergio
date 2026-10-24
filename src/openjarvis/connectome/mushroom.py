"""A mushroom body that really learns: Sergio's new core.

This is the circuit flies use to learn, run on the measured wiring
(:mod:`flywire`). Nothing here is a lookup table:

1. **Input** — the words of a request excite projection neurons, the way
   odorants excite glomeruli (each word, its root and its letter trigrams
   land on a few of them).
2. **Kenyon cells** — every Kenyon cell sums the projection neurons on its
   real claws; the APL neuron's inhibition lets only the strongest 5 % fire.
   That sparse code is the request's identity inside the brain.
3. **Output neurons** — Kenyon cells excite output neurons through plastic
   synapses. Each action Sergio can take (a tool, a Node, a technique) is a
   pattern over several output neurons.
4. **Dopamine** — when an action works (or fails), the dopamine neurons of
   its compartments change the synapses from the Kenyon cells that were
   active — the three-factor rule found in the fly: pre × post × dopamine.
   Only synapses that exist in the connectome can change at first.
5. **New synapses** — when an active Kenyon cell and an output neuron keep
   being rewarded together without a synapse between them, a new synapse
   grows; grown synapses that end up useless are pruned during sleep.
6. **Two memories** — a fast trace (like the gamma lobe: hours) and a slow
   one (like the alpha-beta lobe: weeks). :meth:`consolidate` is sleep: the
   day's episodes are replayed and retrained into the slow trace, so what
   mattered survives and the rest fades.

The learned weights live in ``<folder>/<name>.npz``; every number shown in
the Cerebro page comes from these arrays.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
import unicodedata
import zlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

from openjarvis.connectome.flywire import Wiring, stable_seed

SPARSITY = 0.05  # APL: about 5 % of Kenyon cells fire for one odour
CODE = 6  # output neurons per action
LR = 0.25  # dopamine-gated plasticity of the fast trace
HETERO = 0.02  # the same dopamine slightly depresses the other outputs of active cells
GROW_AFTER = 3  # co-rewarded without a synapse this many times: one grows
TAU_FAST_H = 8.0  # the fast trace halves in about 5.5 hours
TAU_SLOW_D = 90.0  # the slow trace lasts months
REPLAY_MAX = 3000

_STOP = {
    "a", "al", "de", "del", "el", "la", "las", "lo", "los", "en", "y", "o", "u", "un", "una", "unos",
    "por", "para", "con", "mi", "mis", "me", "te", "se", "que", "es", "su", "sus", "le", "les",
    "the", "to", "of", "and", "a", "an", "in", "on", "for", "my", "is", "it", "please", "porfa",
}  # fmt: skip


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def features(text: str) -> Dict[str, float]:
    """What a request "smells" of in words: each word and its root (letter
    trigrams were tried and excited almost every glomerulus: no contrast)."""
    words = [
        w
        for w in re.findall(r"[a-z0-9ñ]+", _fold(text))
        if w not in _STOP and len(w) > 1
    ]
    out: Dict[str, float] = {}
    for w in words[:200]:
        out["w:" + w] = out.get("w:" + w, 0.0) + 1.0
        if len(w) > 4:
            out["r:" + w[:4]] = out.get("r:" + w[:4], 0.0) + 0.8
    return out


class MushroomBody:
    def __init__(
        self,
        wiring: Wiring,
        folder: Optional[Path] = None,
        name: str = "sergio",
        receptors: Any = None,
        adapts: bool = False,
        sparsity: float = SPARSITY,
    ) -> None:
        self.wiring = wiring
        self.receptors = receptors  # meaning -> projection neurons (shared)
        self.adapts = adapts  # only one brain teaches the receptors the background
        self.name = name
        self.path = (Path(folder) / f"{name}.npz") if folder else None
        self._lock = threading.RLock()
        k, m = wiring.n_kc, wiring.n_mbon
        self.k_active = max(1, int(round(sparsity * k)))  # APL inhibition
        self.fast = np.zeros((m, k), dtype=np.float32)
        self.slow = np.zeros((m, k), dtype=np.float32)
        self.grown = np.zeros((m, k), dtype=bool)
        self.elig = np.zeros((m, k), dtype=np.uint8)
        self.codes: Dict[str, List[int]] = {}
        self.replay: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = {
            "created": time.time(),
            "updated": time.time(),
            "rewards": 0,
            "punishments": 0,
            "grown_total": 0,
            "pruned_total": 0,
            "sleeps": 0,
            "history": [],
        }
        self._tie = np.array(
            [(zlib.crc32(f"{name}:{i}".encode()) % 997) * 1e-7 for i in range(k)],
            dtype=np.float32,
        )
        self._claws = np.where(wiring.claws >= 0, wiring.claws, wiring.n_pn)
        self._load()

    # -- persistence ----------------------------------------------------------------
    def _load(self) -> None:
        if not self.path or not self.path.is_file():
            return
        try:
            data = np.load(self.path, allow_pickle=False)
            if data["fast"].shape != self.fast.shape:
                return  # another wiring (the real one arrived): start fresh on it
            self.fast, self.slow = data["fast"], data["slow"]
            self.grown, self.elig = (
                data["grown"].astype(bool),
                data["elig"].astype(np.uint8),
            )
            extra = json.loads(self.path.with_suffix(".json").read_text("utf-8"))
            self.codes = {k: list(v) for k, v in extra.get("codes", {}).items()}
            self.replay = extra.get("replay", [])[-REPLAY_MAX:]
            self.meta.update(extra.get("meta", {}))
        except (OSError, ValueError, KeyError):
            pass

    def save(self) -> None:
        if not self.path:
            return
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.stem + ".tmp.npz")
            np.savez_compressed(
                tmp, fast=self.fast, slow=self.slow, grown=self.grown, elig=self.elig
            )
            tmp.replace(self.path)
            extra = {
                "codes": self.codes,
                "replay": self.replay[-REPLAY_MAX:],
                "meta": self.meta,
            }
            self.path.with_suffix(".json").write_text(
                json.dumps(extra, ensure_ascii=False), "utf-8"
            )

    # -- the circuit ------------------------------------------------------------------
    def projection(self, text: str) -> np.ndarray:
        """Projection-neuron activity for *text* (one extra slot = silence)."""
        pn = np.zeros(self.wiring.n_pn + 1, dtype=np.float32)
        n = self.wiring.n_pn
        for f, w in features(text).items():
            h = zlib.crc32(f.encode())
            pn[h % n] += w
            pn[(h >> 16) % n] += 0.5 * w
        pn[:n] = np.log1p(pn[:n])
        if self.receptors is not None:
            meaning = self.receptors.activity(text, adapt=self.adapts)
            if meaning is not None and len(meaning) == n:
                pn[:n] += meaning
        pn[n] = 0.0
        return pn

    def kenyon(self, text: str) -> np.ndarray:
        """The Kenyon cells that fire (indices, strongest first)."""
        pn = self.projection(text)
        if not pn.any():
            return np.zeros(0, dtype=np.int32)
        drive = (pn[self._claws] * self.wiring.claw_w).sum(axis=1) + self._tie
        drive[drive <= self._tie + 1e-9] = 0.0
        k = min(self.k_active, int((drive > 0).sum()))
        if k == 0:
            return np.zeros(0, dtype=np.int32)
        top = np.argpartition(-drive, k - 1)[:k]
        return top[np.argsort(-drive[top])].astype(np.int32)

    def code(self, action: str) -> List[int]:
        """The output neurons that stand for *action* (spread over compartments)."""
        if action not in self.codes:
            m = self.wiring.n_mbon
            rng = np.random.default_rng(stable_seed(action))
            dans = self.wiring.mbon_dan
            order = rng.permutation(m)
            picked, seen = [], set()
            for j in order:  # one per compartment first, then any
                if int(dans[j]) not in seen:
                    picked.append(int(j))
                    seen.add(int(dans[j]))
                if len(picked) == min(CODE, m):
                    break
            for j in order:
                if len(picked) >= min(CODE, m):
                    break
                if int(j) not in picked:
                    picked.append(int(j))
            self.codes[action] = sorted(picked)
        return self.codes[action]

    def plastic(self) -> np.ndarray:
        return self.wiring.mask0 | self.grown

    def output(self, kc: np.ndarray) -> np.ndarray:
        """Learned drive of every output neuron for these Kenyon cells."""
        if not len(kc):
            return np.zeros(self.wiring.n_mbon, dtype=np.float32)
        return (self.fast[:, kc] + self.slow[:, kc]).sum(axis=1) / len(kc)

    def scores(self, text_or_kc: Any, actions: Iterable[str]) -> Dict[str, float]:
        """How much each action is wanted for this request (0 = nothing learned)."""
        with self._lock:
            kc = (
                self.kenyon(text_or_kc)
                if isinstance(text_or_kc, str)
                else np.asarray(text_or_kc)
            )
            out = self.output(kc)
            return {a: float(out[self.code(a)].mean()) for a in actions}

    # -- learning -----------------------------------------------------------------------
    def learn(
        self,
        text_or_kc: Any,
        action: str,
        reward: float,
        *,
        remember: bool = True,
        now: Optional[float] = None,
    ) -> Dict[str, int]:
        """Dopamine for *action* after this request: + rewards, - punishes.

        Returns what changed: synapses modified and synapses grown."""
        with self._lock:
            kc = (
                self.kenyon(text_or_kc)
                if isinstance(text_or_kc, str)
                else np.asarray(text_or_kc, dtype=np.int32)
            )
            if not len(kc) or not reward:
                return {"changed": 0, "grown": 0}
            reward = float(max(-1.0, min(1.0, reward)))
            code = self.code(action)
            plastic = self.plastic()
            rows = np.array(code)[:, None]
            cols = kc[None, :]
            allowed = plastic[rows, cols]
            delta = LR * reward * allowed
            block = self.fast[rows, cols]
            block += delta * (
                1.0 - np.sign(reward) * block
            )  # saturating, stays in [-1, 1]
            self.fast[rows, cols] = np.clip(block, -1.0, 1.0)
            changed = int(allowed.sum())
            grown = 0
            if reward > 0:
                others = np.setdiff1d(np.arange(self.wiring.n_mbon), code)
                hrows = others[:, None]
                hmask = plastic[hrows, cols]
                self.fast[hrows, cols] -= HETERO * reward * hmask
                # structural plasticity: co-rewarded pairs without a synapse
                missing = ~allowed
                if missing.any():
                    e = self.elig[rows, cols].astype(np.int16) + missing
                    born = missing & (e >= GROW_AFTER)
                    self.elig[rows, cols] = np.minimum(e, 255).astype(np.uint8)
                    if born.any():
                        r_idx, c_idx = np.nonzero(born)
                        gr, gc = rows[r_idx, 0], kc[c_idx]
                        self.grown[gr, gc] = True
                        self.fast[gr, gc] = LR * reward
                        self.elig[gr, gc] = 0
                        grown = int(born.sum())
                        self.meta["grown_total"] = (
                            int(self.meta.get("grown_total", 0)) + grown
                        )
            key = "rewards" if reward > 0 else "punishments"
            self.meta[key] = int(self.meta.get(key, 0)) + 1
            self.meta["updated"] = now or time.time()
            if remember:
                self.replay.append(
                    {
                        "kc": kc[:64].tolist(),
                        "a": action,
                        "r": round(reward, 3),
                        "t": round(now or time.time()),
                    }
                )
                if len(self.replay) > REPLAY_MAX:
                    self.replay = self.replay[-REPLAY_MAX:]
            return {"changed": changed, "grown": grown}

    def reset(self) -> None:
        """Back to a newborn brain on the same wiring (its senses changed)."""
        with self._lock:
            self.fast[:] = 0.0
            self.slow[:] = 0.0
            self.grown[:] = False
            self.elig[:] = 0
            self.replay = []
            for k in (
                "rewards",
                "punishments",
                "grown_total",
                "pruned_total",
                "sleeps",
            ):
                self.meta[k] = 0
            self.meta["history"] = []

    def decay(self, now: Optional[float] = None) -> None:
        """Forgetting: the fast trace in hours, the slow one in months."""
        with self._lock:
            now = now or time.time()
            last = float(self.meta.get("decayed") or now)
            hours = max(0.0, (now - last) / 3600)
            if hours < 0.05:
                return
            self.fast *= math.exp(-hours / TAU_FAST_H)
            self.slow *= math.exp(-hours / 24 / TAU_SLOW_D)
            self.meta["decayed"] = now

    def accuracy(self, episodes: Optional[Sequence[Dict[str, Any]]] = None) -> float:
        """Of the rewarded episodes, how many the brain would choose again
        (the right action ranked first among all it has learned)."""
        eps = [
            e
            for e in (episodes if episodes is not None else self.replay)
            if e.get("r", 0) > 0
        ]
        actions = sorted({e["a"] for e in eps})
        if not eps or len(actions) < 2:
            return 0.0
        hits = 0
        for e in eps:
            s = self.scores(np.array(e["kc"], dtype=np.int32), actions)
            hits += max(s, key=s.get) == e["a"]
        return hits / len(eps)

    def consolidate(
        self, epochs: int = 3, now: Optional[float] = None
    ) -> Dict[str, Any]:
        """Sleep: replay the episodes into the slow trace (retraining), move
        half of the fast trace there, prune grown synapses that did nothing."""
        with self._lock:
            before = self.accuracy()
            plastic = self.plastic()
            for _ in range(max(1, epochs)):
                for e in self.replay[-REPLAY_MAX:]:
                    kc = np.array(e["kc"], dtype=np.int32)
                    if not len(kc):
                        continue
                    rows = np.array(self.code(e["a"]))[:, None]
                    cols = kc[None, :]
                    allowed = plastic[rows, cols]
                    s = self.slow[rows, cols]
                    s += 0.05 * float(e["r"]) * allowed * (1.0 - np.sign(e["r"]) * s)
                    self.slow[rows, cols] = np.clip(s, -1, 1)
            self.slow = np.clip(self.slow + 0.5 * self.fast, -1, 1)
            self.fast *= 0.5
            useless = self.grown & (np.abs(self.fast + self.slow) < 0.01)
            pruned = int(useless.sum())
            self.grown &= ~useless
            self.fast[useless] = 0.0
            self.slow[useless] = 0.0
            after = self.accuracy()
            report = {
                "t": round(now or time.time()),
                "episodes": len(self.replay),
                "epochs": epochs,
                "accuracy_before": round(before, 3),
                "accuracy_after": round(after, 3),
                "pruned": pruned,
            }
            self.meta["sleeps"] = int(self.meta.get("sleeps", 0)) + 1
            self.meta["pruned_total"] = int(self.meta.get("pruned_total", 0)) + pruned
            hist = list(self.meta.get("history", []))[-59:]
            hist.append(report)
            self.meta["history"] = hist
            return report

    # -- what the Cerebro page shows ------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            w = self.fast + self.slow
            changed = int((np.abs(w) > 1e-3).sum())
            info = self.wiring.info
            return {
                "name": self.name,
                "source": info.get("source"),
                "real": bool(info.get("real")),
                "neurons": {
                    "proyeccion": self.wiring.n_pn,
                    "kenyon": self.wiring.n_kc,
                    "salida": self.wiring.n_mbon,
                    "dopamina": int(info.get("n_dan") or 0),
                    "activas_por_pedido": self.k_active,
                },
                "synapses": {
                    "medidas": int(self.wiring.mask0.sum()),
                    "cambiadas": changed,
                    "nuevas": int(self.grown.sum()),
                    "nuevas_total": int(self.meta.get("grown_total", 0)),
                    "podadas_total": int(self.meta.get("pruned_total", 0)),
                },
                "memory": {
                    "rapida": round(float(np.abs(self.fast).sum()), 2),
                    "lenta": round(float(np.abs(self.slow).sum()), 2),
                },
                "episodes": len(self.replay),
                "rewards": int(self.meta.get("rewards", 0)),
                "punishments": int(self.meta.get("punishments", 0)),
                "sleeps": int(self.meta.get("sleeps", 0)),
                "history": list(self.meta.get("history", []))[-30:],
                "actions": len(self.codes),
            }

    def divergence(self, other: "MushroomBody") -> float:
        """How different two brains became (0 = identical learning)."""
        a = (self.fast + self.slow).ravel()
        b = (other.fast + other.slow).ravel()
        na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
        if na == 0 and nb == 0:
            return 0.0
        if na == 0 or nb == 0:
            return 1.0
        return round(1.0 - float(a @ b) / (na * nb), 4)


__all__ = ["CODE", "LR", "MushroomBody", "SPARSITY", "features"]

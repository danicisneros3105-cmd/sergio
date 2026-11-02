"""The fly's real brain — FlyWire, mapped by Google and Princeton — inside Sergio.

The owner (26 Oct 2026): «sobre el cerebro no es uno humano, es un cerebro
real mapeado por Google (el cerebro de una mosca)». FlyWire (Dorkenwald et
al., *Nature* 2024; CC BY 4.0) is the whole brain of an adult *Drosophila
melanogaster*: Google's automated reconstruction of 139 255 neurons, proofread
by the FlyWire consortium led by Princeton. ``scripts/mosca_cerebro.py``
keeps the brain outside the optic lobes — the central brain, the senses other
than the eyes, the visual projection neurons and the neurons that ascend from
and descend to the body: 49 434 neurons and every connection of at least ten
measured synapses between them — and stores it in ``connectome/data`` with
its SHA-256 (checked here before use).

:class:`Fly` carries a request through that wiring the way the fly's senses
reach its decisions: the request's sparse code lands on sensory neurons
(smell, taste, touch, temperature, humidity), and activity crosses the real
synapses step by step — antennal lobe, mushroom body and lateral horn,
central complex and the rest of the central brain, the descending neurons
that tell the body what to do. A neuron's sign follows its transmitter
(Dale's principle: acetylcholine excites, GABA and the fly's glutamate
inhibit), and only the most driven ~2 % stay on, like the mushroom body's APL
neuron keeping its code sparse. The neurons left on are the request's code
in the fly's brain; the decision stage (:mod:`.cortex`) reads it.

Honest claim: "Sergio's decisions cross the measured wiring of a real fly
brain". It is not a simulation of the fly's behaviour, and not a human brain.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import threading
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

DATA = Path(__file__).with_name("data")
EXCITE = {"ACH"}
INHIBIT = {"GABA", "GLUT"}
FANOUT = 8  # sensory neurons each input cell reaches
ACTIVE = 0.02  # share of the brain left on after inhibition
STEPS = 4  # senses → antennal lobe → mushroom body / lateral horn → central → out
OUT_SLOTS = 4096  # what the decision stage reads (fixed size for its weights)
INHIBIT_W = 1.2
MODULATE_W = 0.3  # dopamine, serotonin and octopamine nudge, they do not drive
STAGE = {
    "sensory": "sentidos",
    "sensory_ascending": "sentidos",
    "ascending": "cuerpo",
    "central": "cerebro central",
    "visual_projection": "visión",
    "descending": "órdenes al cuerpo",
    "motor": "órdenes al cuerpo",
    "endocrine": "hormonas",
}
CLASS_ES = {
    "Kenyon_Cell": "células de Kenyon",
    "MBON": "salidas (MBON)",
    "DAN": "dopamina",
    "ALPN": "lóbulo antenal",
    "ALLN": "lóbulo antenal",
    "LHLN": "cuerno lateral",
    "LHCENT": "cuerno lateral",
    "CX": "complejo central",
    "olfactory": "olfato",
    "gustatory": "gusto",
    "mechanosensory": "tacto",
    "thermosensory": "temperatura",
    "hygrosensory": "humedad",
}


class Fly:
    """The FlyWire wiring, ready to carry activity."""

    def __init__(self, folder: Path = DATA, prefix: str = "") -> None:
        self.folder = Path(folder)
        prefix = prefix or default_prefix(self.folder)
        self.prefix = prefix
        self.meta: Dict[str, Any] = json.loads(
            (self.folder / f"{prefix}.json").read_text("utf-8")
        )
        self.verified = all(
            hashlib.sha256((self.folder / name).read_bytes()).hexdigest() == digest
            for name, digest in self.meta.get("sha256", {}).items()
        )
        raw = gzip.decompress((self.folder / f"{prefix}_neuronas.csv.gz").read_bytes())
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
        self.n = len(rows)
        self.super_class = [r["superclase"] for r in rows]
        self.cls = [r["clase"] for r in rows]
        nt = [r["transmisor"] for r in rows]
        sign = np.array(
            [
                1.0 if t in EXCITE else -INHIBIT_W if t in INHIBIT else MODULATE_W
                for t in nt
            ],
            dtype=np.float32,
        )
        data = np.load(self.folder / f"{prefix}_sinapsis.npz")
        self.pre = data["pre"].astype(np.int32)
        self.post = data["post"].astype(np.int32)
        syn = data["syn"].astype(np.float32)
        self.synapses = int(syn.sum())
        weight = np.log1p(syn) * sign[self.pre]
        # Each neuron's gain scales with how much it hears (homeostasis), so the
        # big hubs do not light up for every request.
        heard = np.zeros(self.n, dtype=np.float32)
        np.add.at(heard, self.post, np.abs(weight))
        self.weight = weight / (1.0 + heard[self.post])
        self.indptr = np.searchsorted(self.pre, np.arange(self.n + 1)).astype(np.int64)
        self.vectorised = True  # one numpy pass per step (see _spread)
        self.inputs = np.array(
            [
                i
                for i, (s, c) in enumerate(zip(self.super_class, self.cls))
                if s == "sensory" and c != "visual"
            ],
            dtype=np.int32,
        )
        if not len(self.inputs):
            self.inputs = np.arange(self.n, dtype=np.int32)
        self.k_active = max(8, int(ACTIVE * self.n))
        self.transmitters: Dict[str, int] = {}
        for t in nt:
            self.transmitters[t or "?"] = self.transmitters.get(t or "?", 0) + 1

    # -- activity ---------------------------------------------------------------
    def senses(self, cells: Sequence[int]) -> np.ndarray:
        """Where each input cell lands among the sensory neurons (fixed)."""
        drive = np.zeros(self.n, dtype=np.float32)
        m = len(self.inputs)
        for c in cells:
            h = zlib.crc32(f"sentido:{int(c)}".encode())
            for j in range(FANOUT):
                drive[self.inputs[(h + j * 2654435761) % m]] += 1.0
        return drive

    def run(self, cells: Sequence[int]) -> Dict[str, Any]:
        """Carry a code through the measured synapses. Returns the neurons on
        at each step and all of them (the brain's response)."""
        v = self.senses(cells)
        on = np.flatnonzero(v > 0).astype(np.int32)
        steps = [on]
        seen = set(on.tolist())
        for _ in range(STEPS):
            if self.vectorised:
                nxt = self._spread(on, v)
            else:
                nxt = np.zeros(self.n, dtype=np.float32)
                for a in on:
                    lo, hi = self.indptr[a], self.indptr[a + 1]
                    if hi > lo:
                        nxt[self.post[lo:hi]] += self.weight[lo:hi] * v[a]
            v = np.maximum(nxt, 0.0) + 0.2 * v  # what was on fades, it does not vanish
            on = _top(v, self.k_active)
            if not len(on):
                break
            steps.append(on)
            seen.update(on.tolist())
        return {"pasos": steps, "activas": np.array(sorted(seen), dtype=np.int32)}

    def _spread(self, on: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Every synapse leaving the neurons that are on, in one numpy pass:
        their outgoing ranges gathered and summed per receiver (bincount)."""
        if not len(on):
            return np.zeros(self.n, dtype=np.float32)
        starts = self.indptr[on]
        lens = self.indptr[on + 1] - starts
        total = int(lens.sum())
        if not total:
            return np.zeros(self.n, dtype=np.float32)
        offsets = np.repeat(starts - np.concatenate(([0], np.cumsum(lens)[:-1])), lens)
        idx = offsets + np.arange(total)
        pushed = self.weight[idx] * np.repeat(v[on], lens)
        return np.bincount(self.post[idx], weights=pushed, minlength=self.n).astype(
            np.float32
        )

    def code(self, cells: Sequence[int]) -> List[int]:
        """The brain's response as slots the decision stage can read."""
        if not cells:
            return []
        return sorted({int(i) % OUT_SLOTS for i in self.run(cells)["activas"]})

    def path(self, cells: Sequence[int]) -> List[Dict[str, Any]]:
        """Which parts of the fly's brain lit up at each step, in words."""
        out = []
        for i, step in enumerate(self.run(cells)["pasos"]):
            parts: Dict[str, int] = {}
            for n in step:
                name = CLASS_ES.get(self.cls[n]) or STAGE.get(
                    self.super_class[n], "otras"
                )
                parts[name] = parts.get(name, 0) + 1
            top = sorted(parts.items(), key=lambda kv: -kv[1])[:4]
            out.append({"paso": i, "neuronas": int(len(step)), "zonas": dict(top)})
        return out

    def describe(self) -> Dict[str, Any]:
        stages: Dict[str, int] = {}
        for s in self.super_class:
            name = STAGE.get(s, s)
            stages[name] = stages.get(name, 0) + 1
        parts: Dict[str, int] = {}
        for c in self.cls:
            if c in CLASS_ES:
                parts[CLASS_ES[c]] = parts.get(CLASS_ES[c], 0) + 1
        return {
            "fuente": self.meta.get("fuente"),
            "licencia": self.meta.get("licencia"),
            "region": self.meta.get("region"),
            "verificado": self.verified,
            "neuronas": self.n,
            "neuronas_cerebro_completo": self.meta.get("neuronas_cerebro_completo"),
            "conexiones": int(len(self.pre)),
            "sinapsis": self.synapses,
            "etapas": dict(sorted(stages.items(), key=lambda kv: -kv[1])),
            "zonas": dict(sorted(parts.items(), key=lambda kv: -kv[1])),
            "transmisores": dict(
                sorted(self.transmitters.items(), key=lambda kv: -kv[1])
            ),
        }


def _top(v: np.ndarray, k: int) -> np.ndarray:
    live = int((v > 0).sum())
    if not live:
        return np.zeros(0, dtype=np.int32)
    k = min(k, live)
    idx = np.argpartition(-v, k - 1)[:k]
    return idx[v[idx] > 0].astype(np.int32)


def default_prefix(folder: Path = DATA) -> str:
    """The whole brain when its files are here (owner, 2 Nov 2026: «neuronas
    reales completas»), else the brain without the optic lobes;
    ``SERGIO_MOSCA=central`` keeps the smaller one."""
    import os

    if os.environ.get("SERGIO_MOSCA", "").strip().lower() == "central":
        return "mosca"
    return (
        "mosca_completa"
        if (Path(folder) / "mosca_completa.json").is_file()
        else "mosca"
    )


_FLY: Optional[Fly] = None
_FAILED = False
_LOCK = threading.Lock()


def fly() -> Optional[Fly]:
    """The fly's wiring, loaded once (None if its files are missing or altered)."""
    global _FLY, _FAILED
    if _FLY is not None or _FAILED:
        return _FLY
    with _LOCK:
        if _FLY is None and not _FAILED:
            try:
                f = Fly()
                if f.verified and f.n:
                    _FLY = f
                else:
                    _FAILED = True
            except (OSError, ValueError, KeyError):
                _FAILED = True
    return _FLY


def describe() -> Dict[str, Any]:
    f = fly()
    if f is None:
        return {"verificado": False}
    return f.describe()


__all__ = ["Fly", "OUT_SLOTS", "describe", "fly"]

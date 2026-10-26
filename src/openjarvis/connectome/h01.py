"""A real piece of human cortex — Google's H01 connectome — inside Sergio.

H01 (Shapson-Coe, Januszewski, Berger et al., *Science* 2024; Google
Research and the Lichtman lab at Harvard; CC BY 4.0) is one cubic millimetre
of human temporal cortex mapped synapse by synapse. ``scripts/h01_corteza.py``
reads its cell table and walks the whole exported synapse table, keeping the
synapses between neurons whose cell body lies in the volume; the result lives
in ``connectome/data`` with its SHA-256 (checked here before use):

* every neuron with its cell type (pyramidal, interneuron, spiny stellate…)
  and its cortical layer (1 to 6);
* every measured connection between two of them, with its synapse count.

:class:`Column` runs what the thalamus lets through over that real wiring, the
way a cortical column does: thalamic axons land on layer 4 (and a few on 5
and 6), layer 4 talks to 2/3, 2/3 to 5, 5 sends out — each step through the
measured synapses, pyramidal and stellate cells exciting and interneurons
inhibiting (Dale's principle: a neuron's sign follows its cell type), and only
the most driven few per cent stay on (the inhibition that keeps cortical
codes sparse). The neurons left active are the request's code in human
cortex; the basal ganglia read it (in the brain, layer-5 neurons are what
project to the striatum).

It is a millimetre of one person's cortex, not a brain: the honest claim is
"Sergio's cortical layer is wired with measured human synapses".
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import threading
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

DATA = Path(__file__).with_name("data")
META = DATA / "h01.json"
EXCITATORY = {"PYRAMIDAL", "SPINY_STELLATE", "SPINY_ATYPICAL"}
INHIBITORY = {"INTERNEURON", "C_SHAPED"}
LAYERS = (
    "Layer 1",
    "Layer 2",
    "Layer 3",
    "Layer 4",
    "Layer 5",
    "Layer 6",
    "White matter",
)
THALAMIC_FANOUT = 8  # layer-4 neurons each thalamic cell reaches
ACTIVE = 0.03  # share of the column left on after inhibition
STEPS = 3  # 4 → 2/3 → 5 → out
OUT_SLOTS = 4096  # the striatum's view of the column (fixed size for the weights)
INHIBIT = 1.5  # an interneuron's synapse counts this much (they hit somata)


class Column:
    """The H01 wiring, ready to carry activity."""

    def __init__(self, folder: Path = DATA) -> None:
        self.folder = Path(folder)
        self.meta: Dict[str, Any] = json.loads(
            (self.folder / "h01.json").read_text("utf-8")
        )
        self.verified = all(
            hashlib.sha256((self.folder / name).read_bytes()).hexdigest() == digest
            for name, digest in self.meta.get("sha256", {}).items()
        )
        with gzip.open(self.folder / "h01_neuronas.csv.gz", "rt") as f:
            rows = list(csv.DictReader(f))
        self.ids = [r["soma_id"] for r in rows]
        index = {sid: i for i, sid in enumerate(self.ids)}
        self.kind = [r["tipo"] for r in rows]
        self.layer = np.array(
            [LAYERS.index(r["capa"]) if r["capa"] in LAYERS else -1 for r in rows],
            dtype=np.int8,
        )
        sign = np.array(
            [-INHIBIT if k in INHIBITORY else 1.0 for k in self.kind], dtype=np.float32
        )
        pre, post, n = [], [], []
        with gzip.open(self.folder / "h01_sinapsis.csv.gz", "rt") as f:
            for r in csv.DictReader(f):
                a, b = index.get(r["pre"]), index.get(r["post"])
                if a is None or b is None:
                    continue
                pre.append(a)
                post.append(b)
                n.append(int(r["tipo1"]) + int(r["tipo2"]) + int(r["otro"]))
        pre_a = np.asarray(pre, dtype=np.int32)
        order = np.argsort(pre_a, kind="stable")
        self.pre = pre_a[order]
        self.post = np.asarray(post, dtype=np.int32)[order]
        self.weight = (np.log1p(np.asarray(n, dtype=np.float32)) * sign[self.pre])[
            order
        ]
        self.n = len(self.ids)
        self.indptr = np.searchsorted(self.pre, np.arange(self.n + 1)).astype(np.int64)
        self.synapses = int(np.sum(n))
        l4 = np.flatnonzero(self.layer == 3)
        deep = np.flatnonzero((self.layer == 4) | (self.layer == 5))
        self.inputs = (
            np.concatenate([l4, deep[: max(1, len(deep) // 5)]])
            if len(l4)
            else np.arange(self.n)
        )
        self.k_active = max(4, int(ACTIVE * self.n))

    # -- activity ---------------------------------------------------------------
    def thalamic(self, cells: Sequence[int]) -> np.ndarray:
        """Where each thalamic cell's axon lands (fixed, like development)."""
        drive = np.zeros(self.n, dtype=np.float32)
        m = len(self.inputs)
        for c in cells:
            h = zlib.crc32(f"talamo:{int(c)}".encode())
            for j in range(THALAMIC_FANOUT):
                drive[self.inputs[(h + j * 2654435761) % m]] += 1.0
        return drive

    def run(self, cells: Sequence[int]) -> Dict[str, Any]:
        """Carry a thalamic code through the measured synapses. Returns the
        neurons active at each step and the union (the column's response)."""
        v = self.thalamic(cells)
        on = _top(v, self.k_active)
        steps = [on]
        seen = set(on.tolist())
        for _ in range(STEPS - 1):
            nxt = np.zeros(self.n, dtype=np.float32)
            for a in on:
                lo, hi = self.indptr[a], self.indptr[a + 1]
                if hi > lo:
                    np.add.at(nxt, self.post[lo:hi], self.weight[lo:hi] * v[a])
            nxt = (
                np.maximum(nxt, 0.0) + 0.25 * v
            )  # what was on fades, it does not vanish
            v = nxt
            on = _top(v, self.k_active)
            if not len(on):
                break
            steps.append(on)
            seen.update(on.tolist())
        return {"pasos": steps, "activas": np.array(sorted(seen), dtype=np.int32)}

    def code(self, cells: Sequence[int]) -> List[int]:
        """The column's response as slots the basal ganglia can read."""
        if not cells:
            return []
        return sorted({int(i) % OUT_SLOTS for i in self.run(cells)["activas"]})

    def describe(self) -> Dict[str, Any]:
        layers = {
            name: int((self.layer == i).sum())
            for i, name in enumerate(LAYERS)
            if (self.layer == i).any()
        }
        kinds: Dict[str, int] = {}
        for k in self.kind:
            kinds[k] = kinds.get(k, 0) + 1
        return {
            "fuente": self.meta.get("fuente"),
            "licencia": self.meta.get("licencia"),
            "region": self.meta.get("region"),
            "verificado": self.verified,
            "neuronas": self.n,
            "conexiones": int(len(self.pre)),
            "sinapsis": self.synapses,
            "partes": f"{self.meta.get('partes_leidas')}/{self.meta.get('partes_totales')}",
            "capas": layers,
            "tipos": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
        }


def _top(v: np.ndarray, k: int) -> np.ndarray:
    live = int((v > 0).sum())
    if not live:
        return np.zeros(0, dtype=np.int32)
    k = min(k, live)
    idx = np.argpartition(-v, k - 1)[:k]
    return idx[v[idx] > 0].astype(np.int32)


_COLUMN: Optional[Column] = None
_FAILED = False
_LOCK = threading.Lock()


def column() -> Optional[Column]:
    """The H01 column, loaded once (None if its files are missing or altered)."""
    global _COLUMN, _FAILED
    if _COLUMN is not None or _FAILED:
        return _COLUMN
    with _LOCK:
        if _COLUMN is None and not _FAILED:
            try:
                c = Column()
                if c.verified and c.n:
                    _COLUMN = c
                else:
                    _FAILED = True
            except (OSError, ValueError, KeyError):
                _FAILED = True
    return _COLUMN


def describe() -> Dict[str, Any]:
    c = column()
    if c is None:
        return {"verificado": False}
    return c.describe()


__all__ = ["Column", "OUT_SLOTS", "column", "describe"]

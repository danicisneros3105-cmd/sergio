"""The real wiring of the fly's learning centre, from the measured connectome.

Sergio's core is the mushroom body of *Drosophila*: the part of the brain
where flies learn what to approach and what to avoid. Its wiring is not
invented here; it comes from the MaleCNS v1.0 connectome (FlyEM / HHMI
Janelia, Cambridge, MRC LMB, Google; CC-BY-4.0), packaged as
``fernandofernandes/fly-connectome-49k`` on Hugging Face: 49 393 neurons of
the central brain and 9 050 172 measured connections.

:func:`download` fetches the five files Sergio needs (about 55 MB), checks
every SHA-256 against the package's manifest, and :func:`extract` keeps only
the learning circuit, by cell type:

* projection neurons (``…PN``): the input, like the olfactory glomeruli;
* Kenyon cells (``KC…``): thousands of cells, each listening to a few
  projection neurons through its real "claws";
* output neurons (``MBON…``): where Kenyon cells write what was learned;
* dopamine neurons (``PAM…``, ``PPL…``): the reward and punishment signal,
  each tied to the output neurons it touches (its compartment).

The circuit is saved as ``mb.npz`` (a few MB). Without it (no internet yet),
:func:`synthetic` builds a stand-in with the published counts of one
hemisphere (Li et al. 2020, Dorkenwald et al. 2024), clearly marked as such.
"""

from __future__ import annotations

import hashlib
import json
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

REPO = "fernandofernandes/fly-connectome-49k"
BASE = f"https://huggingface.co/datasets/{REPO}/resolve/main/"
# manifest key -> path in the package
FILES = {
    "edges_offsets": "graph/edges_offsets.i32",
    "edges_source": "graph/edges_source.u16",
    "edges_weight_f32": "graph/edges_weight.f32",
    "cell_type": "neurons/cell_type.json",
}
MAX_CLAWS = 24
SOURCE_REAL = "FlyWire / MaleCNS v1.0, conectoma medido (fly-connectome-49k, CC-BY-4.0)"
SOURCE_SYNTH = (
    "Sustituto con los números publicados (falta descargar el conectoma real)"
)


@dataclass
class Wiring:
    """The learning circuit: who listens to whom, and how strongly."""

    claws: np.ndarray  # (K, C) int32: input neuron of each claw, -1 = none
    claw_w: np.ndarray  # (K, C) float32: synaptic weight of each claw
    mask0: np.ndarray  # (M, K) bool: the measured Kenyon -> output synapses
    w0: np.ndarray  # (M, K) float32: their measured strength (0..1)
    mbon_dan: (
        np.ndarray
    )  # (M,) int32: the dopamine neuron that teaches each output neuron
    kc_class: List[str]  # (K,) gamma / alpha-beta / alpha'-beta' / other
    mbon_types: List[str]
    info: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_pn(self) -> int:
        return int(self.info.get("n_pn") or (self.claws.max() + 1))

    @property
    def n_kc(self) -> int:
        return int(self.claws.shape[0])

    @property
    def n_mbon(self) -> int:
        return int(self.mask0.shape[0])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            claws=self.claws,
            claw_w=self.claw_w,
            mask0=self.mask0,
            w0=self.w0.astype(np.float16),
            mbon_dan=self.mbon_dan,
        )
        meta = {**self.info, "kc_class": self.kc_class, "mbon_types": self.mbon_types}
        path.with_suffix(".json").write_text(
            json.dumps(meta, ensure_ascii=False), "utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "Wiring":
        data = np.load(path)
        meta = json.loads(path.with_suffix(".json").read_text("utf-8"))
        return cls(
            claws=data["claws"].astype(np.int32),
            claw_w=data["claw_w"].astype(np.float32),
            mask0=data["mask0"].astype(bool),
            w0=data["w0"].astype(np.float32),
            mbon_dan=data["mbon_dan"].astype(np.int32),
            kc_class=list(meta.pop("kc_class")),
            mbon_types=list(meta.pop("mbon_types")),
            info=meta,
        )


# -- the real one --------------------------------------------------------------------------


def _kind(cell_type: str) -> str:
    t = cell_type or ""
    if t.startswith("KC"):
        return "kc"
    if t.startswith("MBON"):
        return "mbon"
    if t.startswith(("PAM", "PPL")):
        return "dan"
    if "PN" in t and not t.startswith(("LN", "MBON")):
        return "pn"
    return ""


def _kc_class(cell_type: str) -> str:
    if cell_type.startswith("KCg"):
        return "gamma"
    if cell_type.startswith(("KCa'b'", "KCapbp")):
        return "alpha'-beta'"
    if cell_type.startswith("KCab"):
        return "alpha-beta"
    return "other"


def extract(
    offsets: np.ndarray,
    source: np.ndarray,
    weight: np.ndarray,
    cell_types: List[str],
    info: Dict[str, Any],
) -> Wiring:
    """Keep the mushroom body out of the whole graph (rows are destinations)."""
    kinds = [_kind(t) for t in cell_types]
    pn = [i for i, k in enumerate(kinds) if k == "pn"]
    kc = [i for i, k in enumerate(kinds) if k == "kc"]
    mbon = [i for i, k in enumerate(kinds) if k == "mbon"]
    dan = [i for i, k in enumerate(kinds) if k == "dan"]
    pn_ix = {g: j for j, g in enumerate(pn)}
    kc_ix = {g: j for j, g in enumerate(kc)}
    dan_ix = {g: j for j, g in enumerate(dan)}

    claws = np.full((len(kc), MAX_CLAWS), -1, dtype=np.int32)
    claw_w = np.zeros((len(kc), MAX_CLAWS), dtype=np.float32)
    for j, g in enumerate(kc):
        lo, hi = int(offsets[g]), int(offsets[g + 1])
        ins = [
            (pn_ix[int(s)], abs(float(w)))
            for s, w in zip(source[lo:hi], weight[lo:hi])
            if int(s) in pn_ix
        ]
        ins.sort(key=lambda x: -x[1])
        for c, (p, w) in enumerate(ins[:MAX_CLAWS]):
            claws[j, c], claw_w[j, c] = p, w

    mask0 = np.zeros((len(mbon), len(kc)), dtype=bool)
    w0 = np.zeros((len(mbon), len(kc)), dtype=np.float32)
    mbon_dan = np.full(len(mbon), -1, dtype=np.int32)
    for m, g in enumerate(mbon):
        lo, hi = int(offsets[g]), int(offsets[g + 1])
        best = (-1, 0.0)
        for s, w in zip(source[lo:hi], weight[lo:hi]):
            s = int(s)
            if s in kc_ix:
                mask0[m, kc_ix[s]] = True
                w0[m, kc_ix[s]] = abs(float(w))
            elif s in dan_ix and abs(float(w)) > best[1]:
                best = (dan_ix[s], abs(float(w)))
        mbon_dan[m] = best[0]
    if w0.max() > 0:
        w0 /= w0.max()
    if claw_w.max() > 0:
        claw_w /= claw_w.max()
    info = {
        **info,
        "n_pn": len(pn),
        "n_kc": len(kc),
        "n_mbon": len(mbon),
        "n_dan": len(dan),
        "kc_mbon_synapses": int(mask0.sum()),
        "pn_kc_synapses": int((claws >= 0).sum()),
    }
    return Wiring(
        claws, claw_w, mask0, w0, mbon_dan,
        [_kc_class(cell_types[g]) for g in kc], [cell_types[g] for g in mbon], info,
    )  # fmt: skip


def download(
    dest: Path,
    *,
    fetch: Optional[Callable[[str], bytes]] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> Wiring:
    """Fetch the measured connectome, verify it and keep its learning circuit."""
    if fetch is None:
        import httpx

        def fetch(path: str) -> bytes:
            with httpx.Client(timeout=600, follow_redirects=True) as c:
                r = c.get(BASE + path)
                r.raise_for_status()
                return r.content

    say = progress or (lambda _m: None)
    manifest = json.loads(fetch("manifest.json"))
    arrays: Dict[str, bytes] = {}
    for key, path in FILES.items():
        say(f"descargando {path}")
        data = fetch(path)
        want = manifest["files"][key]["sha256"]
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            raise ValueError(
                f"{path}: la huella no coincide ({got[:12]} ≠ {want[:12]}); no se usa"
            )
        arrays[key] = data
    say("extrayendo el cuerpo fungiforme")
    wiring = extract(
        np.frombuffer(arrays["edges_offsets"], dtype=np.int32),
        np.frombuffer(arrays["edges_source"], dtype=np.uint16),
        np.frombuffer(arrays["edges_weight_f32"], dtype=np.float32),
        json.loads(arrays["cell_type"]),
        {
            "source": SOURCE_REAL,
            "real": True,
            "repo": REPO,
            "neurons_total": int(manifest.get("neurons") or 0),
            "edges_total": int(manifest.get("edges") or 0),
            "sha256": {k: manifest["files"][k]["sha256"] for k in FILES},
            "license": "CC-BY-4.0 (FlyEM / HHMI Janelia, U. Cambridge, MRC LMB, Google Research)",
        },
    )
    wiring.save(dest / "mb.npz")
    return wiring


# -- the stand-in ----------------------------------------------------------------------------

# Published counts for one hemisphere: ~150 uniglomerular projection neurons,
# ~2 000 Kenyon cells (gamma ~670, alpha-beta ~990, alpha'-beta' ~340), each
# with ~7 claws; 15 compartments with 2-4 output neurons each.
COMPARTMENTS = (
    ("gamma", 5), ("alpha-beta", 5), ("alpha'-beta'", 5),
)  # fmt: skip


def synthetic(seed: int = 7) -> Wiring:
    rng = np.random.default_rng(seed)
    n_pn = 150
    classes = ["gamma"] * 670 + ["alpha-beta"] * 990 + ["alpha'-beta'"] * 340
    k = len(classes)
    claws = np.full((k, MAX_CLAWS), -1, dtype=np.int32)
    claw_w = np.zeros((k, MAX_CLAWS), dtype=np.float32)
    for i in range(k):
        n = int(np.clip(rng.poisson(6.9), 3, 12))
        claws[i, :n] = rng.choice(n_pn, size=n, replace=False)
        claw_w[i, :n] = rng.lognormal(0.0, 0.5, size=n)
    claw_w /= claw_w.max()
    mbon_types, mbon_dan, rows = [], [], []
    dan = 0
    for cls, comps in COMPARTMENTS:
        members = np.array([i for i, c in enumerate(classes) if c == cls])
        for c in range(comps):
            for m in range(3):
                mask = np.zeros(k, dtype=bool)
                mask[members[rng.random(len(members)) < 0.85]] = True
                mask[rng.random(k) < 0.02] = True
                rows.append(mask)
                mbon_types.append(f"MBON-{cls}{c + 1}-{m + 1}")
                mbon_dan.append(dan)
            dan += 1
    mask0 = np.array(rows)
    w0 = (rng.lognormal(0.0, 0.6, size=mask0.shape) * mask0).astype(np.float32)
    w0 /= w0.max()
    info = {
        "source": SOURCE_SYNTH,
        "real": False,
        "n_pn": n_pn,
        "n_kc": k,
        "n_mbon": int(mask0.shape[0]),
        "n_dan": dan,
        "kc_mbon_synapses": int(mask0.sum()),
        "pn_kc_synapses": int((claws >= 0).sum()),
    }
    return Wiring(
        claws,
        claw_w,
        mask0,
        w0,
        np.array(mbon_dan, dtype=np.int32),
        classes,
        mbon_types,
        info,
    )


def load(folder: Path) -> Wiring:
    """The real circuit when it was downloaded, the stand-in otherwise."""
    path = Path(folder) / "mb.npz"
    if path.is_file() and path.with_suffix(".json").is_file():
        try:
            return Wiring.load(path)
        except (OSError, ValueError, KeyError):
            pass
    return synthetic()


def stable_seed(name: str) -> int:
    return zlib.crc32(name.encode()) & 0x7FFFFFFF


__all__ = [
    "FILES",
    "REPO",
    "SOURCE_REAL",
    "SOURCE_SYNTH",
    "Wiring",
    "download",
    "extract",
    "load",
    "synthetic",
]

"""Package the fly's real brain wiring (FlyWire, Google + Princeton) for Sergio.

FlyWire (Dorkenwald et al., *Nature* 2024; reconstruction by Google's
automated segmentation, proofread by the FlyWire consortium; CC BY 4.0) is the
whole brain of an adult *Drosophila*: 139 255 neurons and the measured
synapses between them. This reads the public release (snapshot 783) from the
FlyWire Codex bucket and keeps the brain outside the optic lobes: the central
brain, the senses other than the eyes, the visual projection neurons and the
neurons that ascend from and descend to the body, with every connection of at
least ``MIN_SYNAPSES`` measured synapses between two of them.

    python scripts/mosca_cerebro.py [carpeta_de_descarga]

writes ``src/openjarvis/connectome/data/mosca_*`` and their SHA-256 in
``mosca.json`` (``connectome/mosca.py`` refuses files that do not match).
"""

from __future__ import annotations

import datetime
import gzip
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://storage.googleapis.com/flywire-data/codex/data/fafb/783/"
FILES = ("classification.csv.gz", "connections.csv.gz")
OUT = Path(__file__).resolve().parents[1] / "src/openjarvis/connectome/data"
MIN_SYNAPSES = 10
KEEP = {
    "central",
    "ascending",
    "descending",
    "sensory_ascending",
    "motor",
    "endocrine",
    "visual_projection",
}
# Sign by transmitter (Dale's principle): acetylcholine excites; GABA and,
# in the fly, glutamate (GluCl) inhibit; the amines modulate.
NT = ("ACH", "GABA", "GLUT", "DA", "SER", "OCT")


def fetch(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        path = folder / name
        if not path.exists():
            print("descargando", name)
            urllib.request.urlretrieve(BASE + name, path)


def build(folder: Path) -> dict:
    cl = pd.read_csv(folder / "classification.csv.gz")
    keep = cl.super_class.isin(KEEP) | (
        (cl.super_class == "sensory") & (cl["class"] != "visual")
    )
    cells = cl[keep].reset_index(drop=True)
    index = pd.Series(np.arange(len(cells)), index=cells.root_id)
    co = pd.read_csv(
        folder / "connections.csv.gz",
        dtype={"neuropil": "category", "nt_type": "category"},
    )
    co = co[co.pre_root_id.isin(index.index) & co.post_root_id.isin(index.index)]
    # A neuron's transmitter: the one its synapses carry most.
    nt = (
        co.groupby(["pre_root_id", "nt_type"], observed=True)
        .syn_count.sum()
        .reset_index()
        .sort_values("syn_count")
        .drop_duplicates("pre_root_id", keep="last")
        .set_index("pre_root_id")
        .nt_type.astype(str)
    )
    pairs = co.groupby(["pre_root_id", "post_root_id"]).syn_count.sum().reset_index()
    pairs = pairs[pairs.syn_count >= MIN_SYNAPSES]
    pre = index[pairs.pre_root_id].to_numpy(np.uint16)
    post = index[pairs.post_root_id].to_numpy(np.uint16)
    syn = np.minimum(pairs.syn_count.to_numpy(), 65535).astype(np.uint16)
    order = np.lexsort((post, pre))
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT / "mosca_sinapsis.npz", pre=pre[order], post=post[order], syn=syn[order]
    )
    table = pd.DataFrame(
        {
            "id": cells.root_id.astype(str),
            "superclase": cells.super_class,
            "clase": cells["class"].fillna(""),
            "subclase": cells.sub_class.fillna(""),
            "lado": cells.side.fillna(""),
            "transmisor": cells.root_id.map(nt).fillna(""),
        }
    )
    buf = io.StringIO()
    table.to_csv(buf, index=False)
    (OUT / "mosca_neuronas.csv.gz").write_bytes(
        gzip.compress(buf.getvalue().encode(), mtime=0)
    )
    meta = {
        "fuente": "FlyWire (Google y Princeton), Nature 2024 — cerebro completo de "
        "Drosophila melanogaster, versión 783",
        "url": BASE,
        "licencia": "CC BY 4.0",
        "region": "cerebro de la mosca sin los lóbulos ópticos (cerebro central, "
        "sentidos, neuronas ascendentes y descendentes)",
        "neuronas_cerebro_completo": int(len(cl)),
        "neuronas": int(len(cells)),
        "conexiones": int(len(pre)),
        "sinapsis": int(syn.sum()),
        "minimo_sinapsis": MIN_SYNAPSES,
        "sha256": {
            name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
            for name in ("mosca_neuronas.csv.gz", "mosca_sinapsis.npz")
        },
        "fecha": datetime.date.today().isoformat(),
    }
    (OUT / "mosca.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), "utf-8"
    )
    return meta


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "flywire_783")
    fetch(folder)
    print(json.dumps(build(folder), ensure_ascii=False, indent=1))

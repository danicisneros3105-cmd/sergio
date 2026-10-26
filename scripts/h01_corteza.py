"""Google's human cortex connectome (H01) for Sergio's brain, measured.

H01 (Shapson-Coe, Januszewski, Berger et al., Science 2024; Google Research
and the Lichtman lab, Harvard) is one cubic millimetre of human temporal
cortex mapped at nanometre resolution: about 57 000 cells and 150 million
synapses. It is public under CC BY 4.0 (gs://h01-release).

This script reads the real cell table (type and cortical layer of every
cell with a soma) and walks all 166 shards of the exported synapse table (Avro),
keeping every synapse whose two sides are neurons with a soma in the volume:
the neuron-to-neuron wiring of a piece of a human brain. It writes:

    src/openjarvis/connectome/data/h01_neuronas.csv.gz   (one row per neuron)
    src/openjarvis/connectome/data/h01_sinapsis.csv.gz   (pre, post, synapses by type)
    src/openjarvis/connectome/data/h01.json              (source, licence, counts, SHA-256)

    python scripts/h01_corteza.py            # all shards (about two hours on 4 cores)
    python scripts/h01_corteza.py --shards 8 # a quick sample

Needs ``fastavro`` (only for this script). Partial results are cached per
shard, so it can be stopped and resumed.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import sys
import time
import urllib.request
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "openjarvis" / "connectome" / "data"
BUCKET = "https://storage.googleapis.com/h01-release"
API = "https://storage.googleapis.com/storage/v1/b/h01-release/o"
SOMAS = "data/20210601/c3/tables/somas.csv"
SYNAPSES = "data/20210601/c3/synapses/exported/"
NEURONS = {
    "PYRAMIDAL",
    "INTERNEURON",
    "SPINY_STELLATE",
    "SPINY_ATYPICAL",
    "C_SHAPED",
    "UNCLASSIFIED_NEURON",
}
CACHE = Path.home() / ".cache" / "sergio-h01"

# Only the fields needed: the reader skips the rest of every record.
READER = {
    "type": "record",
    "name": "Root",
    "fields": [
        {"name": "pre_synaptic_site", "type": ["null", {"type": "record", "namespace": "root",
         "name": "Pre_Synaptic_Site", "fields": [{"name": "neuron_id", "type": ["null", "long"]}]}]},
        {"name": "post_synaptic_partner", "type": ["null", {"type": "record", "namespace": "root",
         "name": "Post_Synaptic_Partner", "fields": [{"name": "neuron_id", "type": ["null", "long"]}]}]},
        {"name": "type", "type": ["null", "long"]},
    ],
}  # fmt: skip


def fetch(path: str) -> bytes:
    with urllib.request.urlopen(f"{BUCKET}/{path}", timeout=600) as r:
        return r.read()


def shard_names() -> list[str]:
    names, token = [], ""
    while True:
        url = f"{API}?prefix={SYNAPSES}&fields=items(name),nextPageToken&maxResults=1000"
        if token:
            url += f"&pageToken={token}"
        with urllib.request.urlopen(url, timeout=60) as r:
            page = json.load(r)
        # Only the Avro shards directly in the folder (a json/ copy sits below it).
        names += [
            i["name"]
            for i in page.get("items", [])
            if "/" not in i["name"][len(SYNAPSES) :]
        ]
        token = page.get("nextPageToken", "")
        if not token:
            return sorted(names)


def neurons() -> tuple[dict[int, str], list[dict[str, str]]]:
    rows = list(csv.DictReader(io.StringIO(fetch(SOMAS).decode())))
    cells = [r for r in rows if r["celltype"] in NEURONS]
    ids: dict[int, str] = {}
    for r in cells:
        for k in ("c3_rep_manual", "c3_rep_strict"):
            if r[k] not in ("", "NULL"):
                ids[int(r[k])] = r["soma_id"]
    return ids, cells


_IDS: dict[int, str] = {}


def _init(ids: dict[int, str]) -> None:
    global _IDS
    _IDS = ids


def scan(name: str) -> dict[str, int]:
    """One shard: the synapses between two neurons with a soma, by type."""
    import fastavro

    done = CACHE / (Path(name).name + ".json")
    if done.is_file():
        return json.loads(done.read_text())
    pairs: Counter = Counter()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{BUCKET}/{name}", timeout=900) as r:
                for rec in fastavro.reader(io.BufferedReader(r, 1 << 20), reader_schema=READER):
                    pre = (rec.get("pre_synaptic_site") or {}).get("neuron_id")
                    post = (rec.get("post_synaptic_partner") or {}).get("neuron_id")
                    a, b = _IDS.get(pre), _IDS.get(post)
                    if a and b and a != b:
                        pairs[f"{a},{b},{rec.get('type') or 0}"] += 1
            break
        except Exception:  # noqa: BLE001 — a dropped connection: try again
            pairs.clear()
            time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"no pude leer {name}")
    CACHE.mkdir(parents=True, exist_ok=True)
    done.write_text(json.dumps(pairs))
    return dict(pairs)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str]) -> int:
    limit = int(argv[argv.index("--shards") + 1]) if "--shards" in argv else None
    workers = int(argv[argv.index("--workers") + 1]) if "--workers" in argv else 4
    ids, cells = neurons()
    names = shard_names()[:limit]
    print(f"{len(cells)} neuronas con soma; {len(names)} partes de sinapsis", flush=True)
    total: Counter = Counter()
    with Pool(workers, initializer=_init, initargs=(ids,)) as pool:
        for i, part in enumerate(pool.imap_unordered(scan, names), 1):
            total.update(part)
            if i % 10 == 0 or i == len(names):
                print(f"  {i}/{len(names)} partes · {sum(total.values())} sinapsis", flush=True)
    edges: dict[tuple[str, str], list[int]] = {}
    for key, n in total.items():
        a, b, kind = key.split(",")
        row = edges.setdefault((a, b), [0, 0, 0])
        row[min(int(kind), 2)] += n  # 1 and 2: the two synapse classes; 0 unknown
    wired = {a for a, _ in edges} | {b for _, b in edges}
    OUT.mkdir(parents=True, exist_ok=True)
    cells_path = OUT / "h01_neuronas.csv.gz"
    with gzip.open(cells_path, "wt", newline="", compresslevel=9) as f:
        w = csv.writer(f)
        w.writerow(["soma_id", "tipo", "capa", "x", "y", "z"])
        for r in sorted(cells, key=lambda r: int(r["soma_id"])):
            if r["soma_id"] in wired:
                w.writerow([r["soma_id"], r["celltype"], r["layer"], r["x"], r["y"], r["z"]])
    syn_path = OUT / "h01_sinapsis.csv.gz"
    with gzip.open(syn_path, "wt", newline="", compresslevel=9) as f:
        w = csv.writer(f)
        w.writerow(["pre", "post", "tipo1", "tipo2", "otro"])
        for (a, b), (other, t1, t2) in sorted(edges.items(), key=lambda kv: (int(kv[0][0]), int(kv[0][1]))):
            w.writerow([a, b, t1, t2, other])
    meta = {
        "fuente": "H01 — Google Research y laboratorio Lichtman (Harvard), Science 2024",
        "url": "gs://h01-release/data/20210601/c3",
        "licencia": "CC BY 4.0",
        "region": "corteza temporal humana, 1 mm³",
        "partes_leidas": len(names),
        "partes_totales": len(shard_names()),
        "neuronas": len(wired),
        "conexiones": len(edges),
        "sinapsis": int(sum(total.values())),
        "sha256": {cells_path.name: sha(cells_path), syn_path.name: sha(syn_path)},
        "fecha": time.strftime("%Y-%m-%d"),
    }
    (OUT / "h01.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Offline, synthetic workflow measurements; no model or competitor benchmark.

Run from the checkout: PYTHONPATH=src:windows python scripts/benchmark-professional.py
All documents and SQLite databases are created in a temporary directory.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

from sergio_escritorio import files

from openjarvis.connectors.store import KnowledgeStore
from openjarvis.security.process_runner import run_bounded


def measure(iterations: int) -> dict:
    timings = {
        "python_command_ms": [],
        "organize_undo_100_files_ms": [],
        "sqlite_100_chunks_ms": [],
    }
    with tempfile.TemporaryDirectory(prefix="sergio-professional-benchmark-") as temp:
        root = Path(temp)
        old_undo = files.UNDO_DIR
        files.UNDO_DIR = root / "undo"
        try:
            for turn in range(iterations):
                started = time.perf_counter()
                result = run_bounded(
                    [sys.executable, "-c", "print(6*7)"], cwd=root, timeout=5
                )
                assert result.returncode == 0 and result.stdout.strip() == "42"
                timings["python_command_ms"].append(
                    (time.perf_counter() - started) * 1000
                )

                folder = root / f"reports-{turn}"
                folder.mkdir()
                original = {
                    f"report-{n}.csv": f"route,latency\napi,{n}\n".encode()
                    for n in range(100)
                }
                for name, data in original.items():
                    (folder / name).write_bytes(data)
                started = time.perf_counter()
                plan = files.organize(str(folder), apply=True)
                assert files.undo(plan["undo"]) == 100
                assert {p.name: p.read_bytes() for p in folder.iterdir()} == original
                timings["organize_undo_100_files_ms"].append(
                    (time.perf_counter() - started) * 1000
                )

                with KnowledgeStore(root / f"knowledge-{turn}.db") as store:
                    started = time.perf_counter()
                    with store.transaction():
                        for n in range(100):
                            store.store(
                                f"Professional release checklist {n}",
                                source="benchmark",
                            )
                    assert len(store.retrieve("checklist", top_k=100)) == 100
                    timings["sqlite_100_chunks_ms"].append(
                        (time.perf_counter() - started) * 1000
                    )
        finally:
            files.UNDO_DIR = old_undo
    return {
        "environment": {
            "system": platform.system(),
            "python": platform.python_version(),
        },
        "iterations": iterations,
        "failures": 0,
        "measurements": {
            name: {
                "median_ms": round(statistics.median(values), 2),
                "p95_ms": round(
                    sorted(values)[min(len(values) - 1, int(len(values) * 0.95))], 2
                ),
            }
            for name, values in timings.items()
        },
        "scope": "Synthetic local workflows; excludes inference, Windows UI and competitors",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100:
        parser.error("Use 1 to 100 iterations")
    print(json.dumps(measure(args.iterations), ensure_ascii=False, indent=2))

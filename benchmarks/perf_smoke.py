"""Performance smoke benchmark with a machine-independent baseline.

Each step is timed (best of several runs) and divided by the time of a
fixed pure-Python calibration workload measured on the same machine, so a
baseline recorded on one computer is meaningful on a CI runner. A step
fails ``--check`` when it is more than ``--tolerance`` times its baseline
and at least 50 ms slower in absolute terms (noise guard).

    python benchmarks/perf_smoke.py                       # print timings
    python benchmarks/perf_smoke.py --write benchmarks/perf_baseline.json
    python benchmarks/perf_smoke.py --check benchmarks/perf_baseline.json

The memory/scanner steps use the pure-Python twins of the Rust classes so
the numbers do not depend on whether the native extension was built.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict

ABS_SLACK_S = 0.05


def best_of(fn: Callable[[], object], repeat: int) -> float:
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def calibration() -> None:
    acc = 0
    table: Dict[int, int] = {}
    for i in range(250_000):
        acc += i * i % 7
        table[i % 1024] = acc
    json.dumps([table, list(range(20_000))])


def _subprocess(code: str) -> Callable[[], object]:
    env = dict(os.environ, OPENJARVIS_NO_UPDATE_CHECK="1")
    return lambda: subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, env=env
    )


def _words(n: int, seed: int = 7) -> list[str]:
    rnd = random.Random(seed)
    vocab = [f"w{i}" for i in range(3000)] + [
        "kettle",
        "tea",
        "budget",
        "volcano",
        "meeting",
        "invoice",
    ]
    return [" ".join(rnd.choice(vocab) for _ in range(40)) for _ in range(n)]


def step_memory_sqlite() -> None:
    from openjarvis._native_fallback import SQLiteMemory

    mem = SQLiteMemory(":memory:")
    for text in _words(400):
        mem.store(text, "bench", None)
    for query in ("kettle tea", "budget meeting", "volcano invoice", "w12 w99") * 25:
        mem.retrieve(query, 5)


def step_memory_bm25() -> None:
    from openjarvis._native_fallback import BM25Memory

    mem = BM25Memory()
    for text in _words(400):
        mem.store(text, "bench", None)
    for query in ("kettle tea", "budget meeting", "volcano invoice") * 10:
        mem.retrieve(query, 5)


def step_secret_scan() -> None:
    from openjarvis._native_fallback import PIIScanner, SecretScanner

    text = (
        " ".join(_words(500))
        + " sk-abcdefghijklmnopqrstuvwxyz0123 ana@example.org 10.0.0.1"
    )
    for scanner in (SecretScanner(), PIIScanner()):
        scanner.scan(text)
        scanner.redact(text)


def step_capabilities() -> None:
    from openjarvis._native_fallback import CapabilityPolicy

    policy = CapabilityPolicy(default_deny=True)
    for i in range(50):
        policy.grant(f"agent{i}", "file:*", "/home/*")
        policy.deny(f"agent{i}", "file:write")
    for i in range(20_000):
        policy.check(f"agent{i % 60}", "file:read", "/home/ana/notes.txt")


def step_long_context() -> None:
    from openjarvis.intelligence.long_context import bm25_rank, chunk_text

    text = "\n".join(_words(3000))
    chunks = chunk_text(text, max_tokens=300)
    for question in (
        "where is the kettle",
        "budget for the meeting",
        "volcano invoice",
    ):
        bm25_rank(question, chunks)


def step_load_config() -> None:
    from openjarvis.core.config import load_config

    for _ in range(10):
        load_config.cache_clear()
        load_config()


STEPS: Dict[str, Callable[[], Callable[[], object]]] = {
    "import_cli": lambda: _subprocess("import openjarvis.cli"),
    "cli_help": lambda: _subprocess(
        "import sys; sys.argv=['sergio','--help']\nfrom openjarvis.cli import cli\ntry:\n cli()\nexcept SystemExit:\n pass"
    ),
    "load_config": lambda: step_load_config,
    "memory_sqlite": lambda: step_memory_sqlite,
    "memory_bm25": lambda: step_memory_bm25,
    "secret_scan": lambda: step_secret_scan,
    "capabilities": lambda: step_capabilities,
    "long_context_bm25": lambda: step_long_context,
}


def measure(repeat: int) -> Dict[str, Dict[str, float]]:
    unit = best_of(calibration, max(repeat, 5))
    results = {"_calibration": {"seconds": unit, "units": 1.0}}
    with tempfile.TemporaryDirectory() as home:
        os.environ["OPENJARVIS_HOME"] = home  # never read the developer's config
        for name, make in STEPS.items():
            fn = make()
            fn()  # warm-up (imports, caches)
            seconds = best_of(fn, repeat)
            results[name] = {"seconds": seconds, "units": seconds / unit}
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--write", help="save the results as the new baseline")
    ap.add_argument(
        "--check", help="compare with this baseline and fail on regressions"
    )
    ap.add_argument("--tolerance", type=float, default=1.75)
    ap.add_argument(
        "--summary",
        help="append a Markdown table to this file (e.g. $GITHUB_STEP_SUMMARY)",
    )
    args = ap.parse_args()

    results = measure(args.repeat)
    baseline = json.loads(Path(args.check).read_text()) if args.check else {}
    unit = results["_calibration"]["seconds"]
    lines = [
        "## Performance smoke",
        "",
        "| Step | Time | Units | Baseline | Ratio |",
        "|---|---:|---:|---:|---:|",
    ]
    failures = []
    for name, row in results.items():
        if name.startswith("_"):
            continue
        base = baseline.get(name, {}).get("units")
        ratio = row["units"] / base if base else None
        slower_s = (row["units"] - base) * unit if base else 0.0
        bad = ratio is not None and ratio > args.tolerance and slower_s > ABS_SLACK_S
        if bad:
            failures.append(name)
        lines.append(
            f"| {name} | {row['seconds'] * 1000:.0f} ms | {row['units']:.2f} | "
            f"{base if base is None else f'{base:.2f}'} | {'-' if ratio is None else f'{ratio:.2f}x'}{' ❌' if bad else ''} |"
        )
    report = "\n".join(lines)
    print(report)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")
    if args.write:
        Path(args.write).write_text(
            json.dumps(
                {
                    k: {"units": round(v["units"], 3)}
                    for k, v in results.items()
                    if not k.startswith("_")
                },
                indent=2,
            )
            + "\n"
        )
    if failures:
        print(
            f"\nSlower than {args.tolerance}x the baseline: {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

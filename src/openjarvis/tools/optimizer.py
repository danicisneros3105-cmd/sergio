"""Performance Optimizer with profiling: measure, change, prove.

1. ``profile_script`` / ``profile_call`` run the code under cProfile and
   return the hotspots (own time and cumulative time per function).
2. ``optimize_function`` sends the hottest function's source plus the
   numbers to the model, which proposes a faster version.
3. The candidate is accepted only if it gives the SAME results as the
   original on the sample inputs and is measurably faster (median of
   several timed runs, both in fresh subprocesses). Otherwise the original
   stays. No speed-up is claimed without a measurement.
"""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm
from openjarvis.tools.code_generator import code_block

OPTIMIZE_PROMPT = """This Python function is a measured hotspot ({share:.0%} of run time).
Rewrite it to be faster while returning exactly the same results for every
input (same types, same order, same edge cases). Prefer better algorithms
and data structures over micro-tweaks. Keep the same name and signature.
Output only the function in one Python code block.

PROFILE:
{profile}

FUNCTION:
```python
{source}
```"""


@dataclass
class Hotspot:
    function: str
    file: str
    line: int
    calls: int
    own_s: float
    cumulative_s: float


def _hotspots(stats: pstats.Stats, top: int) -> list[Hotspot]:
    rows = []
    for (file, line, func), (cc, nc, tt, ct, _callers) in stats.stats.items():  # type: ignore[attr-defined]
        if file.startswith("<") or "cProfile" in file or "pstats" in file:
            continue
        rows.append(Hotspot(func, file, line, nc, round(tt, 6), round(ct, 6)))
    return sorted(rows, key=lambda h: -h.own_s)[:top]


def profile_call(
    fn: Callable[..., Any], *args: Any, top: int = 10, **kwargs: Any
) -> tuple[Any, list[Hotspot]]:
    prof = cProfile.Profile()
    result = prof.runcall(fn, *args, **kwargs)
    return result, _hotspots(pstats.Stats(prof, stream=io.StringIO()), top)


def profile_script(
    path: Path, args: list[str] | None = None, top: int = 10, timeout: float = 300.0
) -> list[Hotspot]:
    """Profile a script in a subprocess; hotspots in that script's own files first."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "prof.out"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "cProfile",
                "-o",
                str(out),
                str(path),
                *(args or []),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=path.parent,
        )
        if not out.exists():
            return []
        stats = pstats.Stats(str(out), stream=io.StringIO())
    spots = _hotspots(stats, top * 3)
    own = [h for h in spots if str(path.parent) in h.file]
    return (own + [h for h in spots if h not in own])[:top]


def format_profile(spots: list[Hotspot]) -> str:
    return "\n".join(
        f"{h.function} ({Path(h.file).name}:{h.line}) calls={h.calls} own={h.own_s:.4f}s "
        f"cum={h.cumulative_s:.4f}s"
        for h in spots
    )


_BENCH = """
import json, statistics, sys, time
{setup}
{source}
inputs = json.loads(sys.argv[1])
outs = [repr({name}(*a)) for a in inputs]
times = []
for _ in range({repeats}):
    t = time.perf_counter()
    for a in inputs:
        {name}(*a)
    times.append(time.perf_counter() - t)
print(json.dumps({{"outs": outs, "median": statistics.median(times)}}))
"""


def benchmark(
    source: str,
    name: str,
    inputs: list[list[Any]],
    *,
    setup: str = "",
    repeats: int = 5,
    timeout: float = 120.0,
) -> dict:
    """Run *name* from *source* on *inputs* in a fresh Python: outputs + median time."""
    script = _BENCH.format(
        setup=setup, source=textwrap.dedent(source), name=name, repeats=repeats
    )
    with tempfile.TemporaryDirectory() as tmp:
        file = Path(tmp) / "bench.py"
        file.write_text(script, "utf-8")
        proc = subprocess.run(
            [sys.executable, "-I", str(file), json.dumps(inputs)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmp,
        )
    if proc.returncode != 0:
        raise RuntimeError(
            (proc.stderr.strip().splitlines() or ["benchmark failed"])[-1]
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])


@dataclass
class Optimization:
    accepted: bool
    original: str
    candidate: str
    speedup: float
    same_results: bool
    reason: str
    before_s: float = 0.0
    after_s: float = 0.0
    profile: list[Hotspot] = field(default_factory=list)


def optimize_function(
    source: str,
    name: str,
    inputs: list[list[Any]],
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    setup: str = "",
    min_speedup: float = 1.1,
    profile: Optional[list[Hotspot]] = None,
    share: float = 1.0,
) -> Optimization:
    """Ask for a faster *name*; accept only if equal outputs and faster."""
    model = as_llm(llm)
    before = benchmark(source, name, inputs, setup=setup)
    candidate = code_block(
        model(
            OPTIMIZE_PROMPT.format(
                share=share,
                profile=format_profile(profile or [])
                or f"median {before['median']:.6f}s on the sample inputs",
                source=source,
            ),
            temperature=0.3,
        )
    )
    try:
        after = benchmark(candidate, name, inputs, setup=setup)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        return Optimization(
            False,
            source,
            candidate,
            0.0,
            False,
            f"candidate failed to run: {exc}",
            before["median"],
            0.0,
            profile or [],
        )
    same = after["outs"] == before["outs"]
    speedup = (
        before["median"] / after["median"] if after["median"] > 0 else float("inf")
    )
    if not same:
        reason = "rejected: different results"
    elif speedup < min_speedup:
        reason = f"rejected: only {speedup:.2f}x faster"
    else:
        reason = f"accepted: {speedup:.1f}x faster, same results"
    return Optimization(
        same and speedup >= min_speedup,
        source,
        candidate,
        round(speedup, 2),
        same,
        reason,
        before["median"],
        after["median"],
        profile or [],
    )


__all__ = [
    "Hotspot",
    "Optimization",
    "benchmark",
    "format_profile",
    "optimize_function",
    "profile_call",
    "profile_script",
]

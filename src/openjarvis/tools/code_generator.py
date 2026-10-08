"""TDD Code Generator: tests first, then code, then run until green.

1. From the specification the model writes pytest tests (the contract).
2. Then it writes the implementation, without seeing anything but the
   spec and the tests.
3. The tests run for real in a throwaway folder (isolated Python, timeout).
4. Failures (the exact pytest output) go back to the model, which fixes the
   implementation — never the tests — until everything passes or the round
   limit is hit. Tests that are themselves broken (a syntax error, an
   impossible assertion the model flags) are rewritten once.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm

TESTS_PROMPT = """Write pytest tests for this specification. Cover normal cases, edge
cases (empty, zero, negative, unicode, large) and errors the spec mentions.
Import the code with: from {module} import *
Output only one Python code block.

SPECIFICATION:
{spec}"""

CODE_PROMPT = """Write the Python module `{module}.py` that satisfies the specification
and passes these tests. Standard library only unless the spec says otherwise.
Output only one Python code block.

SPECIFICATION:
{spec}

TESTS:
```python
{tests}
```"""

FIX_PROMPT = """The module `{module}.py` fails its tests. Fix the MODULE (do not touch the
tests). Output only the full corrected module in one Python code block.

SPECIFICATION:
{spec}

MODULE:
```python
{code}
```

TESTS:
```python
{tests}
```

PYTEST OUTPUT:
{output}"""


def code_block(text: str, lang: str = "python") -> str:
    """The first fenced code block (or the whole text when there is none)."""
    match = re.search(rf"```(?:{lang}|py|[a-z+#]*)?\s*\n(.*?)```", text or "", re.S | re.I)
    return (match.group(1) if match else (text or "")).strip() + "\n"


@dataclass
class RunResult:
    ok: bool
    passed: int
    failed: int
    output: str


def run_pytest(code: str, tests: str, module: str = "solution", timeout: float = 60.0) -> RunResult:
    """Run *tests* against *code* in a fresh temp folder."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, f"{module}.py").write_text(code, "utf-8")
        Path(tmp, f"test_{module}.py").write_text(tests, "utf-8")
        try:
            proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider",
                                   f"test_{module}.py"], cwd=tmp, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return RunResult(False, 0, 0, f"tests timed out after {timeout:.0f} s (infinite loop?)")
    out = (proc.stdout + proc.stderr)[-6000:]
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) (?:failed|error)", out)) else (0 if proc.returncode == 0 else 1)
    return RunResult(proc.returncode == 0 and passed > 0, passed, failed, out)


@dataclass
class TDDResult:
    code: str
    tests: str
    ok: bool
    rounds: int
    last_run: RunResult
    history: list[dict] = field(default_factory=list)


def tdd(
    spec: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    module: str = "solution",
    tests: Optional[str] = None,
    max_rounds: int = 4,
) -> TDDResult:
    """Generate tests (unless given) and code for *spec*, iterating to green."""
    model = as_llm(llm)
    tests = tests or code_block(model(TESTS_PROMPT.format(spec=spec, module=module), temperature=0.3))
    code = code_block(model(CODE_PROMPT.format(spec=spec, module=module, tests=tests), temperature=0.2))
    history: list[dict] = []
    run = run_pytest(code, tests, module)
    for rnd in range(1, max_rounds + 1):
        history.append({"round": rnd, "passed": run.passed, "failed": run.failed})
        if run.ok:
            return TDDResult(code, tests, True, rnd, run, history)
        if rnd == max_rounds:
            break
        code = code_block(model(FIX_PROMPT.format(spec=spec, module=module, code=code, tests=tests,
                                                  output=run.output[-3500:]), temperature=0.2))
        run = run_pytest(code, tests, module)
    return TDDResult(code, tests, False, len(history), run, history)


__all__ = ["RunResult", "TDDResult", "code_block", "run_pytest", "tdd"]

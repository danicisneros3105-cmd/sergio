"""Smart Debugger with stack analysis.

``parse_traceback`` reads Python tracebacks (including chained ones) and
JavaScript/Node stack traces into frames. ``analyse`` finds the frame that
matters — the deepest one in *your* code, not in libraries — loads the
source around it, and adds what the exception usually means (a ``None``
that slipped through, an off-by-one index, a missing key, a wrong
signature). The model then gets the facts, not just the text, and returns
the root cause and a minimal fix. ``debug_run`` runs a command and does all
of this when it crashes.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, parse_json

_PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)$')
_PY_EXC = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Iteration|"
                     r"Stop\w*)|[A-Z]\w*Error)(?::\s*(?P<msg>.*))?$")
_JS_FRAME = re.compile(r"^\s*at (?:(?P<func>[^\s(]+) )?\(?(?P<file>[^\s():]+):(?P<line>\d+):(?P<col>\d+)\)?$")
_JS_EXC = re.compile(r"^(?P<type>\w*Error)(?::\s*(?P<msg>.*))?$")
LIBRARY_MARKERS = ("site-packages", "dist-packages", "/lib/python", "node_modules", "<frozen", "internal/")

HINTS: dict[str, str] = {
    "AttributeError: 'NoneType'": "A value is None where an object was expected: find which call returned None "
                                  "(a failed lookup, a function without return, an unset attribute).",
    "TypeError: 'NoneType'": "Something is None and is used as a list/function/number.",
    "KeyError": "The key is missing from the dict: check spelling, use .get() with a default, or why it was "
                "never set.",
    "IndexError": "An index is outside the sequence: often off-by-one, or an empty list.",
    "ZeroDivisionError": "A divisor is zero: guard the empty/zero case.",
    "ModuleNotFoundError": "The package is not installed in the Python that runs this, or the import path is wrong.",
    "ImportError": "The name does not exist in that module (renamed/removed) or there is a circular import.",
    "RecursionError": "A function calls itself without reaching a base case.",
    "TypeError: ": "A call has wrong argument types or count: compare the call with the function signature.",
    "ValueError": "A value has the right type but a bad content (parsing, unpacking, ranges).",
    "FileNotFoundError": "The path does not exist relative to the current working directory.",
    "UnicodeDecodeError": "A file is read with the wrong encoding: pass encoding='utf-8' (or the real one).",
    "TypeError: Cannot read propert": "JS: an object is undefined/null where a property is read.",
    "ReferenceError": "JS: a variable is used before it is defined or out of scope.",
}

DIAGNOSE_PROMPT = """You are debugging. Use the facts below; do not guess beyond them.

EXCEPTION: {exc}
WHERE IT MATTERS: {where}
CALL CHAIN (outer -> inner): {chain}
WHAT THIS ERROR USUALLY MEANS: {hint}

SOURCE AROUND THE FAILING LINE (>> marks it):
{source}

Reply with JSON only:
{{"root_cause": "<the real reason, one or two sentences>",
  "fix": "<what to change>",
  "patch": "<a minimal unified diff, or empty>",
  "confidence": <0-100>}}"""


@dataclass
class Frame:
    file: str
    line: int
    func: str
    code: str = ""

    @property
    def is_library(self) -> bool:
        return any(m in self.file for m in LIBRARY_MARKERS)


@dataclass
class StackTrace:
    language: str
    frames: list[Frame]
    exc_type: str
    message: str
    chained: list[str] = field(default_factory=list)  # earlier exceptions in a chain


def parse_traceback(text: str) -> Optional[StackTrace]:
    """Parse the LAST traceback in *text* (Python or JavaScript)."""
    lines = (text or "").splitlines()
    py_frames: list[Frame] = []
    exc_type = message = ""
    chained: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("Traceback (most recent call last)"):
            if exc_type:
                chained.append(f"{exc_type}: {message}")
            py_frames, exc_type, message = [], "", ""
            continue
        m = _PY_FRAME.match(line)
        if m:
            code = lines[i + 1].strip() if i + 1 < len(lines) and not _PY_FRAME.match(lines[i + 1]) else ""
            py_frames.append(Frame(m["file"], int(m["line"]), m["func"].strip(), code))
            continue
        e = _PY_EXC.match(line.strip())
        if e and py_frames and not line.startswith(" "):
            exc_type, message = e["type"], (e["msg"] or "").strip()
    if py_frames:
        return StackTrace("python", py_frames, exc_type or "Exception", message, chained)
    js_frames = [Frame(m["file"], int(m["line"]), (m["func"] or "<anonymous>")) for ln in lines
                 if (m := _JS_FRAME.match(ln))]
    if js_frames:
        exc = next((m for ln in lines if (m := _JS_EXC.match(ln.strip()))), None)
        # JS lists the innermost frame first; store outer -> inner like Python.
        return StackTrace("javascript", list(reversed(js_frames)), exc["type"] if exc else "Error",
                          (exc["msg"] or "").strip() if exc else "")
    return None


def culprit(trace: StackTrace) -> Frame:
    """The innermost frame in user code (else the innermost frame)."""
    for frame in reversed(trace.frames):
        if not frame.is_library:
            return frame
    return trace.frames[-1]


def source_context(frame: Frame, radius: int = 6, root: Optional[Path] = None) -> str:
    path = Path(frame.file)
    if not path.is_absolute() and root is not None:
        path = root / path
    try:
        src = path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return f"(source not available) {frame.line}: {frame.code}"
    lo, hi = max(1, frame.line - radius), min(len(src), frame.line + radius)
    return "\n".join(f"{'>>' if n == frame.line else '  '} {n:4d} | {src[n - 1]}" for n in range(lo, hi + 1))


def hint_for(trace: StackTrace) -> str:
    full = f"{trace.exc_type}: {trace.message}"
    for key, hint in HINTS.items():
        if full.startswith(key) or (key in full and len(key) > 12):
            return hint
    return "No standard pattern; reason from the code."


@dataclass
class Diagnosis:
    trace: StackTrace
    culprit: Frame
    hint: str
    root_cause: str = ""
    fix: str = ""
    patch: str = ""
    confidence: float = 0.0


def analyse(text: str, llm: "LLM | Callable[..., str] | None" = None, *, root: Optional[Path] = None) -> Diagnosis:
    trace = parse_traceback(text)
    if trace is None:
        raise ValueError("No Python or JavaScript stack trace found in the text.")
    frame = culprit(trace)
    diag = Diagnosis(trace, frame, hint_for(trace))
    if llm is None:
        return diag
    chain = " -> ".join(f"{Path(f.file).name}:{f.line} {f.func}" for f in trace.frames[-8:])
    data = parse_json(as_llm(llm)(DIAGNOSE_PROMPT.format(
        exc=f"{trace.exc_type}: {trace.message}" + (f" (after: {'; '.join(trace.chained)})" if trace.chained else ""),
        where=f"{frame.file}:{frame.line} in {frame.func}", chain=chain, hint=diag.hint,
        source=source_context(frame, root=root)), temperature=0.1))
    if isinstance(data, dict):
        diag.root_cause = str(data.get("root_cause") or "")
        diag.fix = str(data.get("fix") or "")
        diag.patch = str(data.get("patch") or "")
        try:
            diag.confidence = float(data.get("confidence") or 0) / 100
        except (TypeError, ValueError):
            diag.confidence = 0.0
    return diag


def debug_run(command: str, llm: "LLM | Callable[..., str] | None" = None, *, cwd: Optional[str] = None,
              timeout: float = 120.0) -> Optional[Diagnosis]:
    """Run *command*; when it fails with a stack trace, diagnose it (else None)."""
    proc = subprocess.run(shlex.split(command), cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode == 0:
        return None
    out = proc.stderr + "\n" + proc.stdout
    if parse_traceback(out) is None:
        return None
    return analyse(out, llm, root=Path(cwd) if cwd else None)


__all__ = ["Diagnosis", "Frame", "StackTrace", "analyse", "culprit", "debug_run", "hint_for", "parse_traceback",
           "source_context"]

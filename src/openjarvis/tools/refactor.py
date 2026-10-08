"""Safe Multi-File Refactor: all files change together, or none do.

* ``rename_symbol`` renames a Python identifier across a project using the
  tokenizer, so strings, comments and longer names that merely contain the
  word are left alone (``count`` does not touch ``account``).
* ``llm_refactor`` asks the model for whole-file rewrites following an
  instruction, limited to the files you name.
* ``apply_atomically`` writes every change, then verifies: each Python file
  must compile and, when given, the test command must pass. Any failure
  restores every file from its backup — the project is never left half
  refactored.
"""

from __future__ import annotations

import io
import shlex
import subprocess
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, parse_json

REFACTOR_PROMPT = """Refactor these files following the instruction. Change only what the
instruction needs; keep behaviour identical. Return the COMPLETE new content
of every file you change (omit files you leave as they are).

INSTRUCTION: {instruction}

{files}

Reply with JSON only: {{"files": [{{"path": "<same path as given>", "content": "<full new content>"}}],
"summary": "<what changed>"}}"""


def rename_in_source(text: str, old: str, new: str) -> tuple[str, int]:
    """Rename identifier tokens equal to *old* (never inside strings or comments)."""
    spots = [tok.start for tok in tokenize.generate_tokens(io.StringIO(text).readline)
             if tok.type == tokenize.NAME and tok.string == old]
    if not spots:
        return text, 0
    lines = text.splitlines(keepends=True)
    for row, col in sorted(spots, reverse=True):  # right to left keeps columns valid
        line = lines[row - 1]
        lines[row - 1] = line[:col] + new + line[col + len(old):]
    return "".join(lines), len(spots)


@dataclass
class Change:
    path: Path
    new_content: str


@dataclass
class RefactorResult:
    ok: bool
    changed: list[str]
    reason: str
    summary: str = ""
    test_output: str = ""
    renames: dict[str, int] = field(default_factory=dict)


def verify_python(paths: list[Path]) -> Optional[str]:
    for path in paths:
        if path.suffix == ".py":
            try:
                compile(path.read_text("utf-8"), str(path), "exec")
            except SyntaxError as exc:
                return f"{path}:{exc.lineno}: {exc.msg}"
    return None


def apply_atomically(changes: list[Change], *, test_cmd: str = "", cwd: Optional[Path] = None,
                     timeout: float = 600.0) -> RefactorResult:
    """Write all *changes*; roll every file back if compile or tests fail."""
    backups: dict[Path, Optional[str]] = {}
    for ch in changes:
        backups[ch.path] = ch.path.read_text("utf-8") if ch.path.exists() else None
    try:
        for ch in changes:
            ch.path.parent.mkdir(parents=True, exist_ok=True)
            ch.path.write_text(ch.new_content, "utf-8")
        problem = verify_python([c.path for c in changes])
        output = ""
        if problem is None and test_cmd:
            proc = subprocess.run(shlex.split(test_cmd), cwd=cwd, capture_output=True, text=True, timeout=timeout)
            output = (proc.stdout + proc.stderr)[-4000:]
            if proc.returncode != 0:
                problem = "tests failed after the change"
        if problem:
            raise RuntimeError(problem)
        return RefactorResult(True, [str(c.path) for c in changes], "applied and verified", test_output=output)
    except Exception as exc:  # noqa: BLE001 — any failure means roll back
        for path, old in backups.items():
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(old, "utf-8")
        return RefactorResult(False, [], f"rolled back: {exc}",
                              test_output=locals().get("output", "") or "")


def rename_symbol(root: Path, old: str, new: str, *, files: Optional[list[Path]] = None, test_cmd: str = "") -> RefactorResult:
    """Rename identifier *old* to *new* in every Python file under *root*."""
    if not new.isidentifier():
        return RefactorResult(False, [], f"'{new}' is not a valid identifier")
    targets = files or [p for p in root.rglob("*.py") if ".venv" not in p.parts and "node_modules" not in p.parts]
    changes, counts = [], {}
    for path in targets:
        text = path.read_text("utf-8")
        new_text, n = rename_in_source(text, old, new)
        if n:
            changes.append(Change(path, new_text))
            counts[str(path)] = n
    if not changes:
        return RefactorResult(False, [], f"'{old}' not found")
    result = apply_atomically(changes, test_cmd=test_cmd, cwd=root)
    result.renames = counts if result.ok else {}
    return result


def llm_refactor(instruction: str, files: list[Path], llm: "LLM | Callable[..., str] | None" = None, *,
                 test_cmd: str = "", cwd: Optional[Path] = None) -> RefactorResult:
    """Let the model rewrite *files* per *instruction*, applied atomically."""
    model = as_llm(llm)
    listing = "\n\n".join(f"FILE {p}:\n```\n{p.read_text('utf-8')}\n```" for p in files)
    data = parse_json(model(REFACTOR_PROMPT.format(instruction=instruction, files=listing), temperature=0.2))
    allowed = {str(p): p for p in files}
    changes = []
    for item in (data or {}).get("files", []) if isinstance(data, dict) else []:
        path = allowed.get(str(item.get("path") or ""))
        if path is not None and isinstance(item.get("content"), str):
            changes.append(Change(path, item["content"]))
    if not changes:
        return RefactorResult(False, [], "the model proposed no usable changes")
    result = apply_atomically(changes, test_cmd=test_cmd, cwd=cwd)
    result.summary = str((data or {}).get("summary") or "") if isinstance(data, dict) else ""
    return result


__all__ = ["Change", "RefactorResult", "apply_atomically", "llm_refactor", "rename_in_source", "rename_symbol",
           ]

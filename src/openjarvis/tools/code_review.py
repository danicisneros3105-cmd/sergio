"""Automatic Code Review: hard checks first, then a focused model review.

Static pass (no model, exact): ruff when available, plus AST checks for the
bugs that matter in practice — bare ``except``, mutable default arguments,
``eval``/``exec``, ``subprocess`` with ``shell=True``, ``assert`` used for
validation, hard-coded secrets, comparisons to ``None`` with ``==``, very
long functions, unreachable code after ``return``.

Model pass: the diff (or file) plus the static findings go to a reviewer
prompt that looks only for real defects (logic, edge cases, error handling,
security, concurrency) and must cite a line. Findings are merged,
de-duplicated and ranked by severity.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, parse_json

SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_SECRET = re.compile(
    r"""(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['"][^'"\s]{12,}['"]"""
)
_KEYLIKE = re.compile(
    r"\b(AIza[0-9A-Za-z_\-]{30,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b"
)

REVIEW_PROMPT = """Review this code change like a senior engineer. Report only REAL
defects a user or caller would hit: wrong logic, unhandled edge cases (empty,
None, zero, unicode, concurrency), broken error handling, security holes,
resource leaks, API misuse. No style nits. Each finding must cite a line.

Static analysis already found:
{static}

CODE ({name}):
{code}

Reply with JSON only:
{{"findings": [{{"line": <n>, "severity": "critical|high|medium|low", "title": "<short>",
  "why": "<the failure scenario>", "fix": "<concrete fix>"}}]}}"""


@dataclass
class Finding:
    file: str
    line: int
    severity: str
    title: str
    why: str = ""
    fix: str = ""
    source: str = "static"


class _Visitor(ast.NodeVisitor):
    def __init__(self, file: str) -> None:
        self.file = file
        self.found: list[Finding] = []

    def add(self, node: ast.AST, severity: str, title: str, why: str, fix: str) -> None:
        self.found.append(
            Finding(self.file, getattr(node, "lineno", 0), severity, title, why, fix)
        )

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.add(
                node,
                "medium",
                "bare except",
                "catches KeyboardInterrupt/SystemExit and hides bugs",
                "catch Exception (or the specific error)",
            )
        self.generic_visit(node)

    def _func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for default in node.args.defaults + [
            d for d in node.args.kw_defaults if d is not None
        ]:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.add(
                    default,
                    "high",
                    f"mutable default argument in {node.name}()",
                    "the same object is shared between calls",
                    "use None and create it inside",
                )
        length = (node.end_lineno or node.lineno) - node.lineno
        if length > 120:
            self.add(
                node,
                "low",
                f"{node.name}() is {length} lines long",
                "hard to test and review",
                "split into smaller functions",
            )
        body = node.body
        for i, stmt in enumerate(body[:-1]):
            if isinstance(stmt, (ast.Return, ast.Raise)):
                self.add(
                    body[i + 1],
                    "medium",
                    "unreachable code",
                    "statements after return/raise never run",
                    "remove or move it",
                )
                break
        self.generic_visit(node)

    visit_FunctionDef = _func
    visit_AsyncFunctionDef = _func

    def visit_Call(self, node: ast.Call) -> None:
        name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else getattr(node.func, "attr", "")
        )
        if name in ("eval", "exec"):
            self.add(
                node,
                "high",
                f"{name}() on dynamic input",
                "runs arbitrary code",
                "parse safely (ast.literal_eval, json)",
            )
        if name in ("run", "call", "Popen", "check_output", "check_call") and any(
            kw.arg == "shell"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
            for kw in node.keywords
        ):
            self.add(
                node,
                "high",
                "subprocess with shell=True",
                "shell injection if any part comes from input",
                "pass a list of arguments without shell=True",
            )
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for op, comp in zip(node.ops, node.comparators):
            if (
                isinstance(op, (ast.Eq, ast.NotEq))
                and isinstance(comp, ast.Constant)
                and comp.value is None
            ):
                self.add(
                    node,
                    "low",
                    "comparison to None with ==",
                    "objects can override __eq__",
                    "use `is None`",
                )
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.add(
            node,
            "low",
            "assert used for a runtime check",
            "asserts vanish with python -O",
            "raise a proper exception",
        )
        self.generic_visit(node)


class _TestVisitor(_Visitor):
    """In tests, asserts are the point."""

    def visit_Assert(self, node: ast.Assert) -> None:
        self.generic_visit(node)


def static_review(path: Path, text: Optional[str] = None) -> list[Finding]:
    text = text if text is not None else path.read_text("utf-8", errors="replace")
    found: list[Finding] = []
    for n, line in enumerate(text.splitlines(), 1):
        if _SECRET.search(line) or _KEYLIKE.search(line):
            found.append(
                Finding(
                    str(path),
                    n,
                    "critical",
                    "hard-coded secret",
                    "anyone with the code has the key",
                    "load it from the environment or a vault",
                )
            )
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            return found + [
                Finding(
                    str(path),
                    exc.lineno or 0,
                    "critical",
                    "syntax error",
                    str(exc.msg),
                    "fix the syntax",
                )
            ]
        visitor = (_TestVisitor if path.name.startswith("test_") else _Visitor)(
            str(path)
        )
        visitor.visit(tree)
        found += visitor.found
        found += _ruff(path)
    return found


def _ruff(path: Path) -> list[Finding]:
    exe = shutil.which("ruff")
    if not exe:
        return []
    try:
        out = subprocess.run(
            [
                exe,
                "check",
                "--output-format",
                "json",
                "--select",
                "F,E9,B",
                "--quiet",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        items = json.loads(out.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return [
        Finding(
            str(path),
            (i.get("location") or {}).get("row", 0),
            "medium" if str(i.get("code", "")).startswith(("F8", "B")) else "low",
            f"{i.get('code')}: {i.get('message')}",
            source="ruff",
        )
        for i in items
    ]


def git_diff(repo: Path, base: str = "HEAD") -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "diff", base, "--unified=5"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return out.stdout


def review(
    paths: list[Path],
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    diff: str = "",
    max_chars: int = 24000,
) -> list[Finding]:
    """Static findings for *paths*, plus model findings for the diff or files."""
    findings: list[Finding] = []
    for path in paths:
        if path.is_file():
            findings += static_review(path)
    if llm is not None:
        model = as_llm(llm)
        static = (
            "\n".join(
                f"- {Path(f.file).name}:{f.line} {f.title}" for f in findings[:40]
            )
            or "- nothing"
        )
        units = (
            [("diff", diff)]
            if diff
            else [(str(p), _numbered(p)) for p in paths if p.is_file()]
        )
        for name, code in units:
            data = parse_json(
                model(
                    REVIEW_PROMPT.format(
                        static=static, name=name, code=code[:max_chars]
                    ),
                    temperature=0.1,
                )
            )
            for item in (
                (data or {}).get("findings", []) if isinstance(data, dict) else []
            ):
                if not isinstance(item, dict) or not item.get("title"):
                    continue
                sev = str(item.get("severity") or "medium").lower()
                findings.append(
                    Finding(
                        name,
                        int(item.get("line") or 0),
                        sev if sev in SEVERITY else "medium",
                        str(item["title"]),
                        str(item.get("why") or ""),
                        str(item.get("fix") or ""),
                        "model",
                    )
                )
    seen: set[tuple[str, int, str]] = set()
    unique = []
    for f in sorted(
        findings, key=lambda f: (SEVERITY.get(f.severity, 5), f.file, f.line)
    ):
        key = (f.file, f.line, f.title.lower()[:40])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _numbered(path: Path) -> str:
    return "\n".join(
        f"{n:4d} {line}"
        for n, line in enumerate(
            path.read_text("utf-8", errors="replace").splitlines(), 1
        )
    )


def as_dicts(findings: list[Finding]) -> list[dict]:
    return [asdict(f) for f in findings]


__all__ = ["Finding", "as_dicts", "git_diff", "review", "static_review"]

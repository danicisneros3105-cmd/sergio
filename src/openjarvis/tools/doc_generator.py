"""Documentation Generator with drift detection.

Generation: every public function/class without a docstring gets one written
by the model from its signature and body; ``api_markdown`` renders the
module's API (signatures + first docstring line) as Markdown.

Drift detection (exact, no model): docs that no longer match the code —
* a docstring documents a parameter the function no longer has, or misses
  one it does have (Google ``Args:``, NumPy ``Parameters``, Sphinx ``:param``);
* a docstring promises a return value for a function that never returns one;
* Markdown docs mention ``name()`` / ``module.name`` that no longer exist.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from openjarvis.intelligence._llm import LLM, as_llm

DOCSTRING_PROMPT = """Write a concise Google-style docstring for this Python {kind}.
First line: what it does. Then Args (every parameter), Returns (if it returns
something) and Raises (if it raises). Output only the docstring text, no quotes.

```python
{source}
```"""

_GOOGLE_ARGS = re.compile(r"^\s*(?:Args|Arguments|Parameters|Params)\s*:?\s*$", re.M)
_NUMPY_RULE = re.compile(r"^\s*-{3,}\s*$")
_SPHINX = re.compile(r":param\s+(?:[\w\[\], ]+\s+)?(\w+)\s*:")


@dataclass
class Drift:
    file: str
    line: int
    name: str
    problem: str


def documented_params(doc: str) -> Optional[set[str]]:
    """Parameter names a docstring documents (None when it has no param section)."""
    names = set(_SPHINX.findall(doc))
    lines = doc.splitlines()
    for i, line in enumerate(lines):
        if _GOOGLE_ARGS.match(line):
            j = i + 1
            if j < len(lines) and _NUMPY_RULE.match(lines[j]):
                j += 1  # NumPy style: "Parameters" then "----------"
            base = None
            while j < len(lines):
                cur = lines[j]
                j += 1
                if not cur.strip():
                    continue
                indent = len(cur) - len(cur.lstrip())
                if base is None:
                    base = indent
                if indent < base or re.match(r"^\s*(Returns|Yields|Raises|Examples?|Notes?|Attributes)\s*:?\s*$", cur):
                    break
                if indent == base and (m := re.match(r"^\s*\*{0,2}(\w+)", cur)):
                    names.add(m.group(1))
            break
    if not names and not _GOOGLE_ARGS.search(doc):
        return None
    return names


def _params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    a = node.args
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)
    return {n for n in names if n not in ("self", "cls")}


def _returns_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Return,)) and sub.value is not None and not (
                isinstance(sub.value, ast.Constant) and sub.value.value is None):
            return True
        if isinstance(sub, (ast.Yield, ast.YieldFrom)):
            return True
    return False


def docstring_drift(path: Path, text: Optional[str] = None) -> list[Drift]:
    text = text if text is not None else path.read_text("utf-8")
    drifts: list[Drift] = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ""
        if not doc:
            continue
        documented = documented_params(doc)
        if documented is not None:
            actual = _params(node)
            for gone in sorted(documented - actual):
                drifts.append(Drift(str(path), node.lineno, node.name, f"documents parameter '{gone}' that no longer exists"))
            for missing in sorted(actual - documented):
                drifts.append(Drift(str(path), node.lineno, node.name, f"parameter '{missing}' is not documented"))
        if re.search(r"^\s*Returns?\s*:?\s*$", doc, re.M) and not _returns_value(node) and node.name != "__init__":
            drifts.append(Drift(str(path), node.lineno, node.name, "documents a return value but returns nothing"))
    return drifts


def defined_names(sources: Iterable[Path]) -> set[str]:
    names: set[str] = set()
    for src in sources:
        try:
            tree = ast.parse(src.read_text("utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        names.add(src.stem)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


_DOC_REF = re.compile(r"`(?:[\w.]+\.)?([A-Za-z_]\w*)\(\)?`")


def markdown_drift(doc: Path, sources: Iterable[Path]) -> list[Drift]:
    """Inline-code references like `name()` in *doc* that the code no longer defines."""
    names = defined_names(sources)
    drifts = []
    for n, line in enumerate(doc.read_text("utf-8").splitlines(), 1):
        for ref in _DOC_REF.findall(line):
            if ref not in names and not ref.startswith("_") and len(ref) > 2 and ref not in dir(__builtins__):
                if "(" in line[line.find(ref):line.find(ref) + len(ref) + 2]:
                    drifts.append(Drift(str(doc), n, ref, f"mentions {ref}() which is not defined in the code"))
    return drifts


def missing_docstrings(text: str) -> list[ast.AST]:
    out = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            if not ast.get_docstring(node):
                out.append(node)
    return out


def add_docstrings(text: str, llm: "LLM | Callable[..., str] | None" = None, limit: int = 30) -> tuple[str, int]:
    """Insert model-written docstrings into undocumented public defs (returns new text, count)."""
    model = as_llm(llm)
    lines = text.splitlines()
    nodes = sorted(missing_docstrings(text), key=lambda n: -n.lineno)[:limit]  # bottom-up keeps line numbers valid
    added = 0
    for node in nodes:
        src = ast.get_source_segment(text, node) or ""
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        doc = model(DOCSTRING_PROMPT.format(kind=kind, source=src[:4000]), temperature=0.2).strip().strip('"').strip("'")
        doc = re.sub(r"^```\w*|```$", "", doc).strip()
        if not doc:
            continue
        body_line = node.body[0].lineno - 1
        indent = " " * (len(lines[body_line]) - len(lines[body_line].lstrip()))
        block = [f'{indent}"""{doc.splitlines()[0]}'] + [f"{indent}{ln}" if ln.strip() else "" for ln in doc.splitlines()[1:]]
        block[-1] += '"""' if len(block) > 1 else ""
        if len(block) == 1:
            block[0] += '"""'
        lines[body_line:body_line] = block
        added += 1
    new = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    ast.parse(new)  # never write broken code
    return new, added


def api_markdown(path: Path) -> str:
    tree = ast.parse(path.read_text("utf-8"))
    out = [f"# `{path.stem}`", ""]
    if (doc := ast.get_docstring(tree)):
        out += [doc.splitlines()[0], ""]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            sig = f"class {node.name}" if isinstance(node, ast.ClassDef) else f"{node.name}({ast.unparse(node.args)})"
            first = (ast.get_docstring(node) or "").splitlines()[:1]
            out += [f"## `{sig}`", "", first[0] if first else "_Undocumented._", ""]
    return "\n".join(out)


__all__ = ["Drift", "add_docstrings", "api_markdown", "docstring_drift", "documented_params", "markdown_drift",
           "missing_docstrings"]

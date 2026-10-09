"""Every module that defines public functions or classes declares ``__all__``,
and every name it lists is defined there (or provided by a module-level
``__getattr__`` for lazy imports)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "src" / "openjarvis"
MODULES = sorted(p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _bound(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
    return names


def _declared(tree: ast.Module) -> list[str] | None:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                try:
                    return list(ast.literal_eval(node.value))
                except ValueError:
                    return []  # computed __all__: trust it
    return None


@pytest.mark.parametrize("path", MODULES, ids=lambda p: str(p.relative_to(ROOT)))
def test_public_api_is_declared(path: Path) -> None:
    tree = ast.parse(path.read_text("utf-8"))
    public = [
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not n.name.startswith("_")
    ]
    declared = _declared(tree)
    if public:
        assert declared is not None, f"add __all__ (public: {public[:5]})"
    if not declared:
        return
    lazy = any(
        isinstance(n, ast.FunctionDef) and n.name == "__getattr__" for n in tree.body
    )
    if lazy:
        return
    missing = sorted(set(declared) - _bound(tree))
    assert not missing, f"__all__ lists undefined names: {missing}"

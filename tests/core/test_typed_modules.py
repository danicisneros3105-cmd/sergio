"""Modules that must stay fully type-annotated (every argument and return)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "src" / "openjarvis"
TYPED = [
    "agents/hybrid/toolorchestra.py",
    "agents/hybrid/conductor.py",
    "server/agent_manager_routes.py",
    "engine/cloud.py",
    "_native_fallback.py",
    "i18n/__init__.py",
]


@pytest.mark.parametrize("relative", TYPED)
def test_every_function_is_annotated(relative):
    tree = ast.parse((ROOT / relative).read_text("utf-8"))
    missing = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        params = args.posonlyargs + args.args + args.kwonlyargs
        unannotated = [
            a.arg
            for a in params
            if a.annotation is None and a.arg not in ("self", "cls")
        ]
        for extra in (args.vararg, args.kwarg):
            if extra is not None and extra.annotation is None:
                unannotated.append(extra.arg)
        if node.returns is None or unannotated:
            missing.append(f"{node.lineno} {node.name} {unannotated or '-> ?'}")
    assert not missing, f"{relative}:\n" + "\n".join(missing)

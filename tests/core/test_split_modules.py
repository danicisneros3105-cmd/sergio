"""Modules split out of big files look helpers up on the original module
(``import openjarvis.engine.cloud as _cloud`` then ``_cloud.name``). Every
such name must still exist there; a lint auto-fix that drops an "unused"
import would otherwise break a code path only a live cloud call reaches."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "src" / "openjarvis"
SPLIT = [
    "engine/cloud_anthropic.py",
    "engine/cloud_compat.py",
    "engine/cloud_google.py",
    "engine/cloud_openai.py",
    "agents/hybrid/toolorchestra_rl.py",
    "agents/hybrid/_base_sdk.py",
    "agents/hybrid/mini_swe_cloud_loops.py",
]


@pytest.mark.parametrize("relative", SPLIT)
def test_every_looked_up_name_exists(relative):
    tree = ast.parse((ROOT / relative).read_text("utf-8"))
    aliases = {
        a.asname: a.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for a in node.names
        if a.asname
    }
    assert aliases, "split module should import its origin under an alias"
    missing = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            module = importlib.import_module(aliases[node.value.id])
            if not hasattr(module, node.attr):
                missing.append(f"line {node.lineno}: {node.value.id}.{node.attr}")
    assert not missing, "\n".join(missing)

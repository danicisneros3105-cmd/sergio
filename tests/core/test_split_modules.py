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
    "server/agent_manager_stream.py",
    "server/routes_stream.py",
    "core/config_toml.py",
    "core/config_hardware.py",
    "evals/cli_builders.py",
    "evals/cli_runs.py",
    "evals/core/runner_modes.py",
    "evals/core/runner_summary.py",
    "evals/core/runner_stats.py",
    "server/agent_manager_helpers.py",
    "server/agent_manager_channels.py",
    "server/agent_manager_tools.py",
    "server/api_memory_routes.py",
    "server/api_ws_routes.py",
    "server/api_speech_routes.py",
    "server/routes_admin.py",
    "server/vision_blender_routes.py",
    "security/data_boundary_settings.py",
    "security/data_boundary_exposure.py",
    "agents/hybrid/mini_swe_local_loop.py",
    "faces/book_identify.py",
    "faces/book_tidy.py",
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

"""The exported API description builds and documents the main endpoints."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="openjarvis[server] not installed")

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_openapi.py"


def _module():
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_spec_documents_the_public_endpoints(tmp_path):
    module = _module()
    out = tmp_path / "openapi.json"
    assert module.main(["--out", str(out)]) == 0
    spec = json.loads(out.read_text("utf-8"))
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "Sergio API"
    for path in (
        "/v1/chat/completions",
        "/v1/models",
        "/v1/embeddings",
        "/v1/cowork",
        "/v1/cowork/{run_id}/decision",
        "/v1/evolve/think/stream",
    ):
        assert path in spec["paths"], path
    assert module.main(["--check", "--out", str(out)]) == 0
    out.write_text("{}", "utf-8")
    assert module.main(["--check", "--out", str(out)]) == 1


def test_committed_spec_lists_the_same_core_paths():
    committed = json.loads(
        (SCRIPT.parents[1] / "docs" / "api" / "openapi.json").read_text("utf-8")
    )
    assert "/v1/chat/completions" in committed["paths"]
    assert "/v1/cowork" in committed["paths"]

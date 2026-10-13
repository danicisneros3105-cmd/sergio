"""Extensiones: plugins install only after the owner accepts their permissions."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server import hub_routes


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    app = FastAPI()
    app.include_router(hub_routes.router)
    return TestClient(app)


def test_lists_catalog_plugins_and_skills(client):
    data = client.get("/v1/hub").json()
    names = {p["name"] for p in data["plugins"]}
    assert {"frase-del-dia", "tipo-de-cambio"} <= names
    assert all(not p["installed"] for p in data["plugins"])
    assert isinstance(data["skills"], list)


def test_permissions_must_be_accepted(client):
    r = client.post("/v1/hub/plugins/tipo-de-cambio/install", json={})
    assert r.status_code == 409
    assert client.post("/v1/hub/plugins/nada/install", json={}).status_code == 404


def test_install_toggle_uninstall(client):
    r = client.post("/v1/hub/plugins/frase-del-dia/install", json={})
    assert r.status_code == 200, r.text
    row = next(
        p
        for p in client.get("/v1/hub").json()["plugins"]
        if p["name"] == "frase-del-dia"
    )
    assert row["installed"] and row["enabled"]
    assert client.post(
        "/v1/hub/plugins/frase-del-dia/enabled", json={"enabled": False}
    ).json() == {
        "name": "frase-del-dia",
        "enabled": False,
    }
    assert client.delete("/v1/hub/plugins/frase-del-dia").status_code == 200
    assert client.delete("/v1/hub/plugins/frase-del-dia").status_code == 404

"""The person and their Sergio (personal.py, server/personal_routes.py)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis import personal


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    from openjarvis.server.personal_routes import router

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)


def test_the_owner_default_is_senor_and_adds_nothing(tmp_path):
    p = personal.load(tmp_path)
    assert p["trato"] == "señor"
    assert personal.address_line(p) == ""


@pytest.mark.parametrize(
    "trato, name, must, must_not",
    [
        ("señora", "", "«señora»", None),
        ("nombre", "Ana", "«Ana»", None),
        ("neutro", "Alex", "neutro", None),
        ("tu", "Sam", "tuteas", None),
    ],
)
def test_every_way_of_being_addressed(tmp_path, trato, name, must, must_not):
    p = personal.save({"trato": trato, "nombre": name}, tmp_path)
    line = personal.address_line(p)
    assert must in line and line.startswith("Trato:")


def test_an_unknown_address_is_refused(tmp_path):
    with pytest.raises(ValueError):
        personal.save({"trato": "majestad"}, tmp_path)


def test_a_switched_off_skill_never_reaches_the_model(tmp_path):
    personal.save({"habilidades_apagadas": ["video"]}, tmp_path)
    blocked = personal.blocked_tools(personal.load(tmp_path))
    assert "video_essay" in blocked or "video_edit" in blocked


def test_routes(client):
    assert client.get("/v1/personal/perfil").json()["trato"] == "señor"
    r = client.put(
        "/v1/personal/perfil", json={"trato": "nombre", "nombre": "  Ana  María "}
    )
    assert r.json()["nombre"] == "Ana María"
    assert client.put("/v1/personal/perfil", json={"trato": "rey"}).status_code == 400
    skills = client.get("/v1/personal/habilidades").json()["habilidades"]
    assert any(s["clave"] == "web" and s["activa"] for s in skills)
    off = client.put("/v1/personal/habilidades/web", json={"activa": False}).json()
    assert not next(s for s in off["habilidades"] if s["clave"] == "web")["activa"]
    assert (
        client.put("/v1/personal/habilidades/volar", json={"activa": True}).status_code
        == 404
    )
    models = client.get("/v1/personal/modelos").json()
    assert models["modelos"][0]["id"].startswith("gemini-")
    assert [e["id"] for e in models["esfuerzos"]] == ["auto", "low", "medium", "high"]
    assert client.get("/v1/personal/en-marcha").json() == {"en_marcha": []}

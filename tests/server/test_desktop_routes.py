"""Health and Profile pages read from Sergio Escritorio's local API."""

from __future__ import annotations

import httpx
import pytest

pytest.importorskip("fastapi", reason="openjarvis[server] not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server import desktop_routes  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_routes, "get_config_dir", lambda: tmp_path)
    app = FastAPI()
    app.include_router(desktop_routes.router)
    return TestClient(app)


def _fake_desktop(monkeypatch, handler):
    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "t0k")
    monkeypatch.setenv("SERGIO_DESKTOP_URL", "http://desk.test")
    real = httpx.post

    def post(url, **kw):
        assert kw["headers"]["Authorization"] == "Bearer t0k"
        return handler(url, kw["json"])

    monkeypatch.setattr(httpx, "post", post)
    return real


def test_profile_comes_from_the_desktop(monkeypatch, client):
    def handler(url, body):
        assert url == "http://desk.test/skill"
        result = {
            "profile_summary": {
                "text": "Le gusta el 3D.",
                "updates": 4,
                "traits": ["rinde mejor por la mañana"],
            },
        }[body["name"]]
        return httpx.Response(200, json={"ok": True, "result": result})

    _fake_desktop(monkeypatch, handler)
    out = client.get("/v1/desktop/profile").json()
    assert out["companion"] is True and out["updates"] == 4
    assert out["traits"] == ["rinde mejor por la mañana"]


def test_profile_with_the_pc_app_closed_says_so_and_invents_nothing(
    monkeypatch, client
):
    monkeypatch.delenv("SERGIO_DESKTOP_TOKEN", raising=False)
    res = client.get("/v1/desktop/profile")
    assert res.status_code == 200
    out = res.json()
    assert out["companion"] is False and out["text"] == "" and out["updates"] == 0
    assert "Escritorio" in out["message"]
    assert not {"goals", "facts", "traits"} & set(
        out
    )  # nothing made up about the owner


def test_health_shows_only_what_the_owner_entered(client):
    first = client.get("/v1/desktop/health").json()
    assert (
        first["entered"] == {}
        and first["sleep"] == "Sin datos"
        and first["gym"] == "Sin sesiones"
    )
    client.post(
        "/v1/desktop/health/log",
        json={"category": "sleep", "payload": {"total_hours": 6.5}},
    )
    after = client.get("/v1/desktop/health").json()
    assert "sleep" in after["entered"] and after["sleep"] == "6.5 h"
    assert after["vitals"] == "Sin datos"  # still nothing about the heart


def test_the_coach_does_not_quote_numbers_it_was_never_given(monkeypatch, client):
    import openjarvis.engine._discovery as discovery

    monkeypatch.setattr(discovery, "get_engine", lambda cfg: None)
    quiet = client.post(
        "/v1/desktop/health/coach-ai", json={"message": "¿Cómo voy?"}
    ).json()
    assert "Todavía no tengo datos" in quiet["reply"]
    client.post(
        "/v1/desktop/health/log",
        json={"category": "sleep", "payload": {"total_hours": 6.5}},
    )
    known = client.post(
        "/v1/desktop/health/coach-ai", json={"message": "¿Cómo voy?"}
    ).json()
    assert "sueño 6.5 h" in known["reply"] and "VFC" not in known["reply"]


def test_sticky_notes_remember_where_they_were_moved(client):
    note = {
        "id": "n1",
        "title": "Compras",
        "content": "leche",
        "color": "mint",
        "x": 120,
        "y": 90,
    }
    assert client.post("/v1/desktop/sticky-notes", json=note).status_code == 200
    client.post("/v1/desktop/sticky-notes", json={**note, "x": 640, "y": 300})
    moved = [
        n
        for n in client.get("/v1/desktop/sticky-notes").json()["notes"]
        if n["id"] == "n1"
    ]
    assert (moved[0]["x"], moved[0]["y"]) == (640, 300)
    assert client.delete("/v1/desktop/sticky-notes/n1").json()["ok"] is True


def test_open_only_known_sections(monkeypatch, client):
    seen = []

    def handler(url, body):
        seen.append(body)
        return httpx.Response(200, json={"ok": True, "result": "ok"})

    _fake_desktop(monkeypatch, handler)
    assert client.post("/v1/desktop/open", json={"section": "gym"}).json() == {
        "ok": True,
        "companion": True,
    }
    assert seen == [{"name": "open_section", "args": {"section": "gym"}}]
    assert (
        client.post("/v1/desktop/open", json={"section": "rm -rf"}).status_code == 400
    )


def test_open_with_the_pc_app_closed_says_so(monkeypatch, client):
    monkeypatch.delenv("SERGIO_DESKTOP_TOKEN", raising=False)
    out = client.post("/v1/desktop/open", json={"section": "faces"}).json()
    assert out["ok"] is True and out["companion"] is False

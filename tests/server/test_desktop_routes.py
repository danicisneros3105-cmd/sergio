"""Health and Profile pages read from Sergio Escritorio's local API."""

from __future__ import annotations

import httpx
import pytest

pytest.importorskip("fastapi", reason="openjarvis[server] not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server import desktop_routes  # noqa: E402


@pytest.fixture()
def client():
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


def test_health_and_profile_come_from_the_desktop(monkeypatch, client):
    def handler(url, body):
        assert url == "http://desk.test/skill"
        result = {
            "health_summary": {"text": "IMC 23.1 (normal)", "metrics": {"imc": 23.1}},
            "profile_summary": {"text": "Le gusta el 3D.", "updates": 4},
        }[body["name"]]
        return httpx.Response(200, json={"ok": True, "result": result})

    _fake_desktop(monkeypatch, handler)
    assert client.get("/v1/desktop/health").json()["metrics"] == {"imc": 23.1}
    assert client.get("/v1/desktop/profile").json()["updates"] == 4


def test_open_only_known_sections(monkeypatch, client):
    seen = []

    def handler(url, body):
        seen.append(body)
        return httpx.Response(200, json={"ok": True, "result": "ok"})

    _fake_desktop(monkeypatch, handler)
    assert client.post("/v1/desktop/open", json={"section": "gym"}).json() == {
        "ok": True
    }
    assert seen == [{"name": "open_section", "args": {"section": "gym"}}]
    assert (
        client.post("/v1/desktop/open", json={"section": "rm -rf"}).status_code == 400
    )


def test_desktop_off_or_old_is_explained(monkeypatch, client):
    monkeypatch.delenv("SERGIO_DESKTOP_TOKEN", raising=False)
    off = client.get("/v1/desktop/health")
    assert off.status_code == 503 and "no responde" in off.json()["detail"]
    _fake_desktop(
        monkeypatch,
        lambda url, body: httpx.Response(
            404, json={"ok": False, "error": "unknown skill"}
        ),
    )
    old = client.get("/v1/desktop/profile")
    assert old.status_code == 501 and "Actualice" in old.json()["detail"]

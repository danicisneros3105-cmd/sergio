"""Conectar la IA con un clic (OpenRouter PKCE): sin pegar claves."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server import conectar_routes as C


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(C.router)
    return TestClient(app)


def test_start_gives_the_openrouter_page_with_a_pkce_challenge():
    url = _client().get("/v1/conectar/openrouter?vuelta=/chat").json()["url"]
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://openrouter.ai/auth?")
    assert q["code_challenge_method"] == ["S256"] and len(q["code_challenge"][0]) >= 43
    assert "/v1/conectar/openrouter/vuelta?state=" in q["callback_url"][0]


def test_back_saves_the_key_and_returns_to_the_app(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        C, "exchange", lambda code, verifier, http=None: "sk-or-v1-test"
    )
    import openjarvis.accounts.autoconfig as A

    monkeypatch.setattr(A, "_save_env", lambda k, v: saved.update({k: v}))
    client = _client()
    url = client.get("/v1/conectar/openrouter?vuelta=/chat").json()["url"]
    callback = parse_qs(urlparse(url).query)["callback_url"][0]
    state = parse_qs(urlparse(callback).query)["state"][0]
    r = client.get(
        f"/v1/conectar/openrouter/vuelta?state={state}&code=abc", follow_redirects=False
    )
    assert r.status_code == 303 and r.headers["location"] == "/chat?ia=conectada"
    assert saved == {"OPENROUTER_API_KEY": "sk-or-v1-test"}
    # the same code cannot be used twice
    again = client.get(
        f"/v1/conectar/openrouter/vuelta?state={state}&code=abc", follow_redirects=False
    )
    assert "ia=caducado" in again.headers["location"]


def test_exchange_sends_the_verifier_and_reads_the_key():
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"key": "sk-or-v1-abc"}

    class Http:
        def post(self, url, json):
            assert (
                url == C.EXCHANGE
                and json["code_verifier"] == "v"
                and json["code"] == "c"
            )
            return Resp()

    assert C.exchange("c", "v", http=Http()) == "sk-or-v1-abc"


def test_only_from_this_computer():
    from fastapi import Request

    class Fake:
        client = type("c", (), {"host": "203.0.113.9"})()

    assert C._local(Fake()) is False  # type: ignore[arg-type]
    assert Request  # imported for typing clarity


def test_management_key_is_checked_saved_and_makes_the_owner_key(monkeypatch):
    import openjarvis.accounts.autoconfig as A

    saved = {}
    monkeypatch.setattr(A, "_save_env", lambda k, v: saved.update({k: v}))
    monkeypatch.setattr(A, "owner_key", lambda http=None: True)
    monkeypatch.setattr(
        C, "check_management", lambda key, http=None: key.endswith("ok")
    )
    c = _client()
    assert (
        c.post("/v1/conectar/gestion", json={"clave": "abc-not-openrouter"}).status_code
        == 400
    )
    bad = c.post("/v1/conectar/gestion", json={"clave": "sk-or-v1-normal-key"})
    assert (
        bad.status_code == 400 and "Provisioning" in bad.json()["detail"] and not saved
    )
    r = c.post("/v1/conectar/gestion", json={"clave": "sk-or-v1-gestion-ok"})
    assert r.json() == {"gestion": True, "ia": True}
    assert saved == {"OPENROUTER_MANAGEMENT_KEY": "sk-or-v1-gestion-ok"}


def test_management_key_only_from_this_computer(monkeypatch):
    monkeypatch.setattr(C, "_local", lambda request: False)
    r = _client().post("/v1/conectar/gestion", json={"clave": "sk-or-v1-gestion-ok"})
    assert r.status_code == 403


def test_estado_says_whether_any_ai_is_connected(monkeypatch):
    import openjarvis.accounts.autoconfig as A

    monkeypatch.setattr(
        A, "ready", lambda: {"openrouter": False, "gemini": False, "gestion": False}
    )
    assert _client().get("/v1/conectar/estado").json() == {
        "ia": False,
        "gestion": False,
        "local": True,
    }

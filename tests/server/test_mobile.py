"""Phone access: pairing token, the relayed-request guard and ``sergio movil``."""

from __future__ import annotations

import base64

import pytest
from click.testing import CliRunner
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from openjarvis.server import mobile

RELAYED = {"cf-connecting-ip": "203.0.113.9"}


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    monkeypatch.delenv("OPENJARVIS_API_KEY", raising=False)
    mobile._cache.update(mtime=None, token="")
    return tmp_path


def _app(api_key: str = "") -> FastAPI:
    app = FastAPI()

    @app.get("/v1/models")
    def models():
        return {"data": []}

    @app.get("/assets/app.js")
    def asset():
        return {"js": True}

    @app.get("/pensar")
    def spa_route():
        return {"html": True}

    @app.websocket("/v1/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text("hola")
        await websocket.close()

    app.add_middleware(mobile.RemoteAccessMiddleware, api_key=api_key)
    return app


def test_token_lifecycle(home):
    assert mobile.current_token() == ""
    first = mobile.ensure_token()
    assert first.startswith("sm_") and len(first) > 40
    assert mobile.ensure_token() == first
    assert (mobile.token_path().stat().st_mode & 0o777) == 0o600
    assert mobile.valid_token(first) and not mobile.valid_token("sm_wrong")
    second = mobile.ensure_token(renew=True)
    assert second != first and not mobile.valid_token(first)


def test_no_token_means_nothing_is_valid(home):
    assert not mobile.valid_token("")
    assert not mobile.valid_token("anything")


def test_local_requests_pass_untouched(home):
    client = TestClient(_app())
    assert client.get("/v1/models").status_code == 200


def test_relayed_requests_need_the_phone_token(home):
    token = mobile.ensure_token()
    client = TestClient(_app())
    denied = client.get("/v1/models", headers=RELAYED)
    assert denied.status_code == 401 and "sergio movil" in denied.json()["detail"]
    for header in ("x-forwarded-for", "x-real-ip", "forwarded", "cf-ray"):
        assert client.get("/v1/models", headers={header: "1.2.3.4"}).status_code == 401
    ok = client.get(
        "/v1/models", headers={**RELAYED, "Authorization": f"Bearer {token}"}
    )
    assert ok.status_code == 200
    wrong = client.get("/v1/models", headers={**RELAYED, "Authorization": "Bearer x"})
    assert wrong.status_code == 401


def test_server_api_key_also_opens_the_tunnel(home):
    client = TestClient(_app(api_key="server-key"))
    headers = {**RELAYED, "Authorization": "Bearer server-key"}
    assert client.get("/v1/models", headers=headers).status_code == 200


def test_app_shell_is_public_but_holds_no_data(home):
    client = TestClient(_app())
    assert client.get("/assets/app.js", headers=RELAYED).status_code == 200
    assert client.get("/pensar", headers=RELAYED).status_code == 200
    assert mobile._is_public("/")
    assert mobile._is_public("/manifest.webmanifest")
    for path in ("/v1/chat/completions", "/api/x", "/docs", "/openapi.json", "/x.db"):
        assert not mobile._is_public(path), path


def test_cors_preflight_passes(home):
    client = TestClient(_app())
    resp = client.options(
        "/v1/models",
        headers={**RELAYED, "Access-Control-Request-Method": "GET", "Origin": "x"},
    )
    assert resp.status_code != 401


def test_websocket_through_the_tunnel(home):
    token = mobile.ensure_token()
    client = TestClient(_app())
    with pytest.raises(Exception) as exc:
        with client.websocket_connect("/v1/ws", headers=RELAYED) as ws:
            ws.receive_text()
    assert "4401" in repr(exc.value) or getattr(exc.value, "code", None) == 4401
    proto = "openjarvis.key.b64url." + base64.urlsafe_b64encode(
        token.encode()
    ).decode().rstrip("=")
    with client.websocket_connect(
        "/v1/ws", headers={**RELAYED, "sec-websocket-protocol": proto}
    ) as ws:
        assert ws.receive_text() == "hola"
    with client.websocket_connect(
        "/v1/ws", headers={**RELAYED, "Authorization": f"Bearer {token}"}
    ) as ws:
        assert ws.receive_text() == "hola"


def test_pair_url_and_tunnel_parsing():
    assert mobile.pair_url("https://a.trycloudflare.com/", "sm_x") == (
        "https://a.trycloudflare.com/#pair=sm_x"
    )
    line = "INF |  https://brave-cat-12.trycloudflare.com  |"
    assert mobile.parse_tunnel_url(line) == "https://brave-cat-12.trycloudflare.com"
    assert mobile.parse_tunnel_url("INF Starting tunnel") is None
    assert mobile.split_pair("#pair=sm_x") == ("pair", "sm_x")


def test_meshgen_key_never_leaves_through_a_tunnel(monkeypatch):
    from openjarvis.server.vision_routes import router

    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, client=("127.0.0.1", 5000))
    assert client.get("/v1/vision/meshgen_key").json() == {"key": "secret-key"}
    relayed = client.get("/v1/vision/meshgen_key", headers=RELAYED)
    assert relayed.status_code == 403
    remote = TestClient(app, client=("192.168.1.5", 5000))
    assert remote.get("/v1/vision/meshgen_key").status_code == 403


def test_phone_token_accepted_by_auth_middleware(home):
    from openjarvis.server.auth_middleware import _phone_token

    token = mobile.ensure_token()
    assert _phone_token(token) and not _phone_token("nope")


# -- sergio movil ---------------------------------------------------------------


def test_movil_olvidar_and_estado(home, monkeypatch):
    from openjarvis.cli import movil_cmd

    first = mobile.ensure_token()
    runner = CliRunner()
    result = runner.invoke(movil_cmd.movil, ["olvidar"])
    assert result.exit_code == 0
    assert mobile.current_token() and mobile.current_token() != first
    monkeypatch.setattr(movil_cmd, "find_cloudflared", lambda: None)
    status = runner.invoke(movil_cmd.movil, ["estado"])
    assert status.exit_code == 0 and "vinculado: sí" in status.output


def test_movil_refuses_when_server_is_off(home, monkeypatch):
    import httpx

    from openjarvis.cli import movil_cmd

    def down(*a, **k):
        raise httpx.ConnectError("off")

    monkeypatch.setattr(httpx, "get", down)
    result = CliRunner().invoke(movil_cmd.movil, [])
    assert result.exit_code != 0 and "servicio encender" in result.output


def test_movil_local_link_shows_qr(home, monkeypatch):
    import httpx

    from openjarvis.cli import movil_cmd

    class Ok:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Ok())
    monkeypatch.setattr(movil_cmd, "build_ui", lambda: True)
    monkeypatch.setattr(movil_cmd, "_server_port", lambda: 8123)
    result = CliRunner().invoke(movil_cmd.movil, ["--sin-tunel"])
    assert result.exit_code == 0, result.output
    assert f"http://127.0.0.1:8123/#pair={mobile.current_token()}" in result.output
    assert movil_cmd.render_qr("hola")  # segno is a core dependency


def test_movil_opens_tunnel_and_closes_it(home, monkeypatch):
    import httpx

    from openjarvis.cli import movil_cmd

    class Ok:
        def raise_for_status(self):
            return None

    class FakeProc:
        terminated = False

        def __init__(self, cmd, **kw):
            self.cmd = cmd
            self.stdout = iter(
                ["INF Requesting\n", "INF | https://red-fox-7.trycloudflare.com |\n"]
            )

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return None if not FakeProc.terminated else 0

        def terminate(self):
            FakeProc.terminated = True

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Ok())
    monkeypatch.setattr(movil_cmd, "build_ui", lambda: True)
    monkeypatch.setattr(movil_cmd, "find_cloudflared", lambda: "/bin/cloudflared")
    monkeypatch.setattr(movil_cmd.subprocess, "Popen", FakeProc)
    result = CliRunner().invoke(movil_cmd.movil, [])
    assert result.exit_code == 0, result.output
    assert "https://red-fox-7.trycloudflare.com/#pair=sm_" in result.output
    assert FakeProc.terminated

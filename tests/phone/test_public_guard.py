"""Only webhook paths are reachable through the public tunnel."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from openjarvis.core.config import JarvisConfig
from openjarvis.phone.public_guard import PublicExposureGuard


def _client():
    cfg = JarvisConfig()
    cfg.phone.public_url = "https://sergio-x.ngrok-free.app"
    app = FastAPI()

    @app.get("/v1/phone/calls")
    def calls():
        return {"secret": True}

    @app.post("/phone/incoming")
    def incoming():
        return {"ok": True}

    @app.post("/webhooks/whatsapp")
    def wa():
        return {"ok": True}

    @app.websocket("/v1/ws")
    async def private_ws(ws: WebSocket):
        await ws.accept()
        await ws.send_text("private")

    app.add_middleware(PublicExposureGuard, config_getter=lambda: cfg)
    return TestClient(app)


def test_local_requests_reach_everything():
    client = _client()
    assert client.get("/v1/phone/calls").status_code == 200


def test_tunnel_requests_only_reach_webhooks():
    client = _client()
    tunneled = {"X-Forwarded-For": "1.2.3.4"}
    assert client.get("/v1/phone/calls", headers=tunneled).status_code == 403
    assert client.post("/phone/incoming", headers=tunneled).status_code == 200
    assert client.post("/webhooks/whatsapp", headers=tunneled).status_code == 200
    by_host = {"Host": "sergio-x.ngrok-free.app"}
    assert client.get("/v1/phone/calls", headers=by_host).status_code == 403
    cf = {"Cf-Connecting-Ip": "1.2.3.4"}
    assert client.get("/v1/phone/calls", headers=cf).status_code == 403


def test_private_websockets_are_closed_through_the_tunnel():
    import pytest
    from starlette.websockets import WebSocketDisconnect

    client = _client()
    with client.websocket_connect("/v1/ws") as ws:
        assert ws.receive_text() == "private"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/v1/ws", headers={"X-Forwarded-For": "1.2.3.4"}
        ) as ws:
            ws.receive_text()

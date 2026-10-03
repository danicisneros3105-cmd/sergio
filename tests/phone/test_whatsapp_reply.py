"""WhatsApp: the owner's message is answered; strangers get nothing."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server import webhook_routes  # noqa: E402


class Bridge:
    def __init__(self):
        self.seen = []

    def handle_incoming(self, sender, text, channel):
        self.seen.append((sender, text, channel))
        return "" if sender != "593991234567" else "Claro, " + "x" * 5000


def _payload(sender, text):
    return json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": sender,
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()


def test_owner_gets_reply_in_chunks_stranger_gets_nothing(monkeypatch):
    sent = []

    class FakeChannel:
        def send(self, to, text):
            sent.append((to, len(text)))
            return True

    monkeypatch.setattr("openjarvis.channels.whatsapp.WhatsAppChannel", FakeChannel)
    bridge = Bridge()
    app = FastAPI()
    app.include_router(
        webhook_routes.create_webhook_router(
            bridge=bridge, whatsapp_verify_token="v", whatsapp_app_secret="s"
        )
    )
    client = TestClient(app)
    for sender in ("593991234567", "15550000000"):
        body = _payload(sender, "hola")
        sig = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
        resp = client.post(
            "/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig}
        )
        assert resp.status_code == 200
    for _ in range(50):
        if len(bridge.seen) == 2 and len(sent) == 2:
            break
        time.sleep(0.05)
    assert sent == [
        ("593991234567", 4096),
        ("593991234567", len("Claro, ") + 5000 - 4096),
    ]

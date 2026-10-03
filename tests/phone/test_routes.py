"""Twilio webhooks: signatures, owner-only inbound calls, status updates."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
twilio = pytest.importorskip("twilio")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from twilio.request_validator import RequestValidator  # noqa: E402

from openjarvis.core.config import JarvisConfig  # noqa: E402
from openjarvis.phone import calls  # noqa: E402
from openjarvis.phone.routes import router  # noqa: E402

BASE = "https://sergio.example.test"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+15550001111")
    cfg = JarvisConfig()
    cfg.phone.enabled = True
    cfg.phone.public_url = BASE
    cfg.phone.owner_numbers = ["+593991234567"]
    app = FastAPI()
    app.state.config = cfg
    app.include_router(router)
    return TestClient(app)


def _post(client, path, form, *, sign=True):
    signature = RequestValidator("secret").compute_signature(BASE + path, form)
    headers = {"X-Twilio-Signature": signature if sign else "bad"}
    return client.post(path, data=form, headers=headers)


def test_owner_call_is_connected_to_the_voice_bot(client):
    resp = _post(
        client,
        "/phone/incoming",
        {"From": "+593991234567", "To": "+1555", "CallSid": "CA1"},
    )
    assert resp.status_code == 200
    assert "<Connect><Stream" in resp.text and "/phone/ws" in resp.text


def test_strangers_hear_a_message_and_the_call_ends(client):
    resp = _post(client, "/phone/incoming", {"From": "+15559999999", "To": "+1555"})
    assert "<Hangup/>" in resp.text and "<Stream" not in resp.text


def test_unsigned_requests_are_rejected(client):
    resp = _post(client, "/phone/incoming", {"From": "+593991234567"}, sign=False)
    assert resp.status_code == 403


def test_status_callback_marks_unanswered_calls_failed(client):
    record = calls.new_call(calls.OUTBOUND, "+593222222222", goal="x")
    path = f"/phone/status?call_id={record.id}"
    assert _post(client, path, {"CallStatus": "no-answer"}).status_code == 200
    assert calls.load(record.id).status == calls.FAILED
    assert calls.load(record.id).error == "no-answer"


def test_call_list_hides_tokens(client):
    calls.new_call(calls.OUTBOUND, "+593222222222", goal="Reservar")
    body = client.get("/v1/phone/calls").json()
    assert body["calls"] and "token" not in body["calls"][0]

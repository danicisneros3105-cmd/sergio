"""Calls: records, Twilio placement, webhooks and the phone/WhatsApp tools."""

from __future__ import annotations

import pytest

from openjarvis.core.config import JarvisConfig
from openjarvis.phone import bot, calls
from openjarvis.tools.approval_store import ApprovalStore
from openjarvis.tools.phone_tools import (
    PhoneCallStatusTool,
    PhoneCallTool,
    WhatsAppSendTool,
)

OWNER = "+593991234567"
STRANGER = "+593222222222"


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+15550001111")
    cfg = JarvisConfig()
    cfg.phone.enabled = True
    cfg.phone.public_url = "https://sergio.example.test"
    cfg.phone.owner_numbers = [OWNER]
    cfg.phone.owner_name = "Dani"
    cfg.phone.approval_wait_seconds = 0
    cfg.phone.max_call_minutes = 1
    return cfg


class FakeCalls:
    def __init__(self):
        self.created = []

    def create(self, **kwargs):
        self.created.append(kwargs)
        return type("Call", (), {"sid": "CA123"})()


def test_twiml_streams_to_the_tunnel_with_a_secret_token(config):
    record = calls.new_call(calls.OUTBOUND, STRANGER, goal="x")
    twiml = calls.stream_twiml(config, record)
    assert 'url="wss://sergio.example.test/phone/ws"' in twiml
    assert f'value="{record.token}"' in twiml
    config.phone.public_url = "http://insecure"
    with pytest.raises(calls.PhoneConfigError):
        calls.stream_twiml(config, record)


def test_place_call_limits_duration_and_reports_status(config):
    fake = type("Client", (), {"calls": FakeCalls()})()
    record = calls.place_call(
        config, calls.new_call(calls.OUTBOUND, STRANGER), client=fake
    )
    sent = fake.calls.created[0]
    assert sent["to"] == STRANGER and sent["from_"] == "+15550001111"
    assert sent["time_limit"] == 60
    assert sent["status_callback"].endswith(f"/phone/status?call_id={record.id}")
    assert calls.load(record.id).twilio_sid == "CA123"


def test_missing_credentials_are_explained(monkeypatch):
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    with pytest.raises(calls.PhoneConfigError, match="TWILIO_AUTH_TOKEN"):
        calls.credentials()


def test_bot_discloses_ai_to_third_parties_only(config):
    third = calls.CallRecord(
        id="a", token="t", kind=calls.OUTBOUND, to=STRANGER, goal="g"
    )
    owner = calls.CallRecord(id="b", token="t", kind=calls.OUTBOUND, to=OWNER)
    assert "inteligencia artificial" in bot.greeting(config, third)
    assert "de parte de Dani" in bot.greeting(config, third)
    assert bot.greeting(config, owner).startswith("Hola Dani")
    prompt = bot.system_prompt(config, third)
    assert "Objetivo de la llamada: g" in prompt and "end_call" in prompt


def test_transcript_keeps_only_spoken_turns():
    messages = [
        {"role": "system", "content": "x"},
        {"role": "assistant", "content": "Hola, ¿mesa para dos?"},
        {"role": "user", "content": [{"type": "text", "text": "Sí, claro"}]},
        {"role": "tool", "content": "ok"},
        "not a dict",
    ]
    assert bot.transcript_from(messages) == [
        {"role": "sergio", "text": "Hola, ¿mesa para dos?"},
        {"role": "them", "text": "Sí, claro"},
    ]


def _finish(text="Reserva hecha para las 17:00"):
    def fake_place(config, record):
        calls.update(
            record.id,
            status=calls.COMPLETED,
            summary=text,
            transcript=[
                {"role": "sergio", "text": "Hola"},
                {"role": "them", "text": "Ok"},
            ],
        )
        return record

    return fake_place


def test_calling_the_owner_needs_no_approval(config, monkeypatch, tmp_path):
    monkeypatch.setattr(calls, "place_call", _finish("Recordatorio entregado"))
    tool = PhoneCallTool(
        config=config,
        approvals=ApprovalStore(str(tmp_path / "a.db")),
        sleep=lambda s: None,
    )
    result = tool.execute(number=OWNER, goal="Recordarle la reunión")
    assert result.success and "Recordatorio entregado" in result.content
    assert "Them: Ok" in result.content


def test_third_party_call_waits_for_approval_and_never_dials_when_denied(
    config, monkeypatch, tmp_path
):
    placed = []
    monkeypatch.setattr(calls, "place_call", lambda c, r: placed.append(r) or r)
    store = ApprovalStore(str(tmp_path / "a.db"))
    tool = PhoneCallTool(config=config, approvals=store, sleep=lambda s: None)
    waiting = tool.execute(number=STRANGER, goal="Reservar mesa")
    assert not waiting.success and waiting.metadata["pending"]
    action_id = waiting.metadata["approval_id"]
    assert store.get_action(action_id).tier == "high"

    store.update_status(action_id, "denied")
    denied = tool.execute(number=STRANGER, goal="x", approval_id=action_id)
    assert not denied.success and placed == []


def test_approved_third_party_call_uses_the_approved_goal(
    config, monkeypatch, tmp_path
):
    seen = []

    def fake_place(cfg, record):
        seen.append((record.to, record.goal))
        return _finish()(cfg, record)

    monkeypatch.setattr(calls, "place_call", fake_place)
    store = ApprovalStore(str(tmp_path / "a.db"))
    tool = PhoneCallTool(config=config, approvals=store, sleep=lambda s: None)
    action_id = tool.execute(number=STRANGER, goal="Mesa para 2 a las 5 pm").metadata[
        "approval_id"
    ]
    store.update_status(action_id, "approved")
    result = tool.execute(
        number="+10000000000", goal="otra cosa", approval_id=action_id
    )
    assert result.success and seen == [(STRANGER, "Mesa para 2 a las 5 pm")]


def test_call_tool_validates_setup_and_numbers(config, monkeypatch):
    tool = PhoneCallTool(config=config)
    assert "international" in tool.execute(number="0991234567", goal="x").content
    config.phone.enabled = False
    assert "not set up" in tool.execute(number=OWNER, goal="x").content
    config.phone.enabled = True
    monkeypatch.delenv("TWILIO_ACCOUNT_SID")
    assert "TWILIO_ACCOUNT_SID" in tool.execute(number=OWNER, goal="x").content


def test_failed_placement_is_reported(config, monkeypatch):
    def boom(cfg, record):
        raise RuntimeError("Twilio said no")

    monkeypatch.setattr(calls, "place_call", boom)
    result = PhoneCallTool(config=config).execute(number=OWNER, goal="x")
    assert not result.success and "Twilio said no" in result.content
    status = PhoneCallStatusTool(config=config).execute(
        call_id=result.metadata["call_id"]
    )
    assert "did not happen" in status.content


class FakeWhatsApp:
    _token = "t"
    _phone_number_id = "1"

    def __init__(self, ok=True):
        self.sent = []
        self.ok = ok

    def send(self, to, text):
        self.sent.append((to, text))
        return self.ok


def test_whatsapp_to_owner_goes_out_directly(config, tmp_path):
    channel = FakeWhatsApp()
    tool = WhatsAppSendTool(config=config, channel=channel)
    assert tool.execute(to=OWNER, text="Llego en 10").success
    assert channel.sent == [("593991234567", "Llego en 10")]


def test_whatsapp_to_others_needs_approval_and_explains_24h_rule(config, tmp_path):
    channel = FakeWhatsApp(ok=False)
    store = ApprovalStore(str(tmp_path / "a.db"))
    tool = WhatsAppSendTool(
        config=config, channel=channel, approvals=store, sleep=lambda s: None
    )
    waiting = tool.execute(to=STRANGER, text="Hola")
    assert waiting.metadata["pending"] and channel.sent == []
    store.update_status(waiting.metadata["approval_id"], "approved")
    result = tool.execute(to="", text="", approval_id=waiting.metadata["approval_id"])
    assert channel.sent == [("593222222222", "Hola")]
    assert not result.success and "24 hours" in result.content


def test_whatsapp_without_keys_is_explained(config):
    channel = FakeWhatsApp()
    channel._token = ""
    assert (
        "WHATSAPP_ACCESS_TOKEN"
        in WhatsAppSendTool(config=config, channel=channel)
        .execute(to=OWNER, text="x")
        .content
    )

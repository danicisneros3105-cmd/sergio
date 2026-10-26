"""Medium and complicated chat requests are understood by Terry first."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server.app import create_app  # noqa: E402
from tests.server.test_routes import _make_engine, _test_config  # noqa: E402

BIG = (
    "Analiza y compara tres estrategias para lanzar mi cafetería en Cuenca: "
    "presupuesto, redes, alianzas con negocios del barrio y un plan paso a paso "
    "de cuatro semanas; además diseña el mensaje principal."
)


@pytest.fixture
def setup(monkeypatch):
    from openjarvis.agents import terry

    monkeypatch.setenv("SERGIO_TERRY", "1")
    monkeypatch.setattr(terry, "learned", lambda text: 0.0)
    monkeypatch.setattr(terry, "judge_previous", lambda text: 0.0)
    calls = []

    def prepare(request, history, model, ask=None):
        calls.append(request)
        return "<encargo_preparado>Objetivo: plan</encargo_preparado>", {
            "intent": "plan"
        }

    monkeypatch.setattr(terry, "prepare", prepare)
    engine = _make_engine()
    client = TestClient(create_app(engine, "test-model", config=_test_config()))
    return client, engine, calls


def test_a_streamed_request_shows_asking_terry_then_the_answer(setup):
    client, _engine, calls = setup
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": BIG}],
            "stream": True,
        },
    ) as resp:
        body = "".join(resp.iter_text())
    assert calls == [BIG]
    assert body.index("event: status") < body.index("Hello")
    phases = [
        json.loads(line[6:])["phase"]
        for line in body.splitlines()
        if line.startswith('data: {"phase"')
    ]
    assert phases[0] == "Entendiendo lo que necesitas…" and len(phases) >= 2


def test_the_brief_rides_as_an_instruction_and_the_owners_words_stay(setup):
    client, engine, calls = setup
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "test-model", "messages": [{"role": "user", "content": BIG}]},
    )
    assert resp.status_code == 200 and calls == [BIG]
    sent = engine.generate.call_args[0][0]
    role = lambda m: getattr(m.role, "value", m.role)  # noqa: E731
    system = " ".join(str(m.content) for m in sent if role(m) == "system")
    users = [m.content for m in sent if role(m) == "user"]
    assert "<encargo_preparado>" in system and users[-1] == BIG


def test_small_talk_never_waits_for_terry(setup):
    client, _engine, calls = setup
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "test-model", "messages": [{"role": "user", "content": "hola"}]},
    )
    assert resp.status_code == 200 and calls == []


def test_quick_chat_never_waits_for_terry(setup):
    client, _engine, calls = setup
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "[Quick Chat] responde corto"},
                {"role": "user", "content": BIG},
            ],
        },
    )
    assert resp.status_code == 200 and calls == []

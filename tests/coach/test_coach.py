"""The coach's thinking, with a fake Gemini (no network)."""

from __future__ import annotations

import json
import time

import pytest

from openjarvis.coach import brain, tasks


class FakeResp:
    def __init__(self, text):
        self.text = text
        self.candidates = []


class FakeModels:
    def __init__(self, answers, delay=0.0):
        self.answers = list(answers)
        self.calls = []
        self.delay = delay

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        time.sleep(self.delay)
        answer = self.answers.pop(0) if self.answers else "{}"
        if isinstance(answer, Exception):
            raise answer
        return FakeResp(answer if isinstance(answer, str) else json.dumps(answer))


class FakeClient:
    def __init__(self, answers, delay=0.0):
        self.models = FakeModels(answers, delay)


def test_parse_json_takes_fenced_or_wrapped_answers():
    assert brain.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert brain.parse_json('Claro: {"a": [1, 2]} listo') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        brain.parse_json("nada")


def test_every_knowledge_file_loads():
    for name in ("psicologia", "psiquiatria", "salud", "aprendizaje", "idiomas", "prompting", "inteligencia"):
        assert len(brain.knowledge(name)) > 500, name
    assert "171" in brain.knowledge("psicologia") and "ECU 911" in brain.knowledge("psicologia")


def test_a_model_that_fails_hands_over_to_the_next():
    client = FakeClient([RuntimeError("503"), {"resumen": "ok"}])
    data = tasks.update_profile({"gym": {}}, client=client)
    assert data["resumen"] == "ok" and data["rasgos"] == [] and len(client.models.calls) == 2


def test_the_plan_researches_on_the_web():
    plan = {"titulo": "Doble lift", "sesiones": [{"dia": 0, "minutos": 20, "objetivo": "x", "pasos": []}]}
    client = FakeClient([plan])
    data = tasks.make_plan("doble lift con cartas", "habilidad", {}, ["19:00-21:00"], client=client)
    assert data["titulo"] == "Doble lift" and data["metricas"] == []
    config = client.models.calls[0][2]
    assert config.tools and config.response_mime_type is None  # Google Search on


def test_video_marks_are_cleaned_and_sorted():
    answer = {"resumen": "bien", "marcas": [
        {"t": 4, "x": 1.4, "y": 0.5, "r": 0.9, "bien": False, "texto": "se ve la carta"},
        {"t": 1, "x": 0.2, "y": 0.3, "bien": True, "texto": "buen ángulo"},
        {"t": "?", "x": 0, "y": 0},
    ]}  # fmt: skip
    data = tasks.review_video(b"vid", "video/mp4", "doble lift", client=FakeClient([answer]))
    assert [m["t"] for m in data["marcas"]] == [1.0, 4.0]
    assert data["marcas"][1]["x"] == 1.0 and data["marcas"][1]["r"] == 0.3 and not data["marcas"][1]["bien"]


def test_risk_always_gets_the_crisis_lines():
    calm = {"respuesta": "Te escucho.", "riesgo": "ninguno"}
    data = tasks.therapy_turn([{"role": "user", "content": "no quiero vivir"}], [], {}, client=FakeClient([calm]))
    assert data["riesgo"] == "alto" and "171" in data["respuesta"] and "ECU 911" in data["respuesta"]
    ok = tasks.therapy_turn([{"role": "user", "content": "tuve un mal día"}], [], {}, client=FakeClient([calm]))
    assert ok["respuesta"] == "Te escucho." and ok["riesgo"] == "ninguno"


def test_a_slow_model_never_delays_someone_at_risk(monkeypatch):
    monkeypatch.setattr(tasks, "RISK_TIMEOUT", 0.2)
    started = time.monotonic()
    data = tasks.therapy_turn(
        [{"role": "user", "content": "me quiero morir"}], [], {}, client=FakeClient([{"respuesta": "x"}], delay=1.0)
    )
    assert time.monotonic() - started < 0.8 and data["respuesta"] == tasks.CRISIS


def test_routes_answer(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server.coach_routes import router

    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(tasks, "update_profile", lambda c, p: {"resumen": "x", "got": c})
    client = TestClient(app)
    assert client.post("/v1/coach/profile", json={"context": {"a": 1}}).json() == {"resumen": "x", "got": {"a": 1}}
    assert client.post("/v1/coach/plan", json={"goal": "  "}).status_code == 400

    def broken(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr(tasks, "therapy_turn", broken)
    risky = client.post("/v1/coach/therapy", json={"messages": [{"role": "user", "content": "quiero morir"}]})
    assert risky.status_code == 200 and "171" in risky.json()["respuesta"]
    calm = client.post("/v1/coach/therapy", json={"messages": [{"role": "user", "content": "hola"}]})
    assert calm.status_code == 502

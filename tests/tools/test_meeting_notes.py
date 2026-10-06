"""Minutes of meetings: Gemini's JSON, the Markdown, the route (fake Gemini)."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from openjarvis.tools import meeting_notes
from openjarvis.tools.meeting_notes import parse_minutes, summarize, to_markdown

MINUTES = {
    "titulo": "Presupuesto 2027",
    "resumen": "Se revisó el presupuesto y se aprobó con cambios.",
    "puntos_clave": ["Marketing baja 10%"],
    "decisiones": ["Aprobar el presupuesto"],
    "tareas": [{"quien": "Ana", "que": "enviar el informe", "cuando": "viernes"}],
    "preguntas_abiertas": [],
    "transcripcion": [{"t": "00:03", "quien": "Daniel", "texto": "Empecemos."}],
}


def test_parse_accepts_fenced_json_and_fills_missing_lists():
    data = parse_minutes("```json\n" + json.dumps({"titulo": "X", "resumen": "Y"}) + "\n```")
    assert data["tareas"] == [] and data["transcripcion"] == [] and data["titulo"] == "X"
    with pytest.raises(ValueError):
        parse_minutes("sin json")
    with pytest.raises(ValueError):
        parse_minutes('{"titulo": "sin resumen"}')


def test_markdown_has_every_section():
    md = to_markdown(MINUTES, when="06/10/2026 10:00", seconds=125, speakers=["Daniel", "Ana"])
    assert md.startswith("# Presupuesto 2027")
    assert "2 min 5 s" in md and "Participantes: Daniel, Ana" in md
    assert "## Decisiones" in md and "| Ana | enviar el informe | viernes |" in md
    assert "**[00:03] Daniel:** Empecemos." in md
    assert "## Preguntas abiertas" not in md  # empty sections are left out


class FakeTypes:
    class Part:
        @staticmethod
        def from_bytes(data, mime_type):
            return NS(data=data, mime=mime_type)

    @staticmethod
    def GenerateContentConfig(**kw):  # noqa: N802
        return NS(**kw)


def test_summarize_tries_the_next_model_and_uses_the_timeline():
    calls = []

    def generate(model, contents, config):
        calls.append((model, contents))
        if len(calls) == 1:
            raise RuntimeError("503 overloaded")
        return NS(text=json.dumps(MINUTES))

    client = NS(models=NS(generate_content=generate))
    data = summarize(b"OggS...", "audio/ogg", "00:00-00:05 Daniel", owner="Daniel", client=client, types=FakeTypes)
    assert data["titulo"] == "Presupuesto 2027"
    assert [m for m, _ in calls] == list(meeting_notes.MODELS[:2])
    audio, prompt = calls[1][1]
    assert audio.mime == "audio/ogg" and "00:00-00:05 Daniel" in prompt and "Daniel" in prompt


def test_route_returns_the_minutes_and_markdown(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server import meeting_routes

    monkeypatch.setattr(meeting_notes, "summarize", lambda *a, **kw: dict(MINUTES))
    monkeypatch.setattr("openjarvis.faces.routes.owner_name", lambda: "Daniel")
    app = FastAPI()
    app.include_router(meeting_routes.router)
    client = TestClient(app)
    resp = client.post(
        "/v1/meeting/summarize",
        files={"audio": ("r.ogg", b"OggS" * 100, "audio/ogg")},
        data={"timeline": "00:00-00:05 Daniel", "seconds": "65", "speakers": json.dumps(["Daniel"])},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["titulo"] == "Presupuesto 2027" and body["markdown"].startswith("# Presupuesto 2027")
    assert client.post("/v1/meeting/summarize", files={"audio": ("r.ogg", b"", "audio/ogg")}).status_code == 413

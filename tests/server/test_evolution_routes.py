"""Evolution over HTTP: feedback, recall, stats and the crew."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.evolution import memory as mem
from openjarvis.server.evolution_routes import router


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        mem, "_shared", [mem.LongTermMemory(tmp_path, use_gemini=False)]
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_feedback_is_kept_and_recalled(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert (
        client.post(
            "/v1/evolve/feedback",
            json={"text": "el asa quedó muy gruesa", "rating": -5, "about": "la taza"},
        ).status_code
        == 200
    )
    hits = client.get(
        "/v1/evolve/recall", params={"q": "asa gruesa de la taza"}
    ).json()["memories"]
    assert hits and "NO LE GUSTÓ" in hits[0]["text"] and "la taza" in hits[0]["text"]
    stats = client.get("/v1/evolve/stats").json()
    assert (
        stats["memories"] == 1
        and stats["self_correction"] in ("langgraph", "loop")
        and "crew" in stats
    )


def test_the_crew_route_reports_a_missing_crewai(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from openjarvis.evolution import crew

    monkeypatch.setattr(crew, "available", lambda: False)
    resp = client.post("/v1/evolve/crew", json={"task": "un informe"})
    assert resp.status_code == 502 and "crewAI" in resp.json()["detail"]


def test_the_crew_result_is_remembered(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from openjarvis.evolution import crew

    monkeypatch.setattr(
        crew,
        "run_crew",
        lambda task, lessons: {
            "result": "informe listo",
            "agents": ["a", "b"],
            "engine": "crewai",
        },
    )
    assert (
        client.post("/v1/evolve/crew", json={"task": "un informe del sueño"}).json()[
            "result"
        ]
        == "informe listo"
    )
    assert (
        "informe del sueño"
        in client.get("/v1/evolve/recall", params={"q": "informe sueño"}).json()[
            "memories"
        ][0]["text"]
    )


def test_think_route_runs_the_deep_layers(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.intelligence import _llm
    from openjarvis.server.evolution_routes import router

    replies = {
        "CONSTITUTION": '{"violations": []}',
        "PROPOSED ANSWER": '{"confidence": 90, "unknowns": []}',
    }

    def fake(prompt):
        return next(
            (v for k, v in replies.items() if k in prompt), "Razono... FINAL ANSWER: 63"
        )

    monkeypatch.setattr(_llm.LLM, "default", classmethod(lambda cls: cls(fake)))
    monkeypatch.setenv("OPENJARVIS_HOME", str(__import__("tempfile").mkdtemp()))
    app = FastAPI()
    app.include_router(router)
    out = (
        TestClient(app)
        .post(
            "/v1/evolve/think",
            json={"question": "calcula 7*9", "strategy": "consistency"},
        )
        .json()
    )
    assert (
        "63" in out["answer"]
        and out["strategy"] == "consistency"
        and out["confidence"] > 0.7
    )
    assert (
        TestClient(app).post("/v1/evolve/think", json={"question": " "}).status_code
        == 400
    )


def _fake_default(monkeypatch, replies=None, fail=False):
    from openjarvis.intelligence import _llm

    replies = replies or {
        "CONSTITUTION": '{"violations": []}',
        "PROPOSED ANSWER": '{"confidence": 90, "unknowns": []}',
    }

    def fake(prompt):
        return next(
            (v for k, v in replies.items() if k in prompt), "Razono... FINAL ANSWER: 63"
        )

    def default(cls):
        if fail:
            raise RuntimeError(
                "No inference engine available (start Ollama or set a Gemini key)."
            )
        return cls(fake)

    monkeypatch.setattr(_llm.LLM, "default", classmethod(default))
    monkeypatch.setenv("OPENJARVIS_HOME", str(__import__("tempfile").mkdtemp()))


def _events(response):
    import json

    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_think_stream_shows_every_step(monkeypatch):
    _fake_default(monkeypatch)
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app).post(
        "/v1/evolve/think/stream",
        json={"question": "calcula 7*9", "strategy": "consistency"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _events(resp)
    stages = [e["stage"] for e in events]
    assert stages[0] == "plan" and stages[-1] == "answer"
    assert {"call", "draft", "constitution", "confidence"} <= set(stages)
    calls = [e for e in events if e["stage"] == "call"]
    assert [c["n"] for c in calls] == list(range(1, len(calls) + 1))
    assert all(c["step"] for c in calls)
    assert "63" in events[-1]["answer"] and events[-1]["calls"] == len(calls)


def test_think_stream_reports_errors_plainly(monkeypatch):
    _fake_default(monkeypatch, fail=True)
    app = FastAPI()
    app.include_router(router)
    events = _events(
        TestClient(app).post("/v1/evolve/think/stream", json={"question": "hola"})
    )
    assert events == [events[0]] and events[0]["stage"] == "error"
    assert events[0]["message"] and events[0]["fix"]


def _ws_app(monkeypatch, api_key=""):
    from openjarvis.server.thinking_routes import router as thinking_router

    app = FastAPI()
    app.include_router(thinking_router)
    app.state.api_key = api_key
    return app


def test_thinking_websocket_streams_every_step(monkeypatch):
    _fake_default(monkeypatch)
    client = TestClient(_ws_app(monkeypatch))
    with client.websocket_connect("/v1/thinking/stream") as ws:
        ws.send_json({"question": "calcula 7*9", "strategy": "consistency"})
        stages = []
        while not stages or stages[-1] not in ("answer", "error"):
            event = ws.receive_json()
            stages.append(event["stage"])
        assert stages[0] == "plan" and stages[-1] == "answer" and "call" in stages
        assert "63" in event["answer"]
        ws.send_json({"question": ""})
        assert ws.receive_json() == {"stage": "error", "message": "question is empty"}
        ws.send_json({"question": "x", "strategy": "magic"})
        assert "strategy" in ws.receive_json()["message"]
        ws.send_json({"stop": True})


def test_thinking_websocket_needs_the_key_when_set(monkeypatch):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    _fake_default(monkeypatch)
    client = TestClient(_ws_app(monkeypatch, api_key="secreta"))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/thinking/stream") as ws:
            ws.receive_json()
    with client.websocket_connect(
        "/v1/thinking/stream", headers={"Authorization": "Bearer secreta"}
    ) as ws:
        ws.send_json({"question": "hola"})
        assert ws.receive_json()["stage"] == "plan"

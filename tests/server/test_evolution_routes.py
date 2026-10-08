"""Evolution over HTTP: feedback, recall, stats and the crew."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.evolution import memory as mem
from openjarvis.server.evolution_routes import router


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(mem, "_shared", [mem.LongTermMemory(tmp_path, use_gemini=False)])
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_feedback_is_kept_and_recalled(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/v1/evolve/feedback", json={"text": "el asa quedó muy gruesa", "rating": -5,
                                                     "about": "la taza"}).status_code == 200
    hits = client.get("/v1/evolve/recall", params={"q": "asa gruesa de la taza"}).json()["memories"]
    assert hits and "NO LE GUSTÓ" in hits[0]["text"] and "la taza" in hits[0]["text"]
    stats = client.get("/v1/evolve/stats").json()
    assert stats["memories"] == 1 and stats["self_correction"] in ("langgraph", "loop") and "crew" in stats


def test_the_crew_route_reports_a_missing_crewai(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from openjarvis.evolution import crew

    monkeypatch.setattr(crew, "available", lambda: False)
    resp = client.post("/v1/evolve/crew", json={"task": "un informe"})
    assert resp.status_code == 502 and "crewAI" in resp.json()["detail"]


def test_the_crew_result_is_remembered(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from openjarvis.evolution import crew

    monkeypatch.setattr(crew, "run_crew", lambda task, lessons: {"result": "informe listo", "agents": ["a", "b"],
                                                                 "engine": "crewai"})
    assert client.post("/v1/evolve/crew", json={"task": "un informe del sueño"}).json()["result"] == "informe listo"
    assert "informe del sueño" in client.get("/v1/evolve/recall", params={"q": "informe sueño"}).json()["memories"][0]["text"]


def test_think_route_runs_the_deep_layers(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.intelligence import _llm
    from openjarvis.server.evolution_routes import router

    replies = {"CONSTITUTION": '{"violations": []}', "PROPOSED ANSWER": '{"confidence": 90, "unknowns": []}'}

    def fake(prompt):
        return next((v for k, v in replies.items() if k in prompt), "Razono... FINAL ANSWER: 63")

    monkeypatch.setattr(_llm.LLM, "default", classmethod(lambda cls: cls(fake)))
    monkeypatch.setenv("OPENJARVIS_HOME", str(__import__("tempfile").mkdtemp()))
    app = FastAPI()
    app.include_router(router)
    out = TestClient(app).post("/v1/evolve/think", json={"question": "calcula 7*9", "strategy": "consistency"}).json()
    assert "63" in out["answer"] and out["strategy"] == "consistency" and out["confidence"] > 0.7
    assert TestClient(app).post("/v1/evolve/think", json={"question": " "}).status_code == 400

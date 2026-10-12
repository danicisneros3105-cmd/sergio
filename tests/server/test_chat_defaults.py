"""A fresh install must chat at once: the configured model is selectable,
easy questions do not think for seconds, and Sergio answers as Sergio."""

from __future__ import annotations

from openjarvis.server.routes import _effort_for


def test_easy_questions_think_little_hard_ones_think_more(monkeypatch):
    monkeypatch.delenv("SERGIO_EFFORT", raising=False)
    assert _effort_for("gemini-3.8-flash", "trivial") == "gemini-3.8-flash@low"
    assert _effort_for("gemini-3.8-flash", "simple") == "gemini-3.8-flash@low"
    assert _effort_for("gemini-3.8-flash", "complex") == "gemini-3.8-flash@medium"
    assert (
        _effort_for("gemini-3.1-pro-preview", "very_complex")
        == "gemini-3.1-pro-preview@high"
    )


def test_explicit_effort_and_other_models_are_left_alone(monkeypatch):
    monkeypatch.delenv("SERGIO_EFFORT", raising=False)
    assert _effort_for("gemini-3.8-flash@high", "trivial") == "gemini-3.8-flash@high"
    assert _effort_for("gemini-2.5-flash", "trivial") == "gemini-2.5-flash"
    assert _effort_for("qwen3.5:0.8b", "trivial") == "qwen3.5:0.8b"
    monkeypatch.setenv("SERGIO_EFFORT", "high")
    assert _effort_for("gemini-3.8-flash", "trivial") == "gemini-3.8-flash"


def test_configured_default_model_is_always_listed():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import openjarvis.server.routes as routes

    class CloudOnly:
        def list_models(self):
            return []

    app = FastAPI()
    app.include_router(routes.router)
    app.state.engine = CloudOnly()
    app.state.model = "gemini-3.8-flash"
    ids = [m["id"] for m in TestClient(app).get("/v1/models").json()["data"]]
    assert ids[0] == "gemini-3.8-flash"


def test_sergio_speaks_as_sergio_by_default():
    from openjarvis.core.config_sections import AgentConfig

    prompt = AgentConfig().default_system_prompt
    assert "Eres Sergio" in prompt and "«señor»" in prompt
    assert "nunca inventes" in prompt.lower()

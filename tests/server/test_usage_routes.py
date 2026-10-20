"""Usage and models for every provider (/v1/usage)."""

import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server import usage_routes


def test_provider_of_covers_more_than_gemini():
    p = usage_routes.provider_of
    assert p("gemini-3.8-flash@low") == "google"
    assert p("claude-opus-5-5") == "anthropic"
    assert p("gpt-5-mini") == "openai" and p("o3-mini") == "openai"
    assert p("openrouter/meta/llama") == "openrouter"
    assert p("kimi-k3") == "moonshot" and p("deepseek-v4") == "deepseek"
    assert p("qwen3:8b") == "local"


def test_usage_groups_models_by_provider_with_their_state(monkeypatch):
    rows = [
        types.SimpleNamespace(
            model_id="gemini-3.8-flash",
            call_count=5,
            total_tokens=900,
            total_cost=0.02,
            avg_latency=1.2,
        ),
        types.SimpleNamespace(
            model_id="qwen3:8b",
            call_count=2,
            total_tokens=300,
            total_cost=0.0,
            avg_latency=3.0,
        ),
    ]

    class Agg:
        def __init__(self, _path):
            pass

        def per_model_stats(self, since):
            return rows

        def close(self):
            pass

    import openjarvis.telemetry.aggregator as aggregator
    from openjarvis.engine import google_client
    from openjarvis.server import api_routes

    monkeypatch.setattr(aggregator, "TelemetryAggregator", Agg)
    monkeypatch.setattr(
        api_routes,
        "_telemetry_db_path",
        lambda _r: types.SimpleNamespace(exists=lambda: True),
    )
    monkeypatch.setattr(usage_routes, "_keys", lambda: {"GEMINI_API_KEY": True})
    monkeypatch.setattr(google_client, "_EXHAUSTED", {})
    app = FastAPI()
    app.state.engine = types.SimpleNamespace(
        list_models=lambda: ["gemini-3.8-flash", "qwen3:8b"]
    )
    app.include_router(usage_routes.router)
    data = TestClient(app).get("/v1/usage?days=7").json()
    assert data["totals"] == {"calls": 7, "tokens": 1200, "cost": 0.02}
    by = {p["key"]: p for p in data["providers"]}
    assert by["google"]["state"] == "conectado" and by["google"]["calls"] == 5
    assert by["anthropic"]["state"] == "sin clave"
    assert by["local"]["models"] == ["qwen3:8b"]

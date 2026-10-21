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


def test_local_models_and_preload_go_through_the_server(monkeypatch):
    import httpx

    calls = []

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            calls.append(url)
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:8b", "size": 5_000_000_000}]}
            )

        async def post(self, url, json):
            calls.append((url, json))
            return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.setenv("OLLAMA_HOST", "http://10.0.0.5:11434")
    app = FastAPI()
    app.include_router(usage_routes.router)
    client = TestClient(app)
    assert client.get("/v1/usage/local-models").json()["models"] == [
        {"name": "qwen3:8b", "size": 5_000_000_000}
    ]
    assert client.post("/v1/usage/preload", json={"model": "qwen3:8b"}).json() == {
        "ok": True
    }
    assert calls[0] == "http://10.0.0.5:11434/api/tags"
    assert calls[1] == (
        "http://10.0.0.5:11434/api/generate",
        {"model": "qwen3:8b", "prompt": "", "keep_alive": "5m"},
    )


def test_local_models_when_ollama_is_closed(monkeypatch):
    import httpx

    class Closed:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            raise httpx.ConnectError("refused")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(httpx, "AsyncClient", Closed)
    app = FastAPI()
    app.include_router(usage_routes.router)
    assert TestClient(app).get("/v1/usage/local-models").json() == {
        "models": [],
        "running": False,
    }

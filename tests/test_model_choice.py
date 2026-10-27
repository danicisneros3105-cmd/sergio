"""Any company's model: the catalog, the effort only for Gemini, and the weight."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.engine.cloud import _plain
from openjarvis.quota import model_weight
from openjarvis.server import personal_routes


def test_effort_stays_only_on_gemini():
    assert _plain("gemini-3.8-flash@low") == "gemini-3.8-flash@low"
    assert _plain("claude-sonnet-4-6@low") == "claude-sonnet-4-6"
    assert _plain("openrouter/meta-llama/llama-3.3-70b-instruct@high").endswith(
        "instruct"
    )
    assert _plain("gpt-5") == "gpt-5"


def test_big_models_count_more():
    assert model_weight("gemini-3.8-flash@low") == 1
    assert model_weight("gemini-3.1-pro-preview") == 3
    assert model_weight("gpt-5-mini") == 1
    assert model_weight("claude-opus-4-6") == 8


def test_catalog_has_every_company(monkeypatch):
    class Engine:
        def list_models(self):
            return ["gemini-3.8-flash"]

        def can_serve(self, model):
            return model.startswith("gemini")

    app = FastAPI()
    app.include_router(personal_routes.router)
    app.state.engine = Engine()
    monkeypatch.setattr(
        "openjarvis.server.cloud_router._load_keys",
        lambda: {"ANTHROPIC_API_KEY": "x"},
    )
    data = TestClient(app).get("/v1/personal/modelos").json()
    companies = {c["id"]: c for c in data["empresas"]}
    assert {"google", "openai", "anthropic", "deepseek", "openrouter"} <= set(companies)
    assert companies["anthropic"]["conectada"] and not companies["openai"]["conectada"]
    by_id = {m["id"]: m for m in data["modelos"]}
    assert by_id["claude-sonnet-5-5"]["disponible"]
    assert not by_id["gpt-5.6-sol"]["disponible"]
    assert by_id["claude-opus-5-5"]["cuenta"] == 8

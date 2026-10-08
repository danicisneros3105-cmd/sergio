"""`sergio ask` never dies with a raw traceback: bad answers, quotas, research
without Ollama, empty questions and piped input."""

from __future__ import annotations

import importlib

import httpx
import pytest
from click.testing import CliRunner

from openjarvis.cli import cli
from openjarvis.cli.hints import hint_engine_error
from openjarvis.core.types import Message, Role
from openjarvis.engine._base import EngineConnectionError
from openjarvis.engine.openai_compat_engines import VLLMEngine

_ask_mod = importlib.import_module("openjarvis.cli.ask")


def _engine(handler) -> VLLMEngine:
    engine = VLLMEngine(host="http://testserver")
    engine._client = httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(handler))
    return engine


def test_a_non_json_answer_is_an_engine_error_not_a_crash():
    engine = _engine(lambda r: httpx.Response(200, text="<html>otro programa</html>"))
    with pytest.raises(EngineConnectionError, match="not JSON.*otro programa"):
        engine.generate([Message(role=Role.USER, content="hola")], model="m")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("engine returned HTTP 429: quota exceeded", "out of quota"),
        ("RESOURCE_EXHAUSTED", "out of quota"),
        ("returned HTTP 401: bad key", "rejected the API key"),
        ("answered with something that is not JSON", "not a model server"),
        ("engine at x returned HTTP 503: busy", "internal error"),
        ("llamacpp engine not reachable at http://localhost:8080", "Engine 'llamacpp' is not reachable"),
    ],
)
def test_each_engine_failure_gets_the_right_hint(error, expected):
    assert expected in hint_engine_error(RuntimeError(error), "llamacpp")


@pytest.fixture()
def patched(monkeypatch, tmp_path):
    from unittest import mock

    from openjarvis.agents.simple import SimpleAgent
    from openjarvis.core.config import JarvisConfig
    from openjarvis.core.registry import AgentRegistry

    if not AgentRegistry.contains("simple"):
        AgentRegistry.register_value("simple", SimpleAgent)
    cfg = JarvisConfig()
    cfg.telemetry.db_path = str(tmp_path / "telemetry.db")
    cfg.traces.enabled = False
    monkeypatch.setattr(_ask_mod, "load_config", lambda: cfg)
    engine = mock.MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    engine.generate.return_value = {"content": "Respuesta.", "usage": {}, "model": "test-model",
                                    "finish_reason": "stop"}
    monkeypatch.setattr(_ask_mod, "get_engine", lambda *a, **kw: ("mock", engine))
    monkeypatch.setattr(_ask_mod, "discover_engines", lambda c: [("mock", engine)])
    monkeypatch.setattr(_ask_mod, "discover_models", lambda e: {"mock": ["test-model"]})
    return engine


def test_a_quota_error_says_quota_not_start_ollama(patched):
    patched.generate.side_effect = EngineConnectionError("mock engine returned HTTP 429: quota")
    result = CliRunner().invoke(cli, ["ask", "--no-stream", "hola"])
    assert result.exit_code == 1
    assert "out of quota" in result.output and "ollama server is running" not in result.output


def test_an_empty_question_is_a_usage_error(patched):
    result = CliRunner().invoke(cli, ["ask", "   "], input="")
    assert result.exit_code == 2 and "Missing question" in result.output


def test_the_question_can_be_piped_in(patched):
    result = CliRunner().invoke(cli, ["ask", "--no-stream"], input="pregunta por tubería\n")
    assert result.exit_code == 0, result.output
    sent = patched.generate.call_args[0][0]
    assert any("pregunta por tubería" in (m.content or "") for m in sent)


def test_research_without_ollama_uses_the_engine_that_was_found(patched, monkeypatch, tmp_path):
    class DeadOllama:
        def health(self):
            return False

    monkeypatch.setattr("openjarvis.engine.ollama.OllamaEngine", DeadOllama)
    seen = {}

    class FakeResearch:
        def __init__(self, engine, search, model, on_event):
            seen["engine"], seen["model"] = engine, model

        def run(self, query):
            raise EngineConnectionError("mock engine returned HTTP 429: quota")

    monkeypatch.setattr("openjarvis.agents.research_loop.ResearchAgent", FakeResearch)
    result = CliRunner().invoke(
        cli, ["ask", "--research", "--knowledge-db", str(tmp_path / "k.db"), "qué sé de mí"]
    )
    assert seen["engine"] is patched and seen["model"] == "test-model"
    assert result.exit_code == 1 and "Research failed" in result.output and "out of quota" in result.output
    assert "Traceback" not in result.output


def test_main_turns_an_unexpected_error_into_one_line(monkeypatch, capsys):
    import openjarvis.cli as cli_pkg

    def boom():
        raise ValueError("algo raro\nsegunda línea")

    monkeypatch.setattr(cli_pkg, "cli", boom)
    monkeypatch.delenv("SERGIO_DEBUG", raising=False)
    monkeypatch.delenv("OPENJARVIS_DEBUG", raising=False)
    with pytest.raises(SystemExit) as stop:
        cli_pkg.main()
    assert stop.value.code == 1
    err = capsys.readouterr().err
    assert "Error: ValueError: algo raro" in err and "SERGIO_DEBUG=1" in err and "segunda" not in err

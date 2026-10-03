"""Kimi (Moonshot) in the cloud engine: tools, instant mode, live model list."""

import sys
import types
from types import SimpleNamespace

import pytest

from openjarvis.core.types import Message, Role
from openjarvis.engine import cloud


class FakeCompletions:
    def __init__(self, reject_thinking=False):
        self.calls = []
        self.reject_thinking = reject_thinking

    def create(self, **kw):
        self.calls.append(kw)
        if self.reject_thinking and "extra_body" in kw:
            raise RuntimeError("Invalid request: unknown parameter thinking")
        call = SimpleNamespace(
            id="c1",
            function=SimpleNamespace(name="screen_read", arguments="{}"),
        )
        msg = SimpleNamespace(
            content="Hola", tool_calls=[call] if kw.get("tools") else None
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, total_tokens=7),
            model=kw["model"],
        )


class FakeOpenAI:
    instances = []

    def __init__(self, base_url=None, api_key=None, **_):
        self.base_url, self.api_key = base_url, api_key
        self.chat = SimpleNamespace(completions=FakeCompletions())
        self.models = SimpleNamespace(
            list=lambda: SimpleNamespace(
                data=[
                    SimpleNamespace(id="kimi-k2.6"),
                    SimpleNamespace(id="moonshot-v1-8k"),
                    SimpleNamespace(id="whisper-x"),
                ]
            )
        )
        FakeOpenAI.instances.append(self)


@pytest.fixture
def engine(monkeypatch):
    for key in list(__import__("os").environ):
        if key.endswith("_API_KEY"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    FakeOpenAI.instances = []
    return cloud.CloudEngine()


def _msgs():
    return [Message(role=Role.USER, content="hola")]


def test_routes_kimi_with_tools_and_instant_mode(engine):
    tools = [
        {"type": "function", "function": {"name": "screen_read", "parameters": {}}}
    ]
    out = engine.generate(_msgs(), model="kimi-k2.6", tools=tools, max_tokens=50)
    client = FakeOpenAI.instances[-1]
    assert (
        client.base_url == cloud.KIMI_DEFAULT_BASE_URL and client.api_key == "sk-test"
    )
    sent = client.chat.completions.calls[-1]
    assert sent["tools"] == tools
    assert sent["extra_body"] == {"thinking": {"type": "disabled"}}
    assert out["content"] == "Hola" and out["tool_calls"][0]["name"] == "screen_read"
    assert engine.can_serve("kimi-k2.6") and engine.health()
    assert not engine.can_serve("qwen3:8b")


def test_models_without_the_switch_are_retried_plainly(engine):
    client = FakeOpenAI.instances[-1]
    client.chat.completions.reject_thinking = True
    out = engine.generate(_msgs(), model="kimi-k2.5")
    assert out["content"] == "Hola"
    assert "extra_body" not in client.chat.completions.calls[-1]


def test_live_model_list_with_fallback(engine):
    assert engine.list_models() == ["kimi-k2.6", "moonshot-v1-8k"]
    broken = cloud.CloudEngine()
    broken._kimi_client.models = SimpleNamespace(
        list=lambda: (_ for _ in ()).throw(OSError())
    )
    broken._kimi_live_models = None
    assert broken.list_models() == cloud._KIMI_MODELS


def test_base_url_override(monkeypatch, engine):
    monkeypatch.setenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    cloud.CloudEngine()
    assert FakeOpenAI.instances[-1].base_url == "https://api.moonshot.cn/v1"


def test_aq_google_keys_use_vertex_express(monkeypatch):
    made = []

    class FakeGenai:
        @staticmethod
        def Client(**kw):  # noqa: N802
            made.append(kw)
            return object()

    google = types.ModuleType("google")
    google.genai = FakeGenai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", FakeGenai)
    for key in list(__import__("os").environ):
        if key.endswith("_API_KEY"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.test")
    cloud.CloudEngine()
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTest")
    cloud.CloudEngine()
    assert made == [{"vertexai": True, "api_key": "AQ.test"}, {"api_key": "AIzaTest"}]


def test_engine_cleans_fullwidth_keys(monkeypatch, engine):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-ｔｅｓｔ")
    cloud.CloudEngine()
    assert FakeOpenAI.instances[-1].api_key == "sk-test"

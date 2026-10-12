"""Free Gemini keys: when a model's daily quota runs out, use a sibling."""

import sys
import types

import pytest

from openjarvis.engine import cloud
from openjarvis.engine.cloud import quota_fallbacks


class Config:
    def __init__(self, **kw):
        self.__dict__.update(
            dict(
                system_instruction=None,
                tools=None,
                response_mime_type=None,
                response_schema=None,
            )
        )
        self.__dict__.update(kw)


@pytest.fixture
def genai(monkeypatch):
    google = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    genai.types = types.SimpleNamespace(
        GenerateContentConfig=Config, ThinkingConfig=lambda **kw: kw
    )
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setattr(cloud, "_QUOTA_EXHAUSTED", {})


class Models:
    def __init__(self, empty):
        self.empty = set(empty)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents))
        if model in self.empty:
            raise RuntimeError(
                "429 RESOURCE_EXHAUSTED. You exceeded your current quota"
            )
        part = types.SimpleNamespace(function_call=None, text=f"hola desde {model}")
        return types.SimpleNamespace(
            candidates=[
                types.SimpleNamespace(content=types.SimpleNamespace(parts=[part]))
            ],
            usage_metadata=None,
            text=f"hola desde {model}",
        )


def _engine(models):
    engine = cloud.CloudEngine.__new__(cloud.CloudEngine)
    engine._google_client = types.SimpleNamespace(models=models)
    engine._thought_sigs = {}
    return engine


def _ask(engine, model):
    from openjarvis.core.types import Message, Role

    return engine._generate_google(
        [Message(role=Role.USER, content="hola")],
        model=model,
        temperature=0.7,
        max_tokens=400,
    )


def test_families():
    assert quota_fallbacks("gemini-3.8-flash")[:2] == [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
    ]
    assert quota_fallbacks("gemini-3.1-pro-preview")[0] == "gemini-pro-latest"
    assert "gemini-3.8-flash" in quota_fallbacks("gemini-3.1-pro-preview")
    assert quota_fallbacks("gemini-3.1-flash-lite")[0] == "gemini-3.5-flash-lite"
    assert quota_fallbacks("qwen3:8b") == []


def test_out_of_quota_moves_on_and_remembers(genai):
    models = Models(empty={"gemini-3.8-flash", "gemini-3.7-flash"})
    engine = _engine(models)
    result = _ask(engine, "gemini-3.8-flash@low")
    assert result["content"] == "hola desde gemini-3.6-flash"
    assert result["model"] == "gemini-3.6-flash"
    assert [m for m, _ in models.calls] == [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
    ]
    # Next time the empty ones are skipped straight away.
    models.calls.clear()
    _ask(engine, "gemini-3.8-flash@low")
    assert [m for m, _ in models.calls] == ["gemini-3.6-flash"]


def test_other_errors_are_not_hidden(genai):
    class Broken(Models):
        def generate_content(self, model, contents, config):
            raise RuntimeError("400 INVALID_ARGUMENT")

    with pytest.raises(RuntimeError, match="INVALID_ARGUMENT"):
        _ask(_engine(Broken(())), "gemini-3.8-flash")


def test_busy_model_moves_on_too(genai):
    class Busy(Models):
        def generate_content(self, model, contents, config):
            if model == "gemini-3.8-flash":
                self.calls.append((model, contents))
                raise RuntimeError(
                    "503 UNAVAILABLE. This model is currently experiencing high demand."
                )
            return super().generate_content(model, contents, config)

    models = Busy(())
    result = _ask(_engine(models), "gemini-3.8-flash@low")
    assert result["model"] == "gemini-3.7-flash"


class SlowModels(Models):
    """The primary model is busy (slow); siblings answer at once."""

    def __init__(self, slow, seconds, fatal=()):
        super().__init__(())
        self.slow = slow
        self.seconds = seconds
        self.fatal = set(fatal)

    def generate_content(self, model, contents, config):
        import time as _time

        if model in self.fatal:
            raise ValueError("400 INVALID_ARGUMENT: bad request")
        if model == self.slow:
            _time.sleep(self.seconds)
        return super().generate_content(model, contents, config)


def test_a_slow_busy_model_gets_a_sibling_and_sergio_answers_fast(genai, monkeypatch):
    import time as _time

    monkeypatch.setattr(cloud, "HEDGE_AFTER", 0.1)
    engine = _engine(SlowModels("gemini-3.8-flash", 3.0))
    t0 = _time.monotonic()
    out = _ask(engine, "gemini-3.8-flash")
    assert out["model"] == "gemini-3.7-flash"
    assert out["content"] == "hola desde gemini-3.7-flash"
    assert _time.monotonic() - t0 < 2.0


def test_a_bad_request_is_not_hidden_by_trying_siblings(genai, monkeypatch):
    monkeypatch.setattr(cloud, "HEDGE_AFTER", 5)
    engine = _engine(SlowModels("", 0, fatal={"gemini-3.8-flash"}))
    with pytest.raises(ValueError, match="INVALID_ARGUMENT"):
        _ask(engine, "gemini-3.8-flash")

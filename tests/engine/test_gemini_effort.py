"""Gemini 3.x: effort (thinking level) per request via a model suffix."""

import sys
import types

from openjarvis.engine.cloud import google_config_kwargs, split_effort


def test_split_effort():
    assert split_effort("gemini-3.8-flash@high") == ("gemini-3.8-flash", "high")
    assert split_effort("gemini-3.1-pro-preview@LOW") == (
        "gemini-3.1-pro-preview",
        "low",
    )
    assert split_effort("qwen3:8b") == ("qwen3:8b", "")
    assert split_effort("user@example") == ("user@example", "")


def _fake_genai(monkeypatch):
    made = []

    class ThinkingConfig:
        def __init__(self, **kw):
            made.append(kw)
            self.kw = kw

    google = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    genai.types = types.SimpleNamespace(ThinkingConfig=ThinkingConfig)
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    return made


def test_gemini3_uses_thinking_level_not_temperature(monkeypatch):
    made = _fake_genai(monkeypatch)
    kw = google_config_kwargs("gemini-3.8-flash", 0.7, 1024, "low")
    assert "temperature" not in kw and kw["max_output_tokens"] == 8192
    assert made == [{"thinking_level": "LOW"}]
    google_config_kwargs("gemini-3.1-pro-preview", 0.7, 1024, "minimal")
    assert made[-1] == {"thinking_level": "LOW"}  # Pro has no minimal


def test_env_default_effort_and_old_models(monkeypatch):
    made = _fake_genai(monkeypatch)
    monkeypatch.setenv("SERGIO_EFFORT", "medium")
    google_config_kwargs("gemini-3.8-flash", 0.7, 1024)
    assert made == [{"thinking_level": "MEDIUM"}]
    assert google_config_kwargs("gemini-2.5-flash", 0.3, 500, "high") == {
        "temperature": 0.3,
        "max_output_tokens": 500,
    }

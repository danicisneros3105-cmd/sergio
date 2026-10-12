import asyncio
import sys

import pytest

from openjarvis.server.live_routes import live_status
from openjarvis.speech import gemini_live


def test_health_distinguishes_missing_sdk_from_missing_key(monkeypatch):
    pytest.importorskip("google.genai", reason="requires the server extra")
    monkeypatch.setattr(gemini_live, "api_key", lambda: "test-key")
    with monkeypatch.context() as m:
        m.setitem(sys.modules, "google.genai", None)
        status = asyncio.run(live_status())
        assert status["reason"] == "missing_sdk" and not status["available"]
    monkeypatch.setattr(gemini_live, "api_key", lambda: "")
    status = asyncio.run(live_status())
    assert status["sdk_installed"] and status["reason"] == "missing_key"


def test_the_real_sdk_accepts_the_duplex_config_without_contacting_google():
    types = pytest.importorskip("google.genai.types", reason="requires the server extra")

    config = gemini_live.live_config(types, voice="Algenib", instructions="Test",
                                     decls=[], search=False)
    assert config.realtime_input_config.automatic_activity_detection.disabled is not True
    assert config.input_audio_transcription and config.output_audio_transcription

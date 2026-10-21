"""The live voice speaks and hears in one fixed language."""

from __future__ import annotations

import pytest

types = pytest.importorskip("google.genai.types")


def test_live_voice_is_locked_to_the_chosen_language():
    from openjarvis.speech.gemini_live import language_code, live_config

    cfg = live_config(
        types, voice="", instructions="x", decls=[], search=False, language="es"
    )
    assert cfg.speech_config.language_code == "es-US"
    assert cfg.input_audio_transcription.language_codes == ["es-US"]
    assert language_code("en-GB") == "en-US"
    auto = live_config(types, voice="", instructions="x", decls=[], search=False)
    assert not auto.input_audio_transcription.language_codes

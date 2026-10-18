"""Sergio's voice is always a man's: names resolve to his voices, and the
read-aloud engine is the same Gemini voice as the live call."""

from __future__ import annotations

import pytest

from openjarvis.speech import _tts_discovery, gemini_tts, gemini_voice


@pytest.mark.parametrize(
    "asked,expected",
    [
        ("", "Algenib"),
        ("Predeterminada", "Algenib"),
        ("default", "Algenib"),
        ("gemini:Orus", "Orus"),
        ("charon", "Charon"),
        ("Zephyr", "Algenib"),
        ("Kore", "Algenib"),
        ("nonsense", "Algenib"),
    ],
)
def test_every_request_becomes_one_of_his_voices(asked, expected):
    assert gemini_voice.sergio_voice(asked) == expected


def test_only_men_are_offered_on_the_desktop():
    pytest.importorskip("sergio_escritorio", reason="the Windows companion")
    from sergio_escritorio.neural_voice import VOICES

    labels = " ".join(label for _id, label in VOICES)
    for woman in ("Andrea", "Dalia", "Elvira"):
        assert woman not in labels
    assert VOICES[0][0] == "gemini:Algenib"


def test_gemini_is_the_configured_default_and_has_its_own_voice():
    from openjarvis.core.config_sections import SpeechConfig

    assert SpeechConfig().tts_backend == "gemini"
    assert SpeechConfig().voice_id == "Algenib"
    assert _tts_discovery.default_voice_for("gemini") == "Algenib"
    assert "gemini" in _tts_discovery.TTS_BACKEND_ORDER


def test_gemini_backend_needs_the_key_and_steps_aside_after_a_quota_error(monkeypatch):
    backend = gemini_tts.GeminiTTSBackend()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert not backend.health()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    gemini_tts._paused_until[0] = 0.0
    assert backend.health()

    spoken = []

    def speak(text, voice):
        spoken.append(voice)
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota")

    monkeypatch.setattr(gemini_voice, "speak", speak)
    with pytest.raises(RuntimeError):
        backend.synthesize("hola", voice_id="Kore")
    assert spoken == ["Algenib"]  # a woman's voice id never reaches Gemini
    assert not backend.health()  # paused: the next backend answers
    gemini_tts._paused_until[0] = 0.0


def test_the_result_is_wav_in_his_voice(monkeypatch):
    monkeypatch.setattr(gemini_voice, "speak", lambda text, voice: b"RIFFwav")
    result = gemini_tts.GeminiTTSBackend().synthesize("hola", voice_id="")
    assert (result.audio, result.format, result.voice_id) == (
        b"RIFFwav",
        "wav",
        "Algenib",
    )

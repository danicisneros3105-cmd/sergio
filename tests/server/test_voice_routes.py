"""Sergio's Gemini voice (British gentleman) and ears; tool schema cleaning."""

import io
import sys
import types
import wave

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.engine.cloud import google_schema
from openjarvis.server import voice_routes
from openjarvis.speech import gemini_voice


def _client():
    app = FastAPI()
    app.include_router(voice_routes.router)
    return TestClient(app)


class FakeModels:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def generate_content(self, model, contents, config=None):
        self.calls.append((model, contents, config))
        result = self.behaviour(model)
        if isinstance(result, Exception):
            raise result
        return result


def _fake_sdk(monkeypatch, behaviour):
    """google.genai.types stand-in + a client whose models we control."""

    class _Cfg(dict):
        def __init__(self, **kw):
            super().__init__(**kw)

    t = types.SimpleNamespace(
        GenerateContentConfig=_Cfg,
        SpeechConfig=_Cfg,
        VoiceConfig=_Cfg,
        PrebuiltVoiceConfig=_Cfg,
        ThinkingConfig=_Cfg,
        Part=types.SimpleNamespace(
            from_bytes=lambda data, mime_type: ("audio", mime_type)
        ),
    )
    google = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    genai.types = t
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    models = FakeModels(behaviour)
    monkeypatch.setattr(
        gemini_voice, "_client", lambda: types.SimpleNamespace(models=models)
    )
    return models


def _audio_response(pcm=b"\x01\x00" * 2400, mime="audio/L16;codec=pcm;rate=24000"):
    blob = types.SimpleNamespace(data=pcm, mime_type=mime)
    part = types.SimpleNamespace(inline_data=blob)
    return types.SimpleNamespace(
        candidates=[types.SimpleNamespace(content=types.SimpleNamespace(parts=[part]))]
    )


def test_speak_returns_wav_with_the_gentleman_style(monkeypatch):
    models = _fake_sdk(monkeypatch, lambda model: _audio_response())
    resp = _client().post(
        "/v1/voice/speak", json={"text": "Buenas tardes.", "voice": "Charon"}
    )
    assert resp.status_code == 200 and resp.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(resp.content)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 2400
    model, prompt, config = models.calls[0]
    assert model == "gemini-3.1-flash-tts-preview"
    assert "caballero británico" in prompt and prompt.endswith("Buenas tardes.")
    voice = config["speech_config"]["voice_config"]["prebuilt_voice_config"]
    assert voice["voice_name"] == "Charon"


def test_speak_falls_back_to_older_tts_models(monkeypatch):
    models = _fake_sdk(
        monkeypatch,
        lambda model: RuntimeError("404") if "3.1" in model else _audio_response(),
    )
    assert _client().post("/v1/voice/speak", json={"text": "Hola"}).status_code == 200
    assert [c[0] for c in models.calls][:2] == [
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-pro-preview-tts",
    ]


def test_speak_reports_failure(monkeypatch):
    _fake_sdk(monkeypatch, lambda model: RuntimeError("quota"))
    resp = _client().post("/v1/voice/speak", json={"text": "Hola"})
    assert resp.status_code == 502 and "quota" in resp.json()["detail"]


def test_transcribe_with_gemini(monkeypatch):
    models = _fake_sdk(
        monkeypatch,
        lambda model: types.SimpleNamespace(text="  «Sergio, ¿qué hora es?»  "),
    )
    resp = _client().post(
        "/v1/voice/transcribe", files={"file": ("v.wav", b"RIFF....", "audio/wav")}
    )
    assert resp.json() == {"text": "Sergio, ¿qué hora es?"}
    assert models.calls[0][0] == "gemini-3.1-flash-lite"  # fastest ears first


def test_empty_transcripts():
    assert gemini_voice.clean_transcript("(vacío)") == ""
    assert gemini_voice.clean_transcript('"hola"') == "hola"


def test_google_schema_cleaning():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "$schema": "x",
        "properties": {
            "city": {"type": ["string", "null"], "default": "Quito"},
            "days": {"type": "integer", "enum": [1, 2, 3]},
            "tags": {"type": "array"},
            "unit": {"oneOf": [{"type": "string"}, {"type": "number"}]},
        },
        "required": ["city", "missing"],
    }
    assert google_schema(schema) == {
        "type": "object",
        "properties": {
            "city": {"type": "string", "nullable": True},
            "days": {"type": "integer", "enum": ["1", "2", "3"]},
            "tags": {"type": "array", "items": {"type": "string"}},
            "unit": {"anyOf": [{"type": "string"}, {"type": "number"}]},
        },
        "required": ["city"],
    }


def test_fast_chat_goes_straight_to_the_model():
    from openjarvis.server import voice_routes as vr

    seen = {}

    class Engine:
        def generate(self, messages, *, model, temperature, max_tokens):
            seen.update(model=model, roles=[m.role.value for m in messages])
            return {"content": " Muy bien, gracias por preguntar. "}

    app = FastAPI()
    app.state.engine = Engine()
    app.include_router(vr.router)
    resp = TestClient(app).post(
        "/v1/voice/chat",
        json={
            "model": "gemini-3.8-flash@low",
            "messages": [
                {"role": "system", "content": "Eres Sergio."},
                {"role": "user", "content": "¿Cómo estás?"},
            ],
        },
    )
    assert resp.json() == {"content": "Muy bien, gracias por preguntar."}
    assert seen == {"model": "gemini-3.8-flash@low", "roles": ["system", "user"]}

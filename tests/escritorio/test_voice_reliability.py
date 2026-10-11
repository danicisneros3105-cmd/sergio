"""Voice identity, audio decoding and conversation continuity, without services."""

import io
import json
import threading
import types
import wave

import httpx
import numpy as np
import pytest
from sergio_escritorio.call import CallSession
from sergio_escritorio.voice import (
    LocalWhisper,
    SergioClient,
    clean_transcript,
    normalise,
)


def audio_wav(rate=16000, channels=1, silence=False):
    samples = (
        np.zeros(rate, dtype=np.int16)
        if silence
        else (np.sin(np.arange(rate) * 2 * np.pi * 440 / rate) * 8000).astype(np.int16)
    )
    samples = np.repeat(samples[:, None], channels, axis=1)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())
    return output.getvalue()


@pytest.mark.parametrize(
    "rate,channels", [(16000, 1), (16000, 2), (48000, 2), (44100, 1)]
)
def test_local_transcription_decodes_audio_and_rejects_unreliable_segments(
    rate, channels
):
    seen = []

    def transcribe(audio, **kwargs):
        seen.append((audio, kwargs))
        return iter(
            [
                types.SimpleNamespace(
                    text="abre VS Code",
                    no_speech_prob=0.1,
                    avg_logprob=-0.2,
                    compression_ratio=1.0,
                ),
                types.SimpleNamespace(
                    text="invento",
                    no_speech_prob=0.9,
                    avg_logprob=-2.0,
                    compression_ratio=5.0,
                ),
            ]
        ), None

    local = LocalWhisper.__new__(LocalWhisper)
    local.lock = threading.Lock()
    local.model = types.SimpleNamespace(transcribe=transcribe)
    assert local.transcribe(audio_wav(rate, channels)) == "abre VS Code"
    data, options = seen[0]
    assert data.ndim == 1 and len(data) == pytest.approx(16000, abs=2)
    assert options["vad_filter"] is True
    assert options["condition_on_previous_text"] is False


def test_silence_does_not_invoke_the_model():
    local = LocalWhisper.__new__(LocalWhisper)
    local.lock = threading.Lock()
    local.model = types.SimpleNamespace(
        transcribe=lambda *a, **kw: pytest.fail("silence reached model")
    )
    assert local.transcribe(audio_wav(silence=True)) == ""
    assert normalise(np.array([], dtype=np.float32)).size == 0
    assert not np.any(normalise(np.array([np.nan, np.inf], dtype=np.float32)))


@pytest.mark.parametrize(
    "text",
    [
        "crea subtítulos para este vídeo",
        "escribe gracias por ver en el cierre",
        "explica qué significa suscríbete",
    ],
)
def test_legitimate_commands_are_not_discarded(text):
    assert clean_transcript(text) == text


def test_custom_voice_failure_never_plays_another_identity(monkeypatch):
    from sergio_escritorio import neural_voice

    monkeypatch.setattr(
        neural_voice, "synthesize", lambda *args: pytest.fail("wrong voice fallback")
    )
    client = SergioClient(
        "http://s",
        http=httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(502, json={"detail": "voice unavailable"})
            )
        ),
    )
    client.voice = "elevenlabs:myVoice"
    with pytest.raises(RuntimeError, match="voz seleccionada"):
        client.speak("Hola")
    assert not client._voice_cache


def test_voice_cache_includes_rate_and_restores_actual_voice(monkeypatch):
    client = SergioClient(
        "http://s",
        http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
    )
    calls = []

    def speak(text):
        calls.append((client.voice_rate, text))
        client.last_voice = "myVoice"
        return b"wav"

    monkeypatch.setattr(client, "_speak", speak)
    assert client.speak("Hola") == b"wav"
    client.last_voice = "another"
    assert client.speak("Hola") == b"wav" and client.last_voice == "myVoice"
    client.voice_rate = "+15%"
    client.speak("Hola")
    assert len(calls) == 2


def test_a_provider_cooldown_does_not_disable_a_new_voice():
    client = SergioClient(
        "http://s",
        http=httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, content=b"myVoice")
            )
        ),
    )
    client._cooldown_voice = "gemini:Algenib"
    client._gemini_voice_off_until = float("inf")
    client.voice = "elevenlabs:myVoice"
    assert client.speak("Hola") == b"myVoice"


def test_partial_stream_is_not_repeated_from_the_start(monkeypatch):
    from sergio_escritorio.voice import Assistant

    client = SergioClient(
        "http://s",
        http=httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200))
        ),
    )
    client.voice = "elevenlabs:myVoice"
    captions, played = [], []

    def stream(text):
        yield b"\x01\x00"
        raise RuntimeError("stream disconnected")

    monkeypatch.setattr(client, "speak_stream", stream)
    monkeypatch.setattr(
        client, "speak", lambda text: pytest.fail("repeated the whole answer")
    )
    assistant = Assistant(
        client,
        ui=types.SimpleNamespace(state=lambda s: None, say=captions.append),
        player=lambda data: None,
    )
    assistant.speaker_factory = lambda: types.SimpleNamespace(
        start=lambda: None, stop=lambda: None, play=played.append, talking=False
    )
    assistant.say_aloud("Mi respuesta completa.")
    assert played == [b"\x01\x00"]
    assert "El audio se interrumpió" in captions[-1]


def test_completed_live_turn_is_saved_once_and_partial_turn_is_not():
    turns = []
    call = CallSession(
        "http://s", on_turn=lambda heard, said: turns.append((heard, said))
    )
    for event in [
        {"type": "heard", "text": "Mi proyecto se llama "},
        {"type": "heard", "text": "Sergio"},
        {"type": "said", "text": "Entendido."},
        {"type": "turn_complete"},
        {"type": "turn_complete"},
        {"type": "heard", "text": "Qué versión"},
        {"type": "said", "text": "Una"},
        {"type": "interrupted"},
        {"type": "turn_complete"},
    ]:
        call._handle(json.dumps(event))
    assert turns == [("Mi proyecto se llama Sergio", "Entendido.")]


def test_live_turn_context_is_available_to_the_next_agent_request():
    seen = []

    def handler(req):
        if req.url.path == "/v1/info":
            return httpx.Response(200, json={"model": "local"})
        seen.append(json.loads(req.content)["messages"])
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Proyecto Sergio"}}]}
        )

    client = SergioClient(
        "http://s", http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    client.remember_turn("Mi proyecto es Sergio", "Entendido")
    assert client.ask("abre su carpeta", force_agent=True) == "Proyecto Sergio"
    assert seen[0][1:3] == [
        {"role": "user", "content": "Mi proyecto es Sergio"},
        {"role": "assistant", "content": "Entendido"},
    ]


@pytest.mark.parametrize(
    "voice",
    [
        "gemini:Algieba",
        "gemini:Predeterminada",
        "es-EC-LuisNeural",
        "elevenlabs:myVoice",
        "",
    ],
)
def test_loading_a_profile_preserves_its_selected_voice(tmp_path, monkeypatch, voice):
    from sergio_escritorio import app

    config = tmp_path / "config.json"
    config.write_text(json.dumps({"voice": voice}), encoding="utf-8")
    monkeypatch.setattr(app, "CONFIG", config)
    assert app.load_config()["voice"] == voice

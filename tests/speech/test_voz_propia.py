"""Sergio's own voice: phrases cut as the answer is written, speech start and
end from loudness, and the /v1/live protocol spoken end to end (with the
speech engines replaced by stand-ins so the test needs no models)."""

import asyncio
import json

import numpy as np

from openjarvis.speech import voz_propia as V


def test_the_first_phrase_goes_out_after_a_few_words():
    c = V.Cutter()
    assert c.add("Mañana en Cuenca ") == []
    first = c.add("estará nublado")
    assert first == ["Mañana en Cuenca"]
    assert c.add(" con dieciocho grados. Lleve") == [
        "estará nublado con dieciocho grados."
    ]
    assert c.add(" chaqueta") == [] and c.rest() == ["Lleve chaqueta"]


def test_what_is_said_has_no_markdown_or_links():
    assert V.clean_for_voice("**Hola** [aquí](http://x.y) `x`") == "Hola aquí x"


def _pcm(seconds, loud):
    n = int(seconds * V.IN_RATE)
    wave = np.sin(np.arange(n) / 8) * (0.3 if loud else 0.0005)
    return (wave * 32767).astype("<i2").tobytes()


def test_the_ear_finds_where_speech_starts_and_ends():
    ear = V.Ear()
    events = [ear.feed(_pcm(0.04, False)) for _ in range(10)]
    events += [ear.feed(_pcm(0.04, True)) for _ in range(25)]
    events += [ear.feed(_pcm(0.04, False)) for _ in range(15)]
    assert events.count("start") == 1 and events.count("end") == 1
    assert "partial" in events
    assert len(ear.utterance()) > V.IN_RATE * 0.9


class _WS:
    def __init__(self, inbox):
        self.inbox, self.out, self.audio = inbox, [], []

    async def receive(self):
        if self.inbox:
            await asyncio.sleep(0.01)
            return self.inbox.pop(0)
        await asyncio.sleep(0.6)
        return {"type": "websocket.disconnect"}

    async def send_text(self, text):
        self.out.append(json.loads(text))

    async def send_bytes(self, data):
        self.audio.append(data)


def test_a_spoken_turn_end_to_end(monkeypatch):
    monkeypatch.setattr(V, "warm", lambda: None)
    monkeypatch.setattr(V, "transcribe", lambda audio, language="es": "¿qué hora es?")
    monkeypatch.setattr(V, "speak_pcm", lambda text, speed=1.05: b"\0\0" * len(text))
    remembered = []

    def think(text, history, sink):
        for word in "Son las tres, señor. Buena tarde.".split(" "):
            sink(word + " ")
        return ""

    inbox = [
        {"type": "websocket.receive", "bytes": _pcm(0.04, True)} for _ in range(20)
    ]
    inbox.append(
        {"type": "websocket.receive", "text": json.dumps({"type": "audio_end"})}
    )
    ws = _WS(inbox)
    call = V.OwnVoiceCall(
        ws,
        {"type": "start"},
        think=think,
        remember=lambda h, s: remembered.append((h, s)),
    )
    asyncio.run(call.run())
    kinds = [m["type"] for m in ws.out]
    assert (
        kinds[0] == "ready"
        and "heard" in kinds
        and "said" in kinds
        and "turn_complete" in kinds
    )
    said = next(m["text"] for m in ws.out if m["type"] == "said")
    assert said.startswith("Son las tres") and len(ws.audio) >= 2
    latency = next(m for m in ws.out if m["type"] == "latency")
    assert latency["voz"] == "propia" and latency["sergio_ms"] >= 0


def test_typed_text_is_answered_too(monkeypatch):
    monkeypatch.setattr(V, "warm", lambda: None)
    monkeypatch.setattr(V, "speak_pcm", lambda text, speed=1.05: b"\0\0")
    ws = _WS(
        [
            {
                "type": "websocket.receive",
                "text": json.dumps({"type": "text", "text": "hola"}),
            }
        ]
    )
    asyncio.run(
        V.OwnVoiceCall(
            ws, {"type": "start"}, think=lambda t, h, s: "Hola, señor."
        ).run()
    )
    assert any(m["type"] == "said" and m["text"] == "Hola, señor." for m in ws.out)

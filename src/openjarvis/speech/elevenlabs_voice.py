"""ElevenLabs voice for Sergio: streamed, the lowest delay we have.

The voice is "J Thomas — Warm, Raspy & Real", an original voice from the
ElevenLabs library (deep, warm, a rasp in the low register, relaxed). It is
not a copy of any real person's voice. Flash v2.5 starts speaking in about
a tenth of a second; it reads Spanish with its own accent.

Needs ``ELEVENLABS_API_KEY`` (``sergio nube voz --elevenlabs CLAVE``). Without
it, or out of credit, Sergio uses Gemini's Algenib voice.
"""

from __future__ import annotations

import io
import os
import wave
from typing import AsyncIterator

API = "https://api.elevenlabs.io/v1"
VOICE_ID = "f5gk6ENs9vgDBvfkTj7e"  # J Thomas — Warm, Raspy & Real
VOICE_NAME = "J Thomas - Warm, Raspy & Real"
MODEL = "eleven_flash_v2_5"
RATE = 24000
SETTINGS = {
    "stability": 0.42,  # some life in the delivery
    "similarity_boost": 0.85,
    "style": 0.15,
    "use_speaker_boost": True,
    "speed": 0.97,  # relaxed, never rushed
}


def key() -> str:
    found = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not found:
        raise RuntimeError("Falta ELEVENLABS_API_KEY (sergio nube voz --elevenlabs CLAVE)")
    return found


def voice_of(name: str) -> str:
    """'elevenlabs:ID' or 'ID' -> ID (the default voice when empty)."""
    return name.split(":", 1)[-1].strip() or VOICE_ID


def request(text: str, voice: str) -> tuple[str, dict, dict]:
    url = f"{API}/text-to-speech/{voice_of(voice)}/stream"
    params = {"output_format": f"pcm_{RATE}", "optimize_streaming_latency": "3"}
    body = {
        "text": text[:2500],
        "model_id": MODEL,
        "language_code": "es",
        "voice_settings": SETTINGS,
    }
    return url, params, body


async def stream_pcm(text: str, voice: str = "") -> AsyncIterator[bytes]:
    """Raw PCM 24 kHz int16 chunks as ElevenLabs makes them."""
    import httpx

    url, params, body = request(text, voice)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5)) as http:
        async with http.stream("POST", url, params=params, json=body,
                               headers={"xi-api-key": key()}) as resp:
            if resp.status_code != 200:
                detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                raise RuntimeError(f"ElevenLabs {resp.status_code}: {detail}")
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk


def speak_wav(text: str, voice: str = "") -> bytes:
    """The whole sentence as a WAV (for the non-streamed path)."""
    import httpx

    url, params, body = request(text, voice)
    resp = httpx.post(url, params=params, json=body, headers={"xi-api-key": key()},
                      timeout=httpx.Timeout(30, connect=5))
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs {resp.status_code}: {resp.text[:300]}")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(resp.content)
    return buf.getvalue()


__all__ = ["VOICE_ID", "VOICE_NAME", "speak_wav", "stream_pcm", "voice_of"]

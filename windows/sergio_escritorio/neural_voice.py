"""Natural voice: Microsoft's neural voices (the ones in Edge "Read aloud").

Free, no key, much more human than a small local TTS. Needs internet; when
it fails Sergio falls back to the local voice on the server.
"""

from __future__ import annotations

import asyncio
import io
import wave

# Voices worth offering (id, label). Sergio is a man: only men's voices are
# offered, and "gemini:" voices are his own (Gemini TTS, via the server). The
# old "Predeterminada" choice is gone: Gemini's own default can be a woman's
# (a saved one still works and means Algenib, see gemini_voice.sergio_voice).
VOICES = [
    ("gemini:Algenib", "Sergio: masculina, grave y relajada (ronca)"),
    ("elevenlabs:f5gk6ENs9vgDBvfkTj7e", "Grave, cálida y rasposa (ElevenLabs, la más rápida; necesita clave)"),
    ("gemini:Algieba", "Sergio británico (suave)"),
    ("gemini:Charon", "Sergio británico (informativo)"),
    ("gemini:Sadaltager", "Sergio británico (erudito)"),
    ("gemini:Orus", "Sergio británico (firme)"),
    ("es-ES-AlvaroNeural", "Álvaro (España)"),
    ("es-EC-LuisNeural", "Luis (Ecuador)"),
    ("es-MX-JorgeNeural", "Jorge (México)"),
    ("es-CO-GonzaloNeural", "Gonzalo (Colombia)"),
    ("es-AR-TomasNeural", "Tomás (Argentina)"),
    ("en-GB-RyanNeural", "Ryan (English, UK)"),
    ("en-US-AndrewNeural", "Andrew (English, US)"),
    ("pt-BR-AntonioNeural", "Antônio (Português, Brasil)"),
    ("fr-FR-HenriNeural", "Henri (Français)"),
    ("de-DE-ConradNeural", "Conrad (Deutsch)"),
    ("it-IT-DiegoNeural", "Diego (Italiano)"),
]
DEFAULT_VOICE = "gemini:Algenib"  # male, deep, relaxed and husky; calls too
EDGE_FALLBACK = "es-ES-AlvaroNeural"  # closest free voice when Gemini fails
FALLBACKS = {  # the same, in each language Sergio speaks (male, calm)
    "es": EDGE_FALLBACK, "en": "en-GB-RyanNeural", "pt": "pt-BR-AntonioNeural",
    "fr": "fr-FR-HenriNeural", "de": "de-DE-ConradNeural", "it": "it-IT-DiegoNeural",
}


def fallback_voice(language: str) -> str:
    return FALLBACKS.get(language, EDGE_FALLBACK)


async def _mp3(text: str, voice: str, rate: str) -> bytes:
    import edge_tts

    out = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
        if chunk.get("type") == "audio":
            out += chunk["data"]
    if not out:
        raise RuntimeError("the neural voice returned no audio")
    return bytes(out)


def mp3_to_wav(mp3: bytes, rate: int = 24_000) -> bytes:
    """Decode MP3 to 16-bit mono WAV (Windows plays WAV natively)."""
    import av

    pcm = bytearray()
    with av.open(io.BytesIO(mp3)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                pcm += bytes(out.planes[0])[: out.samples * 2]
        for out in resampler.resample(None):
            pcm += bytes(out.planes[0])[: out.samples * 2]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(pcm))
    return buf.getvalue()


def synthesize(text: str, voice: str = DEFAULT_VOICE, rate: str = "+0%") -> bytes:
    """WAV bytes of *text* spoken by *voice*."""
    return mp3_to_wav(asyncio.run(_mp3(text[:3000], voice, rate)))


__all__ = ["DEFAULT_VOICE", "VOICES", "fallback_voice", "mp3_to_wav", "synthesize"]

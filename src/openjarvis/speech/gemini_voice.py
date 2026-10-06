"""Sergio's voice and ears through Gemini (needs GEMINI_API_KEY).

* :func:`speak` — Gemini text-to-speech with a style instruction: a refined,
  very intelligent British gentleman of about forty, warm and crisp.
* :func:`transcribe` — Gemini listens to a short WAV and writes exactly what
  was said (much better than a small CPU Whisper with laptop microphones).
"""

from __future__ import annotations

import io
import os
import wave
from typing import Any

TTS_MODELS = (
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-pro-preview-tts",
    "gemini-2.5-flash-preview-tts",
    # Newer voices read the style note aloud: they get the plain text only.
    "gemini-3.8-flash-tts",
    "gemini-3.8-flash-lite-tts",
)
PLAIN_TEXT_TTS = {"gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"}
# Fastest first: Flash-Lite with minimal thinking transcribes in well under a
# second; the bigger Flash models are the backup.
EAR_MODELS = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)
VOICES = {  # Gemini prebuilt voices that fit Sergio (male, adult)
    "Algieba": "Sergio (suave)",
    "Charon": "Sergio (informativo)",
    "Sadaltager": "Sergio (erudito)",
    "Orus": "Sergio (firme)",
    "Iapetus": "Sergio (claro)",
}
DEFAULT_VOICE = "Algieba"
STYLE = (
    "Lee en español, con una voz masculina grave y relajada, algo rasposa y "
    "cálida, de unos cuarenta años: segura, carismática, con media sonrisa y "
    "una ironía amable. Dicción nítida y humana, a ritmo pausado y "
    "conversacional, con pausas naturales, nunca deprisa ni como locutor. "
    "Di exactamente esto:"
)
EAR_PROMPT = (
    "Transcribe exactamente lo que dice la persona en este audio (español; deja "
    "las palabras en inglés como se dicen). Responde solo con la transcripción, "
    "sin comillas ni comentarios. Si no se entiende nada, responde vacío."
)

_CLIENT: Any = None


def _client() -> Any:
    from openjarvis.engine.google_client import SwitchingClient

    global _CLIENT
    key = (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    ).strip()
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY (sergio nube configurar --gemini …)")
    if _CLIENT is None or _CLIENT.key != key:
        _CLIENT = SwitchingClient(key)
    return _CLIENT


def pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm)
    return buf.getvalue()


def _rate(mime: str) -> int:
    for part in (mime or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == "rate" and value.isdigit():
            return int(value)
    return 24000


def speak(text: str, voice: str = DEFAULT_VOICE, style: str = STYLE) -> bytes:
    """WAV of *text* in Sergio's voice."""
    from google.genai import types

    text = " ".join(text.split())[:2500]
    if not text:
        raise ValueError("Nada que decir.")
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice if voice in VOICES else DEFAULT_VOICE
                )
            )
        ),
    )
    last: Exception | None = None
    for model in TTS_MODELS:
        try:
            prompt = text if model in PLAIN_TEXT_TTS else f"{style}\n{text}"
            resp = _client().models.generate_content(
                model=model, contents=prompt, config=config
            )
            for part in resp.candidates[0].content.parts:
                blob = getattr(part, "inline_data", None)
                if blob is not None and blob.data:
                    mime = blob.mime_type or ""
                    if "wav" in mime:
                        return bytes(blob.data)
                    return pcm_to_wav(bytes(blob.data), _rate(mime))
            last = RuntimeError(f"{model} no devolvió audio")
        except Exception as exc:  # noqa: BLE001 — try the next model
            last = exc
    raise RuntimeError(f"La voz de Gemini falló: {last}")


def transcribe(wav: bytes) -> str:
    """What was said in a short WAV clip (Spanish)."""
    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs

    last: Exception | None = None
    for model in EAR_MODELS:
        try:
            resp = _client().models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=wav, mime_type="audio/wav"),
                    EAR_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    **google_config_kwargs(model, 0.0, 512, "minimal")
                ),
            )
            return clean_transcript(str(resp.text or ""))
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"El oído de Gemini falló: {last}")


def clean_transcript(text: str) -> str:
    text = text.strip().strip('"“”«»').strip()
    if text.lower() in ("", "vacío", "vacio", "(vacío)", "[vacío]", "nada"):
        return ""
    return text


__all__ = ["DEFAULT_VOICE", "VOICES", "pcm_to_wav", "speak", "transcribe"]

"""Sergio's own voice as a text-to-speech backend (Gemini, a male voice).

The chat's "read aloud" and autoplay used another engine's voice, so the same
Sergio sounded different (sometimes like a woman) than in the live call. This
backend uses the very same voice as the call, through :mod:`gemini_voice`, and
needs only the Gemini key the call already uses. After a quota error it steps
aside for 15 minutes so the next backend answers instead of every request
waiting for a failing one.
"""

from __future__ import annotations

import time
from typing import List

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech import gemini_voice
from openjarvis.speech.tts import TTSBackend, TTSResult

QUOTA_PAUSE_SECONDS = 15 * 60
_paused_until = [0.0]


def _has_key() -> bool:
    import os

    return bool(
        (
            os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        ).strip()
    )


@TTSRegistry.register("gemini")
class GeminiTTSBackend(TTSBackend):
    """Sergio's Gemini voice (the same one as in the live call)."""

    backend_id = "gemini"

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "mp3",
    ) -> TTSResult:
        voice = gemini_voice.sergio_voice(voice_id)
        try:
            wav = gemini_voice.speak(text, voice)
        except Exception as exc:
            if any(w in str(exc).lower() for w in ("quota", "429", "exhausted")):
                _paused_until[0] = time.monotonic() + QUOTA_PAUSE_SECONDS
            raise
        return TTSResult(
            audio=wav,
            format="wav",
            voice_id=voice,
            sample_rate=24000,
            metadata={"backend": "gemini"},
        )

    def available_voices(self) -> List[str]:
        return list(gemini_voice.VOICES)

    def health(self) -> bool:
        return _has_key() and time.monotonic() >= _paused_until[0]


__all__ = ["GeminiTTSBackend"]

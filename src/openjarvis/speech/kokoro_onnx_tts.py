"""Kokoro text-to-speech through ``kokoro-onnx`` (no PyTorch needed).

The ``phone`` extra already installs ``kokoro-onnx`` for calls, so Sergio can
speak in the chat with the same Spanish voices without the heavy ``kokoro``
(PyTorch) package. Model files are shared with the phone pipeline's cache.
"""

from __future__ import annotations

import io
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, List

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult

_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")
_DEFAULT_VOICE_ID = "em_alex"

# Voice prefix → espeak-ng language used by kokoro-onnx.
_PREFIX_TO_LANG = {
    "a": "en-us",
    "b": "en-gb",
    "e": "es",
    "f": "fr-fr",
    "h": "hi",
    "i": "it",
    "j": "ja",
    "p": "pt-br",
    "z": "cmn",
}


def cache_dir() -> Path:
    return Path(os.path.expanduser("~/.cache/pipecat/kokoro-onnx"))


def _download(url: str, dest: Path) -> None:
    import httpx

    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out, httpx.stream(
            "GET", url, follow_redirects=True, timeout=300
        ) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                out.write(chunk)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@TTSRegistry.register("kokoro_onnx")
class KokoroOnnxTTSBackend(TTSBackend):
    backend_id = "kokoro_onnx"

    def __init__(self, **_: Any) -> None:
        self._kokoro: Any | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> Any:
        with self._lock:
            if self._kokoro is not None:
                return self._kokoro
            try:
                from kokoro_onnx import Kokoro
            except ImportError as exc:
                raise RuntimeError(
                    "kokoro-onnx not installed (uv sync --extra phone)"
                ) from exc
            paths = [cache_dir() / name for name in _FILES]
            for path in paths:
                if not path.exists():
                    _download(f"{_RELEASE}/{path.name}", path)
            self._kokoro = Kokoro(str(paths[0]), str(paths[1]))
            return self._kokoro

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = _DEFAULT_VOICE_ID,
        speed: float = 1.0,
        output_format: str = "wav",
    ) -> TTSResult:
        import soundfile as sf

        kokoro = self._ensure()
        voice = voice_id if voice_id in kokoro.voices else _DEFAULT_VOICE_ID
        lang = _PREFIX_TO_LANG.get(voice[:1], "en-us")
        with self._lock:
            samples, rate = kokoro.create(text, voice=voice, speed=speed, lang=lang)
        fmt = "wav" if output_format == "mp3" else output_format
        buf = io.BytesIO()
        sf.write(buf, samples, rate, format=fmt.upper())
        return TTSResult(
            audio=buf.getvalue(),
            format=fmt,
            voice_id=voice,
            sample_rate=rate,
            duration_seconds=len(samples) / rate,
            metadata={"backend": "kokoro_onnx", "lang": lang},
        )

    def available_voices(self) -> List[str]:
        try:
            return sorted(self._ensure().voices)
        except Exception:  # noqa: BLE001
            return ["em_alex", "em_santa", "ef_dora"]

    def health(self) -> bool:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False
        return True


__all__ = ["KokoroOnnxTTSBackend"]

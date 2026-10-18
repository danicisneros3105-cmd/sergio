"""Speech endpoints (``/v1/speech``): transcription, text-to-speech and their
health checks.

Split out of ``api_routes.py``, which owns the router; its names are looked
up on that module, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from fastapi import Request

import openjarvis.server.api_routes as _api


@_api.speech_router.post("/transcribe")
async def transcribe_speech(request: Request):
    """Transcribe uploaded audio to text."""
    backend = getattr(request.app.state, "speech_backend", None)
    if backend is None:
        # The model download may have failed at startup (no internet yet):
        # try again now instead of staying deaf until a restart.
        config = getattr(request.app.state, "config", None)
        if config is not None:
            from openjarvis.speech._discovery import get_speech_backend

            backend = await _api.asyncio.to_thread(get_speech_backend, config)
            request.app.state.speech_backend = backend
    if backend is None:
        raise _api.HTTPException(
            status_code=501, detail="Speech backend not configured"
        )

    form = await request.form()
    audio_file = form.get("file")
    if audio_file is None:
        raise _api.HTTPException(status_code=400, detail="Missing 'file' field")

    audio_bytes = await audio_file.read()
    language = form.get("language")

    # Detect format from filename
    filename = getattr(audio_file, "filename", "audio.wav")
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "wav"

    try:
        result = await _api.asyncio.to_thread(
            backend.transcribe,
            audio_bytes,
            format=ext,
            language=language or None,
        )
    except Exception as exc:
        _api.logger.exception("Speech transcription failed")
        raise _api.HTTPException(
            status_code=500,
            detail=f"Speech transcription failed: {exc}",
        ) from exc

    return {
        "text": result.text,
        "language": result.language,
        "confidence": result.confidence,
        "duration_seconds": result.duration_seconds,
    }


@_api.speech_router.get("/health")
async def speech_health(request: Request):
    """Check if a speech backend is available."""
    backend = getattr(request.app.state, "speech_backend", None)
    if backend is None:
        return {"available": False, "reason": "No speech backend configured"}
    try:
        available = backend.health()
        reason = None
    except Exception as exc:
        _api.logger.exception("Speech health check failed")
        available = False
        reason = str(exc)

    if not available and reason is None:
        last_error = getattr(backend, "last_error", None)
        if callable(last_error):
            reason = last_error()

    return {
        "available": available,
        "backend": backend.backend_id,
        **({"reason": reason} if reason else {}),
    }


async def _resolve_tts_backend(request: Request):
    """Return a healthy TTS backend, resolved once and cached on app state.

    Backends load models on construction, so this stays lazy: a server whose
    users never ask for audio never pays for it.
    """
    app = request.app
    if getattr(app.state, "tts_resolved", False):
        return getattr(app.state, "tts_backend", None)

    # The first health probe can load Kokoro's model. A shared task keeps that
    # work off the event loop and coalesces concurrent probes, including when
    # the backend is unavailable. A later request may retry that failure.
    task = getattr(app.state, "tts_resolution_task", None)
    if task is None:

        def discover():
            from openjarvis.speech._tts_discovery import (
                get_tts_backend,
                voice_preferences,
            )

            config = getattr(app.state, "config", None)
            if config is None:
                from openjarvis.core.config import load_config

                config = load_config()

            preferred, _, _ = voice_preferences(config)
            return get_tts_backend(preferred)

        task = _api.asyncio.create_task(_api.asyncio.to_thread(discover))
        app.state.tts_resolution_task = task

    try:
        backend = await _api.asyncio.shield(task)
    finally:
        if task.done() and getattr(app.state, "tts_resolution_task", None) is task:
            app.state.tts_resolution_task = None

    if backend is not None:
        app.state.tts_backend = backend
        app.state.tts_resolved = True
    return backend


def _tts_voice_and_speed(request: Request, backend) -> tuple[str, float]:
    """Resolve the voice ID and speed to use with *backend*.

    Voice IDs are not portable between backends, so a configured ``voice_id``
    applies only when the resolved backend is the configured one; otherwise the
    fallback backend's own default is used.
    """
    from openjarvis.speech._tts_discovery import default_voice_for, voice_preferences

    config = getattr(request.app.state, "config", None)
    if config is None:
        return "", 1.0

    preferred, voice_id, speed = voice_preferences(config)
    active = getattr(backend, "backend_id", "")
    if active and active != preferred:
        voice_id = default_voice_for(active)
    return voice_id, speed


async def _fallback_synthesis(failed, text: str, speed: float):
    """Try the next healthy backend after *failed*; None when none works."""
    from openjarvis.speech._tts_discovery import default_voice_for, get_tts_backend

    tried = {getattr(failed, "backend_id", "")}
    for _ in range(4):
        other = await _api.asyncio.to_thread(get_tts_backend, "", attempted=tried)
        if other is None:
            return None
        try:
            return await _api.asyncio.to_thread(
                other.synthesize,
                text,
                voice_id=default_voice_for(other.backend_id),
                speed=speed,
                output_format="wav",
            )
        except Exception:  # noqa: BLE001 — the next one
            _api.logger.exception("Fallback speech synthesis failed")
    return None


@_api.speech_router.post("/synthesize")
async def synthesize_speech(request: Request, body: _api.SpeechSynthesizeRequest):
    """Synthesize text to speech and return the audio as WAV."""
    text = body.text.strip()
    if not text:
        raise _api.HTTPException(status_code=400, detail="Missing 'text'")
    if len(text) > _api._MAX_TTS_CHARS:
        raise _api.HTTPException(
            status_code=413,
            detail=f"Text exceeds {_api._MAX_TTS_CHARS} characters",
        )

    backend = await _api._resolve_tts_backend(request)
    if backend is None:
        raise _api.HTTPException(
            status_code=501, detail="No text-to-speech backend available"
        )

    voice_id, speed = _api._tts_voice_and_speed(request, backend)
    if body.voice_id:
        voice_id = body.voice_id
    if body.speed is not None:
        speed = body.speed

    try:
        result = await _api.asyncio.to_thread(
            backend.synthesize,
            text,
            voice_id=voice_id,
            speed=speed,
            output_format="wav",
        )
    except Exception as exc:
        _api.logger.exception("Speech synthesis failed")
        # Sergio's Gemini voice may be out of quota: the next healthy backend
        # reads it instead of the reply staying silent.
        result = await _fallback_synthesis(backend, text, speed)
        if result is None:
            raise _api.HTTPException(
                status_code=500, detail="Speech synthesis failed"
            ) from exc

    return _api.Response(
        content=result.audio,
        media_type="audio/wav",
        headers={
            "X-Voice-Id": result.voice_id or voice_id,
            "X-Sample-Rate": str(result.sample_rate),
        },
    )


@_api.speech_router.get("/tts/health")
async def tts_health(request: Request):
    """Report whether voice output is available, and with which voice."""
    backend = await _api._resolve_tts_backend(request)
    if backend is None:
        return {"available": False, "reason": "No text-to-speech backend available"}

    voice_id, speed = _api._tts_voice_and_speed(request, backend)
    return {
        "available": True,
        "backend": getattr(backend, "backend_id", ""),
        "voice_id": voice_id,
        "speed": speed,
    }


__all__ = [
    "transcribe_speech",
    "speech_health",
    "_resolve_tts_backend",
    "_tts_voice_and_speed",
    "synthesize_speech",
    "tts_health",
]

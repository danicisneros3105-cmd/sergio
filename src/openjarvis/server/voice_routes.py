"""Sergio's Gemini voice and ears for the Windows companion.

* ``POST /v1/voice/speak`` {text, voice} -> audio/wav
* ``POST /v1/voice/transcribe`` (multipart "file": WAV) -> {"text": ...}
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter(prefix="/v1/voice", tags=["voice"])
MAX_AUDIO = 8 * 1024 * 1024


def preferred(voice: str) -> str:
    """With an ElevenLabs key saved (sergio nube voz), Sergio's default male
    voice is spoken by ElevenLabs: same character, lower delay."""
    import os

    if voice.lower() in ("", "algenib") and os.environ.get("ELEVENLABS_API_KEY", "").strip():
        if os.environ.get("SERGIO_VOICE", "elevenlabs").lower() == "elevenlabs":
            return "elevenlabs:"
    return voice


class SpeakRequest(BaseModel):
    text: str
    voice: str = ""


@router.post("/speak")
async def speak(req: SpeakRequest) -> Response:
    from openjarvis.speech import gemini_voice

    req = SpeakRequest(text=req.text, voice=preferred(req.voice))
    if req.voice.lower().startswith("elevenlabs"):
        from openjarvis.speech import elevenlabs_voice

        try:
            wav = await asyncio.to_thread(elevenlabs_voice.speak_wav, req.text, req.voice)
            return Response(content=wav, media_type="audio/wav")
        except Exception:  # noqa: BLE001 — no key / no credit: Algenib
            req = SpeakRequest(text=req.text, voice="algenib")
    if req.voice.lower() in ("", "predeterminada", "default", "algenib"):
        # Gemini Live's voice, the same as in calls.
        from openjarvis.speech.gemini_live import speak_live

        try:
            wav = await asyncio.to_thread(speak_live, req.text, "" if req.voice.lower() in ("", "predeterminada", "default") else req.voice)
            return Response(content=wav, media_type="audio/wav")
        except Exception as exc:  # noqa: BLE001 — the TTS models next
            live_error = str(exc)
        try:
            wav = await asyncio.to_thread(gemini_voice.speak, req.text, "Predeterminada")
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"{live_error} | {exc}"[:500]) from exc
        return Response(content=wav, media_type="audio/wav")
    try:
        wav = await asyncio.to_thread(
            gemini_voice.speak, req.text, req.voice or gemini_voice.DEFAULT_VOICE
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=wav, media_type="audio/wav")


@router.post("/stream")
async def stream(req: SpeakRequest) -> Any:
    """Gemini Live reading the text aloud, streamed as raw PCM (24 kHz, int16)
    so the companion starts playing within a second."""
    from fastapi.responses import StreamingResponse

    from openjarvis.speech.gemini_live import stream_live

    voice = preferred(req.voice)
    voice = "" if voice.lower() in ("", "predeterminada", "default") else voice
    first = b""
    if voice.lower().startswith("elevenlabs"):
        from openjarvis.speech.elevenlabs_voice import stream_pcm

        chunks = stream_pcm(req.text, voice)
        try:
            first = await chunks.__anext__()
        except Exception:  # noqa: BLE001 — no key / no credit: Gemini's Algenib
            voice = "Algenib"
    if not first:
        chunks = stream_live(req.text, voice)
    try:
        first = first or await chunks.__anext__()
    except StopAsyncIteration:
        raise HTTPException(status_code=502, detail="La voz de Gemini Live no devolvió audio.")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc

    async def body():
        yield first
        async for chunk in chunks:
            yield chunk

    return StreamingResponse(body(), media_type="audio/L16;rate=24000")


class ChatRequest(BaseModel):
    model: str
    messages: list[dict[str, str]]
    max_tokens: int = 400


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> dict[str, Any]:
    """Fast conversation: straight to the model, no agent and no tools.

    The companion uses it for chatting ("¿cómo estás?", "cuéntame algo"),
    which then answers in about a second instead of running the full agent.
    """
    from openjarvis.core.types import Message, Role

    engine = request.app.state.engine
    roles = {"system": Role.SYSTEM, "user": Role.USER, "assistant": Role.ASSISTANT}
    messages = [
        Message(
            role=roles.get(m.get("role", "user"), Role.USER),
            content=m.get("content", ""),
        )
        for m in req.messages
        if m.get("content")
    ]
    try:
        result = await asyncio.to_thread(
            engine.generate,
            messages,
            model=req.model,
            temperature=0.7,
            max_tokens=req.max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 — the companion falls back
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    return {"content": str(result.get("content") or "").strip()}


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict[str, Any]:
    from openjarvis.speech import gemini_voice

    data = await file.read(MAX_AUDIO + 1)
    if len(data) > MAX_AUDIO:
        raise HTTPException(status_code=413, detail="Audio too long")
    try:
        text = await asyncio.to_thread(gemini_voice.transcribe, data)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"text": text}


__all__ = ["router"]

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


class SpeakRequest(BaseModel):
    text: str
    voice: str = ""


@router.post("/speak")
async def speak(req: SpeakRequest) -> Response:
    from openjarvis.speech import gemini_voice

    try:
        wav = await asyncio.to_thread(
            gemini_voice.speak, req.text, req.voice or gemini_voice.DEFAULT_VOICE
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=wav, media_type="audio/wav")


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

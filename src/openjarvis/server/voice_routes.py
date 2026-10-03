"""Sergio's Gemini voice and ears for the Windows companion.

* ``POST /v1/voice/speak`` {text, voice} -> audio/wav
* ``POST /v1/voice/transcribe`` (multipart "file": WAV) -> {"text": ...}
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
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

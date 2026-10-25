"""``/v1/meeting/summarize``: the minutes of a meeting, call or conversation.

The companion sends the mixed audio (OGG or WAV) and the timeline of who
spoke when (from the voices it knows); Gemini writes the transcript with
names, summary, decisions and tasks. See :mod:`openjarvis.tools.meeting_notes`.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(tags=["meeting"])

MAX_AUDIO = 200 * 1024 * 1024  # ~20 hours of OGG: plenty


@router.post("/v1/meeting/summarize")
async def summarize(
    audio: UploadFile = File(...),
    timeline: str = Form(""),
    kind: str = Form("reunión"),
    when: str = Form(""),
    seconds: float = Form(0.0),
    speakers: str = Form(""),
) -> dict[str, Any]:
    from openjarvis.faces.routes import owner_name
    from openjarvis.tools.meeting_notes import by_person, to_markdown
    from openjarvis.tools.meeting_notes import summarize as write_minutes

    data = await audio.read(MAX_AUDIO + 1)
    if not data or len(data) > MAX_AUDIO:
        raise HTTPException(status_code=413, detail="Audio vacío o demasiado grande")
    mime = audio.content_type or "audio/ogg"
    try:
        names = (
            [s for s in json.loads(speakers) if isinstance(s, str)] if speakers else []
        )
    except ValueError:
        names = []
    try:
        minutes = await asyncio.to_thread(
            write_minutes, data, mime, timeline, owner=owner_name(), kind=kind
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        **minutes,
        "personas": by_person(minutes),
        "markdown": to_markdown(minutes, when=when, seconds=seconds, speakers=names),
    }


__all__ = ["router"]

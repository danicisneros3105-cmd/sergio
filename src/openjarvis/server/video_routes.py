"""Direct endpoints for the Video workspace, without a chat turn."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/video", tags=["video"])


class VideoCreateRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=600)
    seconds: int = Field(default=60, ge=15, le=1800)
    aspect: str = "9:16"
    mode: str = "basic"
    reference: str = Field(default="", max_length=2000)
    tendencias_en_vivo: bool = False


class VideoPlanRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=2000)
    seconds: int = Field(default=60, ge=6, le=720)
    aspect: str = "9:16"
    reference: str = Field(default="", max_length=2000)


def _execute(request: Request, tool: Any, params: dict[str, Any]) -> Any:
    from openjarvis.security.runtime import execute_secured_tool

    state = request.app.state
    return execute_secured_tool(
        tool,
        params,
        bus=getattr(state, "bus", None),
        capability_policy=getattr(state, "capability_policy", None),
        rate_limiter=getattr(state, "rate_limiter", None),
        agent_id="server:video",
    )


@router.post("/jobs")
async def create_video(body: VideoCreateRequest, request: Request) -> dict[str, Any]:
    """Start a generated video from the Video screen."""
    if body.aspect not in {"9:16", "16:9", "1:1"}:
        raise HTTPException(400, "Elige formato vertical, horizontal o cuadrado.")
    if body.mode not in {"basic", "post", "cinema"}:
        raise HTTPException(400, "Elige un modo de creación válido.")
    from openjarvis.tools.video_essay_tool import VideoEssayTool

    params = {
        "action": "start",
        "topic": body.idea.strip(),
        "seconds": body.seconds,
        "aspect": body.aspect,
        "mode": body.mode,
        "reference": body.reference.strip(),
        "tendencias_en_vivo": body.tendencias_en_vivo,
    }
    result = await asyncio.to_thread(_execute, request, VideoEssayTool(), params)
    if not result.success:
        raise HTTPException(422, result.content)
    job_id = str((result.metadata or {}).get("job") or "")
    if not job_id:
        raise HTTPException(409, result.content or "No pude iniciar el video.")
    return {
        "job_id": job_id,
        "content": result.content,
        "reused": bool((result.metadata or {}).get("reused")),
    }


@router.post("/plans")
async def create_video_plan(body: VideoPlanRequest, request: Request) -> dict[str, Any]:
    """Create a filmable shot list and animatic from the Video screen."""
    if body.aspect not in {"9:16", "16:9", "1:1"}:
        raise HTTPException(400, "Elige formato vertical, horizontal o cuadrado.")
    from openjarvis.tools.planear_tool import PlanearVideoTool

    result = await asyncio.to_thread(
        _execute,
        request,
        PlanearVideoTool(),
        {
            "action": "crear",
            "idea": body.idea.strip(),
            "segundos": body.seconds,
            "formato": "horizontal" if body.aspect == "16:9" else "vertical",
            "referencia": body.reference.strip(),
        },
    )
    if not result.success:
        raise HTTPException(422, result.content)
    match = re.search(r"\[\[plan:([\w-]+)\]\]", result.content or "")
    if not match:
        raise HTTPException(409, result.content or "No pude crear el plan.")
    return {"plan_id": match.group(1), "content": result.content}


__all__ = ["router"]

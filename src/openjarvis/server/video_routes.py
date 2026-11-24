"""Direct endpoints for the Video workspace, without a chat turn."""

from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/video", tags=["video"])


class VideoCreateRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=600)
    seconds: int = Field(default=60, ge=15, le=1800)
    aspect: str = "9:16"
    mode: str = "basic"
    reference: str = Field(default="", max_length=2000)
    tendencias_en_vivo: bool = False
    galeria_id: str = Field(default="", max_length=32)
    ultimos_clips: int = Field(default=0, ge=0, le=20)
    carpeta_clips: str = Field(default="", max_length=500)
    voz_modo: str = "auto"
    video_boost: bool = False


class VideoPlanRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=2000)
    seconds: int = Field(default=60, ge=6, le=720)
    aspect: str = "9:16"
    reference: str = Field(default="", max_length=2000)


class VideoAnalyticsRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=120)
    platform: str = ""
    published_id: str = Field(default="", max_length=200)


class VideoScheduleRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=600)
    cada_horas: int = Field(default=24, ge=1, le=168)
    modo: str = "basic"
    formato: str = "9:16"
    segundos: int = Field(default=60, ge=15, le=1800)
    publicar_en: list[str] = Field(default_factory=list)
    auto: bool = False


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
    """Start a generated or gallery-based video from the Video screen."""
    if body.aspect not in {"9:16", "16:9", "1:1"}:
        raise HTTPException(400, "Elige formato vertical, horizontal o cuadrado.")
    if body.mode not in {"basic", "post", "cinema"}:
        raise HTTPException(400, "Elige un modo de creación válido.")
    if body.voz_modo not in {"auto", "elevenlabs", "propia", "ninguna"}:
        raise HTTPException(400, "Elige un modo de voz válido.")
    gallery_id = body.galeria_id.strip()
    if body.ultimos_clips:
        if gallery_id:
            raise HTTPException(400, "Elige clips subidos o los últimos clips locales, no ambos.")
        from openjarvis.video_essay import galeria
        try:
            local = galeria.recent_local_clips(body.ultimos_clips, body.carpeta_clips.strip() or None)
            gallery_id = galeria.store(local)
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
    if gallery_id:
        from openjarvis.video_essay import galeria
        try:
            galeria.sources(gallery_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    from openjarvis.tools.video_essay_tool import VideoEssayTool

    params = {
        "action": "start", "topic": body.idea.strip(), "seconds": body.seconds,
        "aspect": body.aspect, "mode": body.mode, "reference": body.reference.strip(),
        "tendencias_en_vivo": body.tendencias_en_vivo, "galeria_id": gallery_id,
        "voz_modo": body.voz_modo, "video_boost": body.video_boost,
    }
    result = await asyncio.to_thread(_execute, request, VideoEssayTool(), params)
    if not result.success:
        raise HTTPException(422, result.content)
    job_id = str((result.metadata or {}).get("job") or "")
    if not job_id:
        raise HTTPException(409, result.content or "No pude iniciar el video.")
    return {"job_id": job_id, "content": result.content, "reused": bool((result.metadata or {}).get("reused"))}


@router.post("/plans")
async def create_video_plan(body: VideoPlanRequest, request: Request) -> dict[str, Any]:
    """Create a filmable shot list and animatic from the Video screen."""
    if body.aspect not in {"9:16", "16:9", "1:1"}:
        raise HTTPException(400, "Elige formato vertical, horizontal o cuadrado.")
    from openjarvis.tools.planear_tool import PlanearVideoTool

    result = await asyncio.to_thread(
        _execute, request, PlanearVideoTool(),
        {"action": "crear", "idea": body.idea.strip(), "segundos": body.seconds,
         "formato": "horizontal" if body.aspect == "16:9" else "vertical",
         "referencia": body.reference.strip()},
    )
    if not result.success:
        raise HTTPException(422, result.content)
    match = re.search(r"\[\[plan:([\w-]+)\]\]", result.content or "")
    if not match:
        raise HTTPException(409, result.content or "No pude crear el plan.")
    return {"plan_id": match.group(1), "content": result.content}


@router.post("/boost")
async def start_video_boost(clip: UploadFile = File(...)) -> dict[str, Any]:
    """Run actual Video Boost rendering as a trackable background task."""
    from openjarvis.video_essay import boost, render

    suffix = Path(clip.filename or "clip.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".m4v", ".webm"}:
        raise HTTPException(400, "Sube un video MP4, MOV, MKV, M4V o WebM.")
    temp = tempfile.NamedTemporaryFile(prefix="sergio-boost-upload-", suffix=suffix, delete=False)
    temp_path = Path(temp.name)
    size = 0
    try:
        with temp:
            while chunk := await clip.read(1024 * 1024):
                size += len(chunk)
                if size > 512 * 1024 * 1024:
                    raise HTTPException(413, "El video supera el límite de 512 MB.")
                temp.write(chunk)
        if size == 0:
            raise HTTPException(400, "El archivo de video está vacío.")
        boost_id = boost.start_boost(temp_path, ffmpeg=render.ffmpeg())
    except HTTPException:
        raise
    except (ValueError, OSError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)
        await clip.close()
    return {"boost_id": boost_id, "status": "queued"}


@router.get("/boost/limits")
def video_boost_limits() -> dict[str, Any]:
    from openjarvis.tiers import current
    from openjarvis.video_essay.boost import plan_limits
    plan = str(current().get("plan") or "free")
    return {"plan": plan, **plan_limits(plan)}


@router.get("/boost/{boost_id}")
def video_boost_status(boost_id: str) -> dict[str, Any]:
    from openjarvis.video_essay import boost
    try:
        state = boost.get_boost(boost_id)
    except ValueError as exc:
        raise HTTPException(404, "No encuentro ese Video Boost.") from exc
    if state is None:
        raise HTTPException(404, "No encuentro ese Video Boost.")
    return state


@router.get("/boost/{boost_id}/file")
def video_boost_file(boost_id: str) -> FileResponse:
    from openjarvis.video_essay import boost
    try:
        state = boost.get_boost(boost_id)
        path = boost._job_dir(boost_id) / "video-boost.mp4"
    except ValueError as exc:
        raise HTTPException(404, "No encuentro ese Video Boost.") from exc
    if not state or state.get("status") != "done" or not path.is_file():
        raise HTTPException(409, "El video todavía no está listo.")
    return FileResponse(path, media_type="video/mp4", filename="video-boost.mp4")


@router.get("/cola")
def video_queue() -> dict[str, Any]:
    from openjarvis.video_essay import job as jobs
    rows = []
    for item in jobs.all_jobs():
        state = item.state()
        if state.get("status") in {"listo", "en curso", "error"}:
            result = state.get("result") or {}
            package = result.get("package") or {}
            rows.append({"job_id": item.id, "status": state.get("status"), "stage": state.get("stage"),
                         "progress": state.get("stage_progress"), "title": package.get("title") or state.get("title", ""),
                         "video": result.get("url", ""), "published": bool(state.get("publicado"))})
    return {"items": rows}


@router.get("/programados")
def video_schedules() -> dict[str, Any]:
    from openjarvis.video_essay import schedule
    return {"items": schedule.load(), "intervals": list(schedule.EVERY_HOURS)}


@router.post("/programados")
def add_video_schedule(body: VideoScheduleRequest) -> dict[str, Any]:
    from openjarvis.automatiza import canales
    from openjarvis.video_essay import schedule
    if body.formato not in {"9:16", "16:9", "1:1"}:
        raise HTTPException(400, "Elige formato vertical, horizontal o cuadrado.")
    channels = [item for item in body.publicar_en if item in {"youtube", "instagram"}]
    if body.auto:
        for name in channels:
            account = canales.account(name)
            key = "refresh_token" if name == "youtube" else "token"
            if not account.get(key):
                raise HTTPException(409, f"Conecta {name} antes de activar la publicación automática.")
        if not channels:
            raise HTTPException(400, "Conecta YouTube o Instagram para publicar automáticamente.")
    try:
        item = schedule.add(body.idea, every_hours=body.cada_horas, mode=body.modo,
                            aspect=body.formato, seconds=body.segundos,
                            publish_to=channels, auto=body.auto)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"item": item}


@router.post("/analitica")
async def video_analytics(body: VideoAnalyticsRequest) -> dict[str, Any]:
    from openjarvis.video_essay import analitica
    try:
        return await asyncio.to_thread(analitica.analyze_job, body.job_id,
                                       platform=body.platform, published_id=body.published_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/memoria")
def video_memory() -> dict[str, Any]:
    try:
        from openjarvis.evolution.memory import lessons, shared
        return {"stats": shared().stats(), "lessons": lessons("videos, retencion, gancho, edicion y publicacion", ("feedback", "video"))}
    except Exception as exc:
        return {"available": False, "error": str(exc)[:180], "lessons": ""}


__all__ = ["router"]

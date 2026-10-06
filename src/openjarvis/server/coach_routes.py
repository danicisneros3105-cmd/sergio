"""``/v1/coach/*``: profile, learning plans, lessons, video reviews, health
reports and the support conversation (see :mod:`openjarvis.coach`).

The companion keeps the user's data; these endpoints only think with it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/coach", tags=["coach"])

MAX_VIDEO = 150 * 1024 * 1024
MAX_IMAGE = 15 * 1024 * 1024


class ProfileRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    previous: dict[str, Any] = Field(default_factory=dict)


class PlanRequest(BaseModel):
    goal: str
    kind: str = "habilidad"
    profile: dict[str, Any] = Field(default_factory=dict)
    free_slots: list[str] = Field(default_factory=list)


class LessonRequest(BaseModel):
    goal: dict[str, Any]
    profile: dict[str, Any] = Field(default_factory=dict)


class AssessRequest(BaseModel):
    goal: dict[str, Any]
    results: str


class HealthRequest(BaseModel):
    data: dict[str, Any]


class TherapyRequest(BaseModel):
    messages: list[dict[str, str]]
    notes: list[dict[str, Any]] = Field(default_factory=list)
    profile: dict[str, Any] = Field(default_factory=dict)


async def _run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/profile")
async def profile(req: ProfileRequest) -> dict[str, Any]:
    from openjarvis.coach.tasks import update_profile

    return await _run(update_profile, req.context, req.previous)


@router.post("/plan")
async def plan(req: PlanRequest) -> dict[str, Any]:
    from openjarvis.coach.tasks import make_plan

    if not req.goal.strip():
        raise HTTPException(status_code=400, detail="¿Qué quieres aprender?")
    return await _run(make_plan, req.goal.strip(), req.kind, req.profile, req.free_slots)


@router.post("/lesson")
async def lesson(req: LessonRequest) -> dict[str, Any]:
    from openjarvis.coach.tasks import next_lesson

    return await _run(next_lesson, req.goal, req.profile)


@router.post("/assess")
async def assess(req: AssessRequest) -> dict[str, Any]:
    from openjarvis.coach.tasks import assess as grade

    return await _run(grade, req.goal, req.results)


@router.post("/review_video")
async def review_video(
    video: UploadFile = File(...), goal: str = Form(...), focus: str = Form("")
) -> dict[str, Any]:
    from openjarvis.coach.tasks import review_video as review

    data = await video.read(MAX_VIDEO + 1)
    if not data or len(data) > MAX_VIDEO:
        raise HTTPException(status_code=413, detail="Video vacío o demasiado grande")
    return await _run(review, data, video.content_type or "video/mp4", goal, focus)


@router.post("/school")
async def school(image: UploadFile = File(...)) -> dict[str, Any]:
    from openjarvis.coach.tasks import read_school

    data = await image.read(MAX_IMAGE + 1)
    if not data or len(data) > MAX_IMAGE:
        raise HTTPException(status_code=413, detail="Imagen vacía o demasiado grande")
    return await _run(read_school, data, image.content_type or "image/jpeg")


@router.post("/health")
async def health(req: HealthRequest) -> dict[str, Any]:
    from openjarvis.coach.tasks import health_report

    return await _run(health_report, req.data)


@router.post("/therapy")
async def therapy(req: TherapyRequest) -> dict[str, Any]:
    from openjarvis.coach.tasks import CRISIS, at_risk, therapy_turn

    last = next((m.get("content", "") for m in reversed(req.messages) if m.get("role") == "user"), "")
    try:
        return await asyncio.to_thread(therapy_turn, req.messages, req.notes, req.profile)
    except RuntimeError as exc:
        if at_risk(last):  # never leave someone at risk without the lines
            return {"respuesta": CRISIS, "riesgo": "alto", "nota": {}, "animo": 0, "temas": []}
        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = ["router"]

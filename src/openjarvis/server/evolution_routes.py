"""Sergio's evolution over HTTP: feedback, memory recall and the crew."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/evolve", tags=["evolution"])


class Feedback(BaseModel):
    text: str
    rating: int = 0
    about: str = ""


class Remember(BaseModel):
    kind: str
    text: str


class CrewTask(BaseModel):
    task: str


@router.post("/feedback")
async def feedback_route(req: Feedback) -> dict[str, Any]:
    """The user's opinion of the last result, kept for similar jobs."""
    from openjarvis.evolution.memory import shared

    rid = await asyncio.to_thread(shared().feedback, req.text[:1000], max(-1, min(1, req.rating)), req.about[:300])
    return {"id": rid}


@router.post("/remember")
async def remember_route(req: Remember) -> dict[str, Any]:
    from openjarvis.evolution.memory import shared

    return {"id": await asyncio.to_thread(shared().remember, req.kind, req.text[:4000])}


@router.get("/recall")
async def recall_route(q: str, k: int = 5) -> dict[str, Any]:
    from openjarvis.evolution.memory import shared

    return {"memories": await asyncio.to_thread(shared().recall, q, max(1, min(k, 20)))}


@router.get("/stats")
async def stats_route() -> dict[str, Any]:
    from openjarvis.evolution import crew
    from openjarvis.evolution.memory import shared

    stats = await asyncio.to_thread(shared().stats)
    try:
        import langgraph  # noqa: F401

        loop = "langgraph"
    except ImportError:
        loop = "loop"
    return {**stats, "self_correction": loop, "crew": crew.available()}


@router.post("/crew")
async def crew_route(req: CrewTask) -> dict[str, Any]:
    """A long written task done by the crewAI team with a quality supervisor."""
    from openjarvis.evolution import crew
    from openjarvis.evolution.memory import lessons, shared

    try:
        out = await asyncio.to_thread(crew.run_crew, req.task[:6000], lessons(req.task, ("feedback", "lesson", "task")))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    await asyncio.to_thread(shared().remember, "task", f"Equipo crewAI: {req.task[:300]} -> {out['result'][:500]}")
    return out


__all__ = ["router"]

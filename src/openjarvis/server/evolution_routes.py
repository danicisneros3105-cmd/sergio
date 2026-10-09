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

    rid = await asyncio.to_thread(
        shared().feedback, req.text[:1000], max(-1, min(1, req.rating)), req.about[:300]
    )
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
        out = await asyncio.to_thread(
            crew.run_crew,
            req.task[:6000],
            lessons(req.task, ("feedback", "lesson", "task")),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    await asyncio.to_thread(
        shared().remember,
        "task",
        f"Equipo crewAI: {req.task[:300]} -> {out['result'][:500]}",
    )
    return out


__all__ = ["router"]


class DeepQuestion(BaseModel):
    question: str
    strategy: str = "auto"


@router.post("/think")
async def think_route(req: DeepQuestion) -> dict[str, Any]:
    """Deep reasoning (the ten layers) with a confidence for the answer."""
    from openjarvis.intelligence._llm import LLM
    from openjarvis.intelligence.deep import deep_think
    from openjarvis.intelligence.uncertainty import default_calibrator
    from openjarvis.learning.meta_learner import default_learner

    if not req.question.strip():
        raise HTTPException(400, "question is empty")
    try:
        llm = await asyncio.to_thread(LLM.default)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None
    result = await asyncio.to_thread(
        deep_think,
        req.question[:8000],
        llm,
        strategy=req.strategy,
        learner=default_learner(),
        calibrator=default_calibrator(),
    )
    return {
        "answer": result.answer,
        "strategy": result.strategy,
        "kind": result.kind,
        "confidence": result.confidence,
        "decision": result.decision,
        "unknowns": result.unknowns,
        "calls": result.calls,
        "seconds": result.seconds,
    }

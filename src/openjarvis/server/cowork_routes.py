"""Cowork mode over HTTP: ``/v1/cowork``.

Start a run with the outcome you want, watch it (``/events`` streams every
step as it happens), answer the steps that wait for you, read the audit
trail, or cancel. ``POST /v1/cowork/scrutinize`` scores a single step, so
other front ends (Sergio Escritorio, the phone) apply the same rules.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from openjarvis.cowork.scrutiny import AXES, AXIS_LABELS_ES, AdaptiveScrutiny
from openjarvis.cowork.session import CoworkEngine

router = APIRouter(prefix="/v1/cowork", tags=["cowork"])
_engine_lock = threading.Lock()


class StartRequest(BaseModel):
    goal: str
    autonomy: Optional[str] = None
    max_actions: Optional[int] = None
    follows: Optional[str] = None  # the earlier task this one continues
    plan_first: bool = False  # «modo plan»: approve the plan before it starts


class NoteRequest(BaseModel):
    text: str


class DecisionRequest(BaseModel):
    step: int  # 1-based, as shown to the owner; 0 answers the plan itself
    approve: bool


class ScrutinizeRequest(BaseModel):
    text: str
    goal: str = ""
    tools: List[str] = []
    where: str = "fondo"
    check: str = ""
    autonomy: Optional[str] = None


def get_engine(request: Request) -> CoworkEngine:
    """One engine per app, built on first use with the owner notifier."""
    state = request.app.state
    with _engine_lock:
        engine = getattr(state, "cowork_engine", None)
        if engine is None:
            from openjarvis.core.config import load_config
            from openjarvis.cowork.notify import owner_sender

            config = load_config()
            engine = CoworkEngine(
                send_owner=owner_sender(config, getattr(state, "channel_bridge", None)),
                approval_timeout=max(1, config.cowork.approval_timeout_minutes) * 60,
            )
            state.cowork_engine = engine
    return engine


def _run_or_404(engine: CoworkEngine, run_id: str):
    run = engine.get(run_id)
    if run is None:
        raise HTTPException(404, "No existe esa tarea de Cowork.")
    return run


@router.post("")
async def start_run(req: StartRequest, request: Request) -> Dict[str, Any]:
    from openjarvis.core.config import load_config

    config = load_config()
    engine = get_engine(request)
    try:
        run = engine.start(
            req.goal,
            autonomy=req.autonomy or config.cowork.autonomy,
            max_actions=req.max_actions or config.cowork.max_actions,
            follows=req.follows or "",
            plan_first=req.plan_first,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return run.to_dict()


@router.get("")
async def list_runs(request: Request) -> Dict[str, Any]:
    runs = get_engine(request).list()
    return {"runs": [r.to_dict() for r in runs[:50]]}


@router.get("/axes")
async def axes() -> Dict[str, Any]:
    return {"axes": [{"id": a, "label": AXIS_LABELS_ES[a]} for a in AXES]}


@router.post("/scrutinize")
async def scrutinize(req: ScrutinizeRequest, request: Request) -> Dict[str, Any]:
    engine = get_engine(request)
    verdict = AdaptiveScrutiny(req.autonomy or "normal", engine.trust).review(
        req.text, goal=req.goal, tools=req.tools, where=req.where, check=req.check
    )
    return verdict.to_dict()


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> Dict[str, Any]:
    return _run_or_404(get_engine(request), run_id).to_dict()


@router.post("/{run_id}/decision")
async def decide(run_id: str, req: DecisionRequest, request: Request) -> Dict[str, Any]:
    engine = get_engine(request)
    _run_or_404(engine, run_id)
    if not engine.decide(run_id, req.step - 1, req.approve):
        raise HTTPException(409, "Ese paso no está esperando su respuesta.")
    return {"ok": True}


@router.post("/{run_id}/note")
async def note(run_id: str, req: NoteRequest, request: Request) -> Dict[str, Any]:
    """Steer a run while it works: the next steps read the owner's words."""
    engine = get_engine(request)
    _run_or_404(engine, run_id)
    if not engine.note(run_id, req.text):
        raise HTTPException(409, "Esa tarea ya terminó o la indicación está vacía.")
    return {"ok": True}


@router.post("/{run_id}/cancel")
async def cancel(run_id: str, request: Request) -> Dict[str, Any]:
    engine = get_engine(request)
    _run_or_404(engine, run_id)
    return {"ok": engine.cancel(run_id)}


@router.get("/{run_id}/audit")
async def audit(run_id: str, request: Request) -> Dict[str, Any]:
    engine = get_engine(request)
    _run_or_404(engine, run_id)
    trail = engine.audit(run_id)
    intact, broken_at = trail.verify()
    return {"entries": trail.to_list(), "intact": intact, "broken_at": broken_at}


@router.get("/{run_id}/events")
async def events(run_id: str, request: Request) -> StreamingResponse:
    """Server-sent events: the run as it is now, then every change."""
    engine = get_engine(request)
    run = _run_or_404(engine, run_id)
    box = engine.listen(run_id)

    async def stream() -> AsyncIterator[str]:
        try:
            yield f"data: {json.dumps({'type': 'snapshot', 'run': run.to_dict()}, ensure_ascii=False)}\n\n"
            while run.status not in (
                "done",
                "partial",
                "failed",
                "capped",
                "cancelled",
            ):
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.to_thread(box.get, True, 15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "finished":
                    break
            yield f"data: {json.dumps({'type': 'snapshot', 'run': run.to_dict()}, ensure_ascii=False)}\n\n"
        finally:
            engine.unlisten(run_id, box)

    return StreamingResponse(stream(), media_type="text/event-stream")


__all__ = ["get_engine", "router"]

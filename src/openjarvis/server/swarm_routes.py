"""Agent Swarm over HTTP: ``/v1/swarm``.

* ``POST /v1/swarm``               — start one (form: ``task``, ``parallel``,
  optional ``files`` — each document gets its own reading sub-agent).
* ``GET  /v1/swarm``               — the recent swarms (summaries).
* ``GET  /v1/swarm/{id}``          — one swarm: plan, sub-agents, report.
* ``GET  /v1/swarm/{id}/events``   — server-sent events while it works.
* ``POST /v1/swarm/{id}/cancel``   — stop it; it dissolves.
"""

from __future__ import annotations

import asyncio
import json
import queue
import re
import threading
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from openjarvis.swarm.engine import FINAL, MAX_SUBTASKS, Document, SwarmEngine

router = APIRouter(prefix="/v1/swarm", tags=["swarm"])
_lock = threading.Lock()
MAX_FILE_BYTES = 25_000_000
DOC_TYPES = (
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".html",
    ".xml",
    ".docx",
    ".log",
    ".py",
    ".js",
    ".ts",
)


def get_engine(request: Request) -> SwarmEngine:
    state = request.app.state
    with _lock:
        engine = getattr(state, "swarm_engine", None)
        if engine is None:
            engine = SwarmEngine()
            state.swarm_engine = engine
    return engine


def _safe_name(name: str, index: int) -> str:
    base = re.sub(
        r"[^\w.\- ]+", "_", (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    ).strip(" .")
    return base[:120] or f"documento-{index}"


@router.post("")
async def start(
    request: Request,
    task: str = Form(...),
    parallel: int = Form(8),
    files: Optional[List[UploadFile]] = File(None),
) -> Dict[str, Any]:
    engine = get_engine(request)
    documents: List[Document] = []
    if files:
        if len(files) > MAX_SUBTASKS:
            raise HTTPException(
                400, f"Como mucho {MAX_SUBTASKS} documentos por enjambre."
            )
        folder = engine.home / "uploads" / uuid.uuid4().hex[:12]
        folder.mkdir(parents=True, exist_ok=True)
        for i, upload in enumerate(files, 1):
            name = _safe_name(upload.filename or "", i)
            if not name.lower().endswith(DOC_TYPES):
                raise HTTPException(400, f"«{name}»: tipo no admitido.")
            data = await upload.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(400, f"«{name}» pasa de 25 MB.")
            path = folder / f"{i:03d}-{name}"
            await asyncio.to_thread(path.write_bytes, data)
            documents.append(Document(name=name, path=str(path)))
    try:
        run = engine.start(task, parallel=parallel, documents=documents)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return run.to_dict()


@router.get("")
async def list_runs(request: Request) -> Dict[str, Any]:
    return {"runs": [r.to_dict(results=False) for r in get_engine(request).list()[:50]]}


def _run_or_404(engine: SwarmEngine, run_id: str):
    run = engine.get(run_id)
    if run is None:
        raise HTTPException(404, "No existe ese enjambre.")
    return run


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> Dict[str, Any]:
    return _run_or_404(get_engine(request), run_id).to_dict()


@router.post("/{run_id}/cancel")
async def cancel(run_id: str, request: Request) -> Dict[str, Any]:
    engine = get_engine(request)
    _run_or_404(engine, run_id)
    return {"ok": engine.cancel(run_id)}


@router.get("/{run_id}/events")
async def events(run_id: str, request: Request) -> StreamingResponse:
    engine = get_engine(request)
    run = _run_or_404(engine, run_id)
    box = engine.listen(run_id)

    async def stream() -> AsyncIterator[str]:
        try:
            first = {"type": "snapshot", "swarm": run.to_dict(results=False)}
            yield f"data: {json.dumps(first, ensure_ascii=False)}\n\n"
            while run.status not in FINAL:
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
            yield f"data: {json.dumps({'type': 'snapshot', 'swarm': run.to_dict()}, ensure_ascii=False)}\n\n"
        finally:
            engine.unlisten(run_id, box)

    return StreamingResponse(stream(), media_type="text/event-stream")


__all__ = ["get_engine", "router"]

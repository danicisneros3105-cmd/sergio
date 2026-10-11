"""Nodes over HTTP: ``/v1/nodes`` — your 24/7 digital employees.

* ``GET/POST /v1/nodes``                       — list · create (it introduces itself)
* ``GET/PATCH/DELETE /v1/nodes/{id}``          — one Node: settings, rules, apps
* ``GET/POST /v1/nodes/{id}/messages``         — talk to it (it answers in the background)
* ``GET  /v1/nodes/{id}/activity?after=``      — what it did, live
* ``GET/PUT /v1/nodes/{id}/memory``            — its long-term memory
* ``POST /v1/nodes/{id}/routines``, ``DELETE …/routines/{rid}`` — recurring work
* ``POST /v1/nodes/{id}/approvals/{aid}``      — ``{"approve": true|false}``
* ``POST /v1/nodes/{id}/hand-back``            — after you took over
* ``POST /v1/nodes/{id}/stop`` · ``/resume``   — emergency stop and back
* ``GET  /v1/nodes/{id}/computer``, ``…/computer/file?path=`` — its disk
* ``GET  /v1/nodes/rules``                     — the rule categories and choices
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from openjarvis.nodes.store import COLORS, RULES, NodeError
from openjarvis.nodes.worker import NodeWorker

router = APIRouter(prefix="/v1/nodes", tags=["nodes"])
_lock = threading.Lock()


def get_worker(request: Request) -> NodeWorker:
    state = request.app.state
    with _lock:
        worker = getattr(state, "node_worker", None)
        if worker is None:
            worker = NodeWorker()
            worker.start()
            state.node_worker = worker
    return worker


class NewNode(BaseModel):
    name: str
    instructions: str = ""
    color: str = ""
    apps: List[str] = []
    rules: Dict[str, str] = {}


class NodeChanges(BaseModel):
    name: Optional[str] = None
    instructions: Optional[str] = None
    color: Optional[str] = None
    apps: Optional[List[str]] = None
    rules: Optional[Dict[str, str]] = None


class Message(BaseModel):
    text: str


class Memory(BaseModel):
    text: str


class NewRoutine(BaseModel):
    task: str
    every_minutes: int = 0
    at: str = ""
    days: List[int] = []


class Decision(BaseModel):
    approve: bool


class HandBack(BaseModel):
    note: str = ""


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(400, str(exc))


def _node(worker: NodeWorker, node_id: str):
    node = worker.store.get(node_id)
    if node is None:
        raise HTTPException(404, "No existe ese Node.")
    return node


def _full(worker: NodeWorker, node_id: str) -> Dict[str, Any]:
    node = _node(worker, node_id)
    store = worker.store
    unread = len(
        [
            a
            for a in store.activity(node_id, after=node.last_seen)
            if a["kind"] in ("done", "approval", "needs_you")
        ]
    )
    return {
        **node.to_dict(),
        "busy": worker.busy(node_id),
        "memory": store.memory(node_id),
        "approvals": [a for a in store.approvals(node_id) if a["status"] == "pending"],
        "unread": unread,
        "computer": str(store.computer(node_id)),
    }


@router.get("/rules")
async def rules() -> Dict[str, Any]:
    return {
        "rules": [
            {
                "key": k,
                "label": v["label"],
                "default": v["default"],
                "choices": v["choices"],
            }
            for k, v in RULES.items()
        ],
        "colors": list(COLORS),
    }


@router.get("")
async def list_nodes(request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    return {"nodes": [_full(worker, n.id) for n in worker.store.all()]}


@router.post("")
async def create(body: NewNode, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    try:
        node = await asyncio.to_thread(
            worker.create,
            body.name,
            body.instructions,
            color=body.color,
            apps=body.apps,
            rules=body.rules,
        )
    except NodeError as exc:
        raise _bad(exc) from exc
    return _full(worker, node.id)


@router.get("/{node_id}")
async def get_node(node_id: str, request: Request) -> Dict[str, Any]:
    return _full(get_worker(request), node_id)


@router.patch("/{node_id}")
async def change(node_id: str, body: NodeChanges, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    try:
        worker.store.update(node_id, **body.model_dump(exclude_none=True))
    except NodeError as exc:
        raise _bad(exc) from exc
    return _full(worker, node_id)


@router.delete("/{node_id}")
async def delete(node_id: str, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    worker.stop(node_id)
    return {"deleted": worker.store.delete(node_id)}


@router.post("/{node_id}/seen")
async def seen(node_id: str, request: Request) -> Dict[str, Any]:
    import time

    worker = get_worker(request)
    _node(worker, node_id)
    worker.store.update(node_id, last_seen=time.time())
    return {"ok": True}


@router.get("/{node_id}/messages")
async def messages(
    node_id: str, request: Request, after: float = 0.0
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    return {"messages": worker.store.messages(node_id, after=after)}


@router.post("/{node_id}/messages")
async def send(node_id: str, body: Message, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    try:
        return {"message": worker.send(node_id, body.text)}
    except NodeError as exc:
        raise _bad(exc) from exc


@router.get("/{node_id}/activity")
async def activity(
    node_id: str, request: Request, after: float = 0.0
) -> Dict[str, Any]:
    worker = get_worker(request)
    node = _node(worker, node_id)
    return {
        "activity": worker.store.activity(node_id, after=after),
        "status": node.status,
        "doing": node.doing,
        "waiting": node.waiting,
        "busy": worker.busy(node_id),
    }


@router.get("/{node_id}/memory")
async def memory(node_id: str, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    return {"text": worker.store.memory(node_id)}


@router.put("/{node_id}/memory")
async def set_memory(node_id: str, body: Memory, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    text = worker.store.set_memory(node_id, body.text)
    worker.store.log(node_id, "memory", "Usted editó su memoria.")
    return {"text": text}


@router.post("/{node_id}/routines")
async def add_routine(
    node_id: str, body: NewRoutine, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    try:
        routine = worker.store.add_routine(node_id, body.model_dump())
    except NodeError as exc:
        raise _bad(exc) from exc
    worker.store.log(node_id, "routine", f"Nueva rutina: {routine.task}")
    return _full(worker, node_id)


@router.delete("/{node_id}/routines/{routine_id}")
async def remove_routine(
    node_id: str, routine_id: str, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    worker.store.remove_routine(node_id, routine_id)
    return _full(worker, node_id)


@router.post("/{node_id}/approvals/{approval_id}")
async def decide(
    node_id: str, approval_id: str, body: Decision, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    try:
        worker.decide(node_id, approval_id, body.approve)
    except NodeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _full(worker, node_id)


@router.post("/{node_id}/hand-back")
async def hand_back(node_id: str, body: HandBack, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    worker.hand_back(node_id, body.note)
    return _full(worker, node_id)


@router.post("/{node_id}/stop")
async def stop(node_id: str, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    worker.stop(node_id)
    return _full(worker, node_id)


@router.post("/{node_id}/resume")
async def resume(node_id: str, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    worker.resume(node_id)
    return _full(worker, node_id)


@router.get("/{node_id}/computer")
async def computer(node_id: str, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    node = _node(worker, node_id)
    tools = [
        a for a in worker.store.activity(node_id, limit=400) if a["kind"] == "tool"
    ][-30:]
    return {
        "files": worker.store.files(node_id),
        "path": str(worker.store.computer(node_id)),
        "doing": node.doing,
        "recent": tools,
    }


@router.get("/{node_id}/computer/file")
async def computer_file(node_id: str, path: str, request: Request) -> FileResponse:
    worker = get_worker(request)
    _node(worker, node_id)
    found = worker.store.file_path(node_id, path)
    if found is None:
        raise HTTPException(404, "No encuentro ese archivo en su computadora.")
    return FileResponse(found, filename=found.name)


__all__ = ["get_worker", "router"]

"""Nodes over HTTP: ``/v1/nodes`` — your 24/7 digital employees.

* ``GET/POST /v1/nodes``                       — list · create (from a template; it introduces itself)
* ``GET  /v1/nodes/catalog``                   — rules, colours, plush parts, tones, templates, plan
* ``GET/PATCH/DELETE /v1/nodes/{id}``          — one Node: face, tone, rules, apps
* ``GET/POST /v1/nodes/{id}/threads``          — separate conversations, same memory
* ``GET/POST /v1/nodes/{id}/messages``         — talk to it (``?thread=``; it answers in the background)
* ``GET  /v1/nodes/{id}/activity?after=``      — what it did, live
* ``GET/PUT /v1/nodes/{id}/memory``            — its long-term memory
* ``POST /v1/nodes/{id}/routines``, ``DELETE …/routines/{rid}``, ``POST …/routines/{rid}/check``
* ``POST /v1/nodes/{id}/approvals/{aid}``      — ``{"approve": true|false}``
* ``POST /v1/nodes/{id}/hand-back``            — after you took over
* ``POST /v1/nodes/{id}/stop`` · ``/resume``   — emergency stop and back
* ``POST /v1/nodes/{id}/cancel``              — drop what it is doing now, stay available
* ``GET  /v1/nodes/{id}/computer``, ``…/computer/file?path=`` — its disk
* ``POST /v1/nodes/{id}/connections/{cli|mcp|api}``, ``DELETE …/{kind}/{cid}``,
  ``POST …/mcp/{cid}/tools`` — commands, MCP servers, APIs (Dev plan)
* ``GET  /v1/nodes/rules``                     — the rule categories and choices (kept for old clients)
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from openjarvis.nodes import connections, skills, team
from openjarvis.nodes.store import (
    COLORS,
    MAIN_THREAD,
    RULES,
    SHAPES,
    TONES,
    NodeError,
)
from openjarvis.nodes.worker import NodeWorker

router = APIRouter(prefix="/v1/nodes", tags=["nodes"])
_lock = threading.Lock()


def get_worker(request: Request) -> NodeWorker:
    state = request.app.state
    with _lock:
        worker = getattr(state, "node_worker", None)
        if worker is None:
            worker = NodeWorker(swarm=_swarm(request), notify=_owner_notify(request))
            worker.store.ensure_team()  # Rihno, Manchas, Hous y Tennessee: siempre
            worker.start()
            state.node_worker = worker
    return worker


def _swarm(request: Request) -> Any:
    try:
        from openjarvis.server.swarm_routes import get_engine

        return get_engine(request)
    except Exception:  # noqa: BLE001 - Nodes work without the swarm
        return None


def _owner_notify(request: Request) -> Any:
    """The owner's notifier (the same one Cowork uses), when configured."""
    try:
        from openjarvis.core.config import load_config
        from openjarvis.cowork.notify import owner_sender

        return owner_sender(
            load_config(), getattr(request.app.state, "channel_bridge", None)
        )
    except Exception:  # noqa: BLE001
        return None


class NewNode(BaseModel):
    name: str
    instructions: str = ""
    color: str = ""
    apps: Any = None
    rules: Dict[str, str] = {}
    tone: str = ""
    template: str = ""


class NodeChanges(BaseModel):
    name: Optional[str] = None
    instructions: Optional[str] = None
    color: Optional[str] = None
    apps: Any = None
    rules: Optional[Dict[str, str]] = None
    tone: Optional[str] = None


class Message(BaseModel):
    text: str
    thread: str = MAIN_THREAD


class NewThread(BaseModel):
    title: str = ""


class Memory(BaseModel):
    text: str


class NewRoutine(BaseModel):
    task: str
    kind: str = "time"
    every_minutes: int = 0
    at: str = ""
    days: List[int] = []
    url: str = ""
    app: str = ""
    keywords: List[str] = []


class Decision(BaseModel):
    approve: bool


class HandBack(BaseModel):
    note: str = ""


class NewConnection(BaseModel):
    name: str
    command: str = ""
    url: str = ""
    base_url: str = ""
    auth_header: str = "Authorization"
    prefix: str = ""
    secret: str = ""


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
        "approvals": [
            {k: v for k, v in a.items() if k != "action"}
            for a in store.approvals(node_id)
            if a["status"] == "pending"
        ],
        "unread": unread,
        "computer": str(store.computer(node_id)),
    }


def _plan() -> Dict[str, Any]:
    from openjarvis.tiers import current

    plan = current().get("plan", "free")
    return {"plan": plan, "api_allowed": connections.api_allowed()}


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


@router.get("/catalog")
async def catalog() -> Dict[str, Any]:
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
        "shapes": list(SHAPES),
        "tones": [{"key": k, "label": v} for k, v in TONES.items()],
        "team": team.roster(),
        "team_pitch": team.TEAM_PITCH,
        "templates": [
            {k: t.get(k) for k in ("id", "name", "title", "description", "avatar")}
            for t in skills.TEMPLATES
        ],
        **_plan(),
    }


@router.get("")
async def list_nodes(request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    return {"nodes": [_full(worker, n.id) for n in worker.store.all()]}


@router.post("")
async def create(body: NewNode, request: Request) -> Dict[str, Any]:
    """The Nodes are a fixed team of four; no others are made."""
    raise HTTPException(
        400,
        "Los Nodes son un equipo fijo de cuatro: Rihno, Manchas, Hous y Tennessee. "
        "Encárgueles a ellos lo que necesite.",
    )


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


class OwnRule(BaseModel):
    text: str


@router.post("/{node_id}/own-rules")
async def add_own_rule(node_id: str, body: OwnRule, request: Request) -> Dict[str, Any]:
    """«Pídeme permiso antes de borrar archivos»: understood once, reviewed
    by code before every action (and shown back so the owner sees how)."""
    from openjarvis.nodes.own_rules import MAX_RULES, compile_rule, explain

    worker = get_worker(request)
    node = _node(worker, node_id)
    try:
        rule = compile_rule(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if len(node.own_rules) >= MAX_RULES:
        raise HTTPException(status_code=422, detail="Máximo 30 reglas propias.")
    worker.store.update(node_id, own_rules=[*node.own_rules, rule])
    worker.store.log(
        node_id, "rules", f"Nueva regla: «{rule['text']}» · {explain(rule)}"
    )
    return {**_full(worker, node_id), "rule": {**rule, "explain": explain(rule)}}


@router.delete("/{node_id}/own-rules/{rule_id}")
async def remove_own_rule(
    node_id: str, rule_id: str, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    node = _node(worker, node_id)
    worker.store.update(
        node_id, own_rules=[r for r in node.own_rules if r.get("id") != rule_id]
    )
    return _full(worker, node_id)


@router.delete("/{node_id}")
async def delete(node_id: str, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    node = _node(worker, node_id)
    if node.team:
        raise HTTPException(400, f"{node.name} es del equipo fijo: siempre está.")
    worker.stop(node_id)
    try:
        return {"deleted": worker.store.delete(node_id)}
    except NodeError as exc:
        raise _bad(exc) from exc


@router.post("/{node_id}/seen")
async def seen(node_id: str, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    worker.store.update(node_id, last_seen=time.time())
    return {"ok": True}


@router.get("/{node_id}/threads")
async def threads(node_id: str, request: Request) -> Dict[str, Any]:
    return {"threads": _node(get_worker(request), node_id).threads}


@router.post("/{node_id}/threads")
async def new_thread(node_id: str, body: NewThread, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    try:
        return {"thread": worker.store.add_thread(node_id, body.title)}
    except NodeError as exc:
        raise _bad(exc) from exc


@router.get("/{node_id}/messages")
async def messages(
    node_id: str, request: Request, after: float = 0.0, thread: Optional[str] = None
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    return {"messages": worker.store.messages(node_id, after=after, thread=thread)}


@router.post("/{node_id}/messages")
async def send(node_id: str, body: Message, request: Request) -> Dict[str, Any]:
    from openjarvis.quota import guard

    guard("nodes")
    worker = get_worker(request)
    _node(worker, node_id)
    try:
        return {"message": worker.send(node_id, body.text, thread=body.thread)}
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
    if (
        routine.kind == "web"
    ):  # take the reference copy now, so the next look can compare
        await asyncio.to_thread(worker.check_now, node_id, routine.id)
    return _full(worker, node_id)


@router.post("/{node_id}/routines/{routine_id}/check")
async def check_routine(
    node_id: str, routine_id: str, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    result = await asyncio.to_thread(worker.check_now, node_id, routine_id)
    return {"woke": bool(result.get("woke")), "error": result.get("error", "")}


@router.delete("/{node_id}/routines/{routine_id}")
async def remove_routine(
    node_id: str, routine_id: str, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    worker.store.remove_routine(node_id, routine_id)
    return _full(worker, node_id)


class RoutineState(BaseModel):
    enabled: bool


@router.patch("/{node_id}/routines/{routine_id}")
async def routine_state(
    node_id: str, routine_id: str, body: RoutineState, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    node = _node(worker, node_id)
    if not any(r.id == routine_id for r in node.routines):
        raise HTTPException(status_code=404, detail="Rutina no encontrada.")
    worker.store.mark_routine(
        node_id, routine_id, 0, enabled=body.enabled, failures=0, last_error=""
    )
    return _full(worker, node_id)


@router.post("/{node_id}/approvals/{approval_id}")
async def decide(
    node_id: str, approval_id: str, body: Decision, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    try:
        await asyncio.to_thread(worker.decide, node_id, approval_id, body.approve)
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


@router.post("/{node_id}/cancel")
async def cancel(node_id: str, request: Request) -> Dict[str, Any]:
    """Cancel the action in progress; the Node stays available."""
    worker = get_worker(request)
    _node(worker, node_id)
    worker.cancel(node_id)
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
        a
        for a in worker.store.activity(node_id, limit=400)
        if a["kind"] in ("tool", "result")
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


@router.post("/{node_id}/connections/{kind}")
async def add_connection(
    node_id: str, kind: str, body: NewConnection, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    if kind == "api" and not connections.api_allowed():
        raise HTTPException(
            402,
            "Las APIs propias en los Nodes son del plan Dev. Véalo con: sergio planes",
        )
    try:
        data = body.model_dump()
        secret = data.pop("secret", "")
        worker.store.add_connection(
            node_id, kind, data, secret=secret if kind == "api" else ""
        )
    except NodeError as exc:
        raise _bad(exc) from exc
    worker.store.log(node_id, "connection", f"Nueva conexión ({kind}): {body.name}")
    return _full(worker, node_id)


@router.delete("/{node_id}/connections/{kind}/{conn_id}")
async def remove_connection(
    node_id: str, kind: str, conn_id: str, request: Request
) -> Dict[str, Any]:
    worker = get_worker(request)
    _node(worker, node_id)
    worker.store.remove_connection(node_id, kind, conn_id)
    return _full(worker, node_id)


@router.post("/{node_id}/connections/mcp/{conn_id}/tools")
async def mcp_tools(node_id: str, conn_id: str, request: Request) -> Dict[str, Any]:
    worker = get_worker(request)
    node = _node(worker, node_id)
    entry = next(
        (c for c in node.connections.get("mcp", []) if c["id"] == conn_id), None
    )
    if entry is None:
        raise HTTPException(404, "No existe esa conexión.")
    try:
        return {"tools": await asyncio.to_thread(connections.mcp_tools, entry)}
    except Exception as exc:  # noqa: BLE001 - shown to you as is
        raise HTTPException(502, f"No pude hablar con el servidor MCP: {exc}") from exc


__all__ = ["get_worker", "router"]

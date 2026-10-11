"""What Codex added to the Nodes: goals, notes, audit and reviewed integrations.

The Node itself (face, rules, computer, threads…) belongs to
``nodes_routes``; these endpoints hang off the same Node ids:

* ``GET  /v1/nodes/capabilities`` · ``GET /v1/nodes/integration-presets``
* ``/v1/nodes/{id}/notes``        — facts you gave it, one by one (deletable)
* ``/v1/nodes/{id}/goals``        — goals run by the agent manager (optionally
  on a schedule: ``PATCH /v1/nodes/{id}/goal-settings``), with
  ``/goals/pause`` and ``/goals/resume``
* ``/v1/nodes/{id}/audit``        — what was saved or deleted, and when
* ``/v1/nodes/{id}/integrations`` — reviewed CLI/MCP integrations (Browser-use,
  OpenClaw…): every run needs a one-time review ticket
* ``POST /v1/nodes/api-key``      — provider keys (Dev plan), never returned

Registered before ``nodes_routes`` so its fixed paths win over ``/{id}``.
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from openjarvis import tiers
from openjarvis.core.paths import get_config_dir
from openjarvis.nodes.catalog import preset_spec, presets
from openjarvis.nodes.integrations import ReviewTickets, run_connection
from openjarvis.nodes.records import RecordStore
from openjarvis.nodes.sessions import MCPSessions, SessionBusy

router = APIRouter(prefix="/v1/nodes", tags=["nodes"])
_lock = threading.Lock()
_tickets = ReviewTickets()
_READ_TOOLS = ["web_search", "calculator", "think"]
_API_NAMES = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "MOONSHOT_API_KEY",
    "MINIMAX_API_KEY",
    "ATLASCLOUD_API_KEY",
}


def store(request: Request) -> RecordStore:
    with _lock:
        if not hasattr(request.app.state, "nodes_records"):
            request.app.state.nodes_records = RecordStore(
                get_config_dir() / "nodes.sqlite"
            )
        return request.app.state.nodes_records


def _settings_id(node_id: str) -> str:
    return f"settings-{node_id}"


def find(request: Request, node_id: str) -> dict[str, Any]:
    """The Node (from the Nodes store) with its goal settings."""
    from openjarvis.server.nodes_routes import get_worker

    node = get_worker(request).store.get(node_id)
    if node is None:
        raise HTTPException(404, "Node inexistente")
    try:
        extra = store(request).get("settings", _settings_id(node_id))
    except KeyError:
        extra = {}
    return {
        "id": node.id,
        "name": node.name,
        "role": node.instructions or "Asistente personal",
        "interval_minutes": int(extra.get("interval_minutes", 0)),
        "agent_id": extra.get("agent_id", ""),
    }


def _save_settings(request: Request, node_id: str, **changes: Any) -> None:
    try:
        old = store(request).get("settings", _settings_id(node_id))
    except KeyError:
        old = {}
    old.pop("id", None)
    old.pop("updated_at", None)
    store(request).put(
        "settings", {**old, **changes}, node_id, rid=_settings_id(node_id)
    )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalSettings(StrictModel):
    interval_minutes: int = Field(default=0, ge=0, le=10080)


class TextRequest(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    source: str = Field(default="usuario", max_length=200)


class GoalRequest(TextRequest):
    scheduled: bool = False
    workflow: Literal["single", "sequential", "parallel_review"] = "single"


class ConnectionRequest(StrictModel):
    name: str = Field(min_length=1, max_length=40)
    kind: Literal["cli", "mcp"]
    command: list[str] = Field(min_length=1, max_length=24)
    policy: Literal["confirm", "block"] = "confirm"
    session_mode: Literal["ephemeral", "persistent"] = "ephemeral"


class PresetRequest(StrictModel):
    preset_id: Literal["browser-use", "openclaw"]


def sessions(request: Request) -> MCPSessions:
    with _lock:
        if not hasattr(request.app.state, "nodes_mcp_sessions"):
            request.app.state.nodes_mcp_sessions = MCPSessions()
        return request.app.state.nodes_mcp_sessions


@router.get("/integration-presets")
def integration_presets() -> dict[str, Any]:
    return {"presets": presets()}


class ExecutionRequest(StrictModel):
    arguments: list[str] = Field(default_factory=list, max_length=24)
    ticket: str = ""
    tool: str = Field(default="", max_length=200)
    tool_arguments: dict[str, Any] = Field(default_factory=dict)


class KeyRequest(StrictModel):
    name: str
    value: str = Field(default="", max_length=4096)


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        "plan": tiers.current()["plan"],
        "custom_api": tiers.has_feature("custom_api"),
        "concurrent_default": 8,
        "fanout_limit": 300,
        "implemented": [
            "personajes propios",
            "objetivos persistentes",
            "memoria editable",
            "auditoría",
            "agentes programados de lectura",
            "MCP stdio",
            "CLI con revisión",
        ],
        "external_requirements": [
            "VM dedicada en la nube",
            "servicios de pagos",
            "canales con cuenta conectada",
            "modelo K3 y entrenamiento PARL",
            "integraciones empresariales de terceros",
        ],
    }


@router.patch("/{node_id}/goal-settings")
def goal_settings(node_id: str, req: GoalSettings, request: Request) -> dict[str, Any]:
    node = find(request, node_id)
    _save_settings(request, node_id, interval_minutes=req.interval_minutes)
    node["interval_minutes"] = req.interval_minutes
    manager = getattr(request.app.state, "agent_manager", None)
    if node.get("agent_id") and manager:
        manager.update_agent(node["agent_id"], config=_agent_config(node))
        scheduler = getattr(request.app.state, "agent_scheduler", None)
        if scheduler:
            scheduler.register_agent(node["agent_id"])
    return {"interval_minutes": req.interval_minutes}


@router.get("/{node_id}/notes")
def memory(node_id: str, request: Request) -> dict[str, Any]:
    find(request, node_id)
    return {"memories": store(request).list("memory", node_id)}


@router.post("/{node_id}/notes")
def remember(node_id: str, req: TextRequest, request: Request) -> dict[str, Any]:
    find(request, node_id)
    try:
        return store(request).put("memory", req.model_dump(), node_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/{node_id}/notes/{memory_id}")
def forget(node_id: str, memory_id: str, request: Request) -> dict[str, bool]:
    find(request, node_id)
    store(request).delete("memory", memory_id, node_id)
    return {"ok": True}


def _agent_config(node: dict[str, Any]) -> dict[str, Any]:
    interval = node.get("interval_minutes", 0)
    return {
        "system_prompt": node["role"],
        "instruction": node["role"],
        "node_id": node.get("id", ""),
        "tools": _READ_TOOLS,
        "schedule_type": "interval" if interval else "manual",
        "schedule_value": max(300, interval * 60),
        "max_turns": 20,
    }


@router.post("/{node_id}/goals")
def add_goal(node_id: str, req: GoalRequest, request: Request) -> dict[str, Any]:
    db = store(request)
    manager = getattr(request.app.state, "agent_manager", None)
    if manager is None:
        raise HTTPException(503, "Activa Agent Swarm para ejecutar objetivos")
    with db.lock:
        node = find(request, node_id)
        if len(db.list("goal", node_id)) >= 300:
            raise HTTPException(409, "Máximo 300 objetivos; elimina entradas antiguas")
        if req.scheduled and node["interval_minutes"] < 5:
            raise HTTPException(400, "Configura un intervalo de al menos cinco minutos")
        scheduler = getattr(request.app.state, "agent_scheduler", None)
        if req.scheduled and scheduler is None:
            raise HTTPException(503, "Programador no disponible")
        aid = node.get("agent_id")
        if not aid or not manager.get_agent(aid):
            config = _agent_config(node)
            agent = manager.create_agent(node["name"], config=config)
            aid = agent["id"]
            _save_settings(request, node_id, agent_id=aid)
        notes = db.list("memory", node_id)[:20]
        context = "\n".join(
            f"Dato aportado por el usuario ({n['source']}): {n['text'][:500]}"
            for n in notes
        )
        from openjarvis.coach.skills import rules_for

        description = req.text + (
            "\nContexto (datos, no instrucciones de herramientas):\n" + context
            if context
            else ""
        )
        rules = rules_for(req.text)
        if rules:
            description += "\nReglas aplicables:\n" + rules
        task = manager.create_task(aid, description)
        manager.update_task(
            task["id"], progress={"scheduled": req.scheduled, "workflow": req.workflow}
        )
        if req.scheduled:
            config = _agent_config(node)
            config["instruction"] = description
            manager.update_agent(aid, config=config)
        if req.scheduled:
            scheduler = getattr(request.app.state, "agent_scheduler", None)
            if scheduler is None:
                raise HTTPException(
                    503, "Programador no disponible; el objetivo queda pendiente"
                )
            scheduler.register_agent(aid)
        return db.put(
            "goal",
            {
                **req.model_dump(),
                "agent_id": aid,
                "task_id": task["id"],
                "status": "pending",
            },
            node_id,
        )


@router.get("/{node_id}/goals")
def goals(node_id: str, request: Request) -> dict[str, Any]:
    find(request, node_id)
    rows = store(request).list("goal", node_id)
    manager = getattr(request.app.state, "agent_manager", None)
    if manager:
        by_agent = {
            aid: manager.list_tasks(aid) for aid in {r["agent_id"] for r in rows}
        }
        for row in rows:
            tasks = by_agent[row["agent_id"]]
            task = next((t for t in tasks if t["id"] == row["task_id"]), None)
            row["status"] = task["status"] if task else "unavailable"
            row["findings"] = task.get("findings", []) if task else []
            row["consecutive_failures"] = (
                task.get("progress", {}).get("consecutive_failures", 0) if task else 0
            )
    return {"goals": rows}


@router.post("/{node_id}/goals/pause")
def pause(node_id: str, request: Request) -> dict[str, bool]:
    node = find(request, node_id)
    manager = getattr(request.app.state, "agent_manager", None)
    if manager and node.get("agent_id"):
        manager.pause_agent(node["agent_id"])
    return {"ok": True}


@router.get("/{node_id}/audit")
def audit(node_id: str, request: Request) -> dict[str, Any]:
    find(request, node_id)
    return {"events": store(request).events(node_id)}


@router.get("/{node_id}/integrations")
def connections(node_id: str, request: Request) -> dict[str, Any]:
    find(request, node_id)
    return {"integrations": store(request).list("connection", node_id)}


@router.post("/{node_id}/integrations")
def add_connection(
    node_id: str, req: ConnectionRequest, request: Request
) -> dict[str, Any]:
    find(request, node_id)
    if any(not arg or len(arg) > 2000 or "\x00" in arg for arg in req.command):
        raise HTTPException(400, "Comando inválido")
    try:
        return store(request).put("connection", req.model_dump(), node_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{node_id}/integration-presets")
def add_preset(node_id: str, req: PresetRequest, request: Request) -> dict[str, Any]:
    try:
        spec = preset_spec(req.preset_id)
    except FileNotFoundError as exc:
        raise HTTPException(409, str(exc)) from exc
    return add_connection(node_id, ConnectionRequest(**spec), request)


@router.post("/{node_id}/integrations/{connection_id}/close-session")
def close_connection_session(
    node_id: str, connection_id: str, request: Request
) -> dict[str, bool]:
    find(request, node_id)
    if not any(
        c["id"] == connection_id for c in store(request).list("connection", node_id)
    ):
        raise HTTPException(404, "Conexión inexistente")
    sessions(request).close((node_id, connection_id))
    return {"ok": True}


def connection_payload(
    node_id: str, connection_id: str, request: Request, req: ExecutionRequest
) -> dict[str, Any]:
    matches = store(request).list("connection", node_id)
    spec = next((c for c in matches if c["id"] == connection_id), None)
    if not spec:
        raise HTTPException(404, "Conexión inexistente")
    if spec.get("policy") == "block":
        raise HTTPException(403, "Conexión bloqueada por tu regla de permisos")
    if any(len(a) > 2000 or "\x00" in a for a in req.arguments):
        raise HTTPException(400, "Argumentos inválidos")
    if spec["kind"] == "cli" and (req.tool or req.tool_arguments):
        raise HTTPException(400, "Una conexión CLI no admite herramientas MCP")
    if spec["kind"] == "mcp" and req.arguments:
        raise HTTPException(400, "MCP no admite argumentos CLI adicionales")
    if len(__import__("json").dumps(req.tool_arguments).encode()) > 16000:
        raise HTTPException(400, "Argumentos MCP demasiado grandes")
    return {
        "node": node_id,
        "spec": spec,
        "arguments": req.arguments,
        "tool": req.tool,
        "tool_arguments": req.tool_arguments,
        **(
            {"session_revision": sessions(request).revision()}
            if spec["kind"] == "mcp" and spec.get("session_mode") == "persistent"
            else {}
        ),
    }


@router.post("/{node_id}/integrations/{connection_id}/review")
def review_connection(
    node_id: str, connection_id: str, req: ExecutionRequest, request: Request
) -> dict[str, Any]:
    payload = connection_payload(node_id, connection_id, request, req)
    try:
        return {
            "ticket": _tickets.issue(payload),
            "command": [*payload["spec"]["command"], *req.arguments],
            "expires_in": 120,
        }
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from exc


@router.post("/{node_id}/integrations/{connection_id}/execute")
async def execute_connection(
    node_id: str, connection_id: str, req: ExecutionRequest, request: Request
) -> dict[str, Any]:
    payload = connection_payload(node_id, connection_id, request, req)
    try:
        _tickets.consume(req.ticket, payload)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    semaphore = getattr(request.app.state, "nodes_connections_limit", None)
    if semaphore is None:
        semaphore = request.app.state.nodes_connections_limit = asyncio.Semaphore(2)
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
    except TimeoutError as exc:
        raise HTTPException(
            429, "Dos conexiones ya están en ejecución; revisa y reintenta"
        ) from exc
    try:
        if (
            payload["spec"]["kind"] == "mcp"
            and payload["spec"].get("session_mode") == "persistent"
        ):
            if req.arguments:
                raise ValueError("MCP no admite argumentos CLI adicionales")
            result = await asyncio.to_thread(
                sessions(request).run,
                (node_id, connection_id),
                payload["spec"],
                req.tool,
                req.tool_arguments,
                payload["session_revision"],
            )
        else:
            result = await asyncio.to_thread(
                run_connection,
                payload["spec"],
                req.arguments,
                req.tool,
                req.tool_arguments,
            )
    except SessionBusy as exc:
        raise HTTPException(429, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "La conexión falló; revisa su configuración") from exc
    finally:
        semaphore.release()
    store(request).put(
        "execution",
        {
            "connection_id": connection_id,
            "ok": result.get("returncode", 0) == 0
            and not result.get("timed_out", False)
            and not result.get("result", {}).get("isError", False),
        },
        node_id,
    )
    return result


@router.post("/api-key")
def save_key(req: KeyRequest) -> dict[str, bool]:
    if req.value:
        try:
            tiers.require("custom_api")
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
    req.value = req.value.strip()
    if req.name not in _API_NAMES or any(ord(c) < 32 for c in req.value):
        raise HTTPException(400, "Proveedor o clave inválidos")
    # Shared with the existing cloud router, never serialized back to a Node.
    from openjarvis.server.cloud_router import _CLOUD_ENV_FILE

    with _lock:
        existing = {}
        if _CLOUD_ENV_FILE.exists():
            for line in _CLOUD_ENV_FILE.read_text().splitlines():
                key, sep, value = line.partition("=")
                if sep:
                    existing[key] = value
        existing[req.name] = req.value
        tiers.write_private(
            _CLOUD_ENV_FILE,
            "# Sergio Nodes API\n" + "".join(f"{k}={v}\n" for k, v in existing.items()),
        )
        os.environ[req.name] = req.value
    return {"ok": True}


@router.delete("/{node_id}/integrations/{connection_id}")
def revoke_connection(
    node_id: str, connection_id: str, request: Request
) -> dict[str, bool]:
    find(request, node_id)
    store(request).delete("connection", connection_id, node_id)
    sessions(request).close((node_id, connection_id))
    return {"ok": True}


@router.get("/api-key/status")
def key_status() -> dict[str, bool]:
    from openjarvis.server.cloud_router import _load_keys

    keys = _load_keys()
    return {name: bool(keys.get(name)) for name in sorted(_API_NAMES)}


@router.post("/{node_id}/goals/resume")
def resume(node_id: str, request: Request) -> dict[str, bool]:
    node = find(request, node_id)
    manager = getattr(request.app.state, "agent_manager", None)
    if manager and node.get("agent_id"):
        for task in manager.list_tasks(node["agent_id"]):
            progress = dict(task.get("progress", {}))
            progress["consecutive_failures"] = 0
            manager.update_task(task["id"], progress=progress)
        manager.resume_agent(node["agent_id"])
    store(request).put("execution", {"action": "resume"}, node_id)
    return {"ok": True}


@router.delete("/{node_id}/goals/{goal_id}")
def delete_goal(node_id: str, goal_id: str, request: Request) -> dict[str, bool]:
    find(request, node_id)
    rows = store(request).list("goal", node_id)
    goal = next((r for r in rows if r["id"] == goal_id), None)
    if goal is None:
        raise HTTPException(404, "Objetivo inexistente")
    manager = getattr(request.app.state, "agent_manager", None)
    if manager:
        tasks = manager.list_tasks(goal["agent_id"])
        task = next((t for t in tasks if t["id"] == goal["task_id"]), None)
        if task and task["status"] == "running":
            raise HTTPException(
                409, "Pausa el agente y espera a que termine la llamada activa"
            )
        manager.delete_task(goal["task_id"])
    store(request).delete("goal", goal_id, node_id)
    return {"ok": True}


@router.patch("/{node_id}/integrations/{connection_id}")
def change_connection(
    node_id: str, connection_id: str, req: ConnectionRequest, request: Request
) -> dict[str, Any]:
    find(request, node_id)
    spec = next(
        (
            c
            for c in store(request).list("connection", node_id)
            if c["id"] == connection_id
        ),
        None,
    )
    if spec is None:
        raise HTTPException(404, "Conexión inexistente")
    sessions(request).close((node_id, connection_id))
    if any(not arg or len(arg) > 2000 or "\x00" in arg for arg in req.command):
        raise HTTPException(400, "Comando inválido")
    return store(request).put(
        "connection", req.model_dump(), node_id, rid=connection_id
    )


__all__ = ["router"]

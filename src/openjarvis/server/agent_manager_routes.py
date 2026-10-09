"""FastAPI routes for the Agent Manager."""

from __future__ import annotations

import logging
import re as _re  # noqa: F401 - looked up here by agent_manager_helpers
import threading
from typing import Any, Dict, List, Optional, Tuple

from openjarvis.agents.manager import AgentManager

# The helpers moved to agent_manager_helpers look these up on this module, so
# tests (and callers) can keep patching them here.
from openjarvis.agents.tool_resolver import (  # noqa: F401
    BROWSER_SUB_TOOLS as _BROWSER_SUB_TOOLS,
)
from openjarvis.agents.tool_resolver import (  # noqa: F401
    build_deep_research_tools,
    instantiate_registered_tool,
    resolve_tool_specs,
)
from openjarvis.agents.tool_resolver import (  # noqa: F401
    ensure_registries_populated as _ensure_registries_populated,
)
from openjarvis.server.model_capabilities import is_embed_only_model  # noqa: F401

try:
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
except ImportError:
    raise ImportError("fastapi and pydantic are required for server routes")

logger = logging.getLogger("openjarvis.server.agent_manager")
_MEMORY_BACKEND_LOCK_SETUP = threading.Lock()
_MCP_LOCK_SETUP = threading.Lock()


def _get_runtime_event_bus(runtime: Any = None) -> Any:
    """Return the server-owned event bus, falling back outside app runtimes."""

    from openjarvis.core.events import get_event_bus

    bus = getattr(runtime, "bus", None)
    return bus if bus is not None else get_event_bus()


def _start_managed_worker(app_state: Any, target: Any, *, name: str) -> Any:
    """Start and track a managed-agent worker for orderly app shutdown."""

    lock = getattr(app_state, "_managed_worker_lock", None)
    if lock is None:
        lock = threading.Lock()
        app_state._managed_worker_lock = lock
    workers = getattr(app_state, "_managed_workers", None)
    if workers is None:
        workers = set()
        app_state._managed_workers = workers

    thread: threading.Thread

    def _run() -> None:
        try:
            target()
        finally:
            with lock:
                workers.discard(thread)

    with lock:
        if getattr(app_state, "_managed_runtime_stopping", False):
            raise RuntimeError("managed-agent runtime is shutting down")
        thread = threading.Thread(target=_run, daemon=True, name=name)
        workers.add(thread)
        try:
            # Shutdown must never snapshot an added-but-not-started thread,
            # because joining such a thread raises instead of draining it.
            thread.start()
        except Exception:
            workers.discard(thread)
            raise
    return thread


class CreateAgentRequest(BaseModel):
    name: str
    agent_type: str = "monitor_operative"
    config: Optional[Dict[str, Any]] = None
    template_id: Optional[str] = None


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    agent_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class CreateTaskRequest(BaseModel):
    description: str


class UpdateTaskRequest(BaseModel):
    description: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None
    findings: Optional[List[Any]] = None


class BindChannelRequest(BaseModel):
    channel_type: str
    config: Optional[Dict[str, Any]] = None
    routing_mode: str = "dedicated"


class SendMessageRequest(BaseModel):
    content: str
    mode: str = "queued"
    stream: bool = False  # SSE streaming mode


class FeedbackRequest(BaseModel):
    score: float
    reason: Optional[str] = None


class _LightweightSystem:
    """Minimal system facade for the executor — avoids rebuilding the
    full JarvisSystem (which picks a random model from Ollama)."""

    def __init__(
        self,
        engine: Any,
        model: str,
        config: Any = None,
        runtime: Any = None,
    ) -> None:
        self.engine = engine
        self.model = model
        self.config = config
        self._runtime = runtime
        self.capability_policy = getattr(runtime, "capability_policy", None)
        self.rate_limiter = getattr(runtime, "rate_limiter", None)
        # Wire the configured memory backend so an agent's memory_store /
        # memory_retrieve tools work when the tick runs through the server.
        # The executor injects system.memory_backend into those tools; this
        # facade previously left it None, so they reported "No memory backend
        # configured" even though the backend was configured and active.
        self.memory_backend = _get_or_create_memory_backend(runtime, config)
        self.channel_backend = None
        self.mcp_tools: list[Any] = []
        self._mcp_clients: list[Any] = []
        self.knowledge_db_path = None
        if runtime is not None:
            self.channel_backend = getattr(runtime, "channel_backend", None) or getattr(
                runtime, "channel_bridge", None
            )
            self.knowledge_db_path = getattr(runtime, "knowledge_db_path", None)

    def get_managed_agent_mcp_tools(self) -> tuple[list[Any], list[Any]]:
        """Lazily discover MCP tools only after the agent allows them."""

        if self.mcp_tools:
            return self.mcp_tools, self._mcp_clients
        if self._runtime is None:
            return [], []

        runtime_tools = list(getattr(self._runtime, "mcp_tools", []) or [])
        if runtime_tools:
            self.mcp_tools = runtime_tools
        else:
            _, adapters = _get_mcp_tools(self._runtime)
            self.mcp_tools = list(adapters.values())
        self._mcp_clients = list(getattr(self._runtime, "_mcp_clients", []) or [])
        return self.mcp_tools, self._mcp_clients


_CLOUD_PREFIXES = ("gpt-", "claude-", "gemini-", "o1-", "o3-", "o4-")


# Per-agent sampler params forwarded to the engine when present in config.
# The OpenAI-compat engine passes **kwargs straight through to the upstream
# payload, so these reach local servers (vLLM / mlx_lm / etc.) that support
# them. Only forwarded when explicitly set, so default agents send nothing
# extra and engines that don't support a key never receive it. (#386)
_SAMPLER_PARAM_KEYS = (
    "top_p",
    "top_k",
    "min_p",
    "repetition_penalty",
    "frequency_penalty",
    "presence_penalty",
)


def create_agent_manager_router(
    manager: AgentManager,
) -> Tuple[APIRouter, APIRouter, APIRouter, APIRouter, APIRouter]:
    """Create FastAPI routers with agent management endpoints.

    Returns a 5-tuple:
    ``(agents_router, templates_router, global_router, tools_router, sendblue_router)``.
    """
    agents_router = APIRouter(prefix="/v1/managed-agents", tags=["managed-agents"])
    templates_router = APIRouter(prefix="/v1/templates", tags=["templates"])

    # ── Agent lifecycle ──────────────────────────────────────

    @agents_router.get("")
    async def list_agents() -> Dict[str, Any]:
        return {"agents": manager.list_agents()}

    @agents_router.post("")
    async def create_agent(req: CreateAgentRequest, request: Request) -> Dict[str, Any]:
        if req.template_id:
            agent = manager.create_from_template(
                req.template_id, req.name, overrides=req.config
            )
        else:
            agent = manager.create_agent(
                name=req.name, agent_type=req.agent_type, config=req.config
            )

        # Register with scheduler if cron/interval
        scheduler = getattr(request.app.state, "agent_scheduler", None)
        sched_type = (req.config or {}).get("schedule_type", "manual")
        if scheduler and sched_type in ("cron", "interval"):
            scheduler.register_agent(agent["id"])

        return agent

    @agents_router.get("/{agent_id}")
    async def get_agent(agent_id: str) -> Dict[str, Any]:
        agent = manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent

    @agents_router.patch("/{agent_id}")
    async def update_agent(agent_id: str, req: UpdateAgentRequest) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        kwargs: Dict[str, Any] = {}
        if req.name is not None:
            kwargs["name"] = req.name
        if req.agent_type is not None:
            kwargs["agent_type"] = req.agent_type
        if req.config is not None:
            kwargs["config"] = req.config
        return manager.update_agent(agent_id, **kwargs)

    @agents_router.delete("/{agent_id}")
    async def delete_agent(agent_id: str) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        manager.delete_agent(agent_id)
        return {"status": "archived"}

    @agents_router.post("/{agent_id}/pause")
    async def pause_agent(agent_id: str) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        manager.pause_agent(agent_id)
        return {"status": "paused"}

    @agents_router.post("/{agent_id}/resume")
    async def resume_agent(agent_id: str) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        manager.resume_agent(agent_id)
        return {"status": "idle"}

    @agents_router.post("/{agent_id}/run")
    async def run_agent(agent_id: str, request: Request) -> Dict[str, Any]:
        agent = manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent["status"] == "archived":
            raise HTTPException(status_code=400, detail="Agent is archived")

        # Auto-recover from error/needs_attention state
        if agent["status"] in ("error", "needs_attention"):
            manager.update_agent(agent_id, status="idle")

        # Acquire tick BEFORE spawning thread — prevents race
        try:
            manager.start_tick(agent_id)
        except ValueError:
            raise HTTPException(status_code=409, detail="Agent is already running")

        # Re-use the server's engine + model so we don't pick a
        # random model from Ollama's list.
        app_state = request.app.state
        server_engine = getattr(app_state, "engine", None)
        server_model = getattr(app_state, "model", "")
        server_config = getattr(app_state, "config", None)
        server_bus = _get_runtime_event_bus(app_state)

        def _run_tick() -> None:
            try:
                from openjarvis.agents.executor import AgentExecutor

                _ts = getattr(app_state, "trace_store", None)
                executor = AgentExecutor(
                    manager=manager,
                    event_bus=server_bus,
                    trace_store=_ts,
                )
                system = _make_lightweight_system(
                    server_engine,
                    server_model,
                    server_config,
                    app_state,
                )
                executor.set_system(system)
                # The route handler above already called start_tick() to
                # serialize concurrent POSTs; tell the executor not to
                # re-acquire, otherwise it bails on its own guard and the
                # tick never runs.
                executor.execute_tick(agent_id, lock_already_held=True)
            except Exception as exc:
                logger.error(
                    "Run-tick failed for agent %s: %s",
                    agent_id,
                    exc,
                    exc_info=True,
                )
                try:
                    manager.end_tick(agent_id)
                except Exception:
                    pass
                manager.update_agent(agent_id, status="error")
                manager.update_summary_memory(
                    agent_id,
                    f"ERROR: {exc}",
                )

        try:
            _start_managed_worker(
                app_state,
                _run_tick,
                name=f"managed-agent-run-{agent_id}",
            )
        except RuntimeError as exc:
            try:
                manager.end_tick(agent_id)
            except Exception:
                pass
            raise HTTPException(status_code=503, detail=str(exc))
        return {"status": "running", "agent_id": agent_id}

    # ── Recover ──────────────────────────────────────────────

    @agents_router.post("/{agent_id}/recover")
    def recover_agent(agent_id: str) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        checkpoint = manager.recover_agent(agent_id)
        return {"recovered": True, "checkpoint": checkpoint}

    # ── Tasks ────────────────────────────────────────────────

    @agents_router.get("/{agent_id}/tasks")
    async def list_tasks(agent_id: str, status: Optional[str] = None) -> Dict[str, Any]:
        return {"tasks": manager.list_tasks(agent_id, status=status)}

    @agents_router.post("/{agent_id}/tasks")
    async def create_task(agent_id: str, req: CreateTaskRequest) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        return manager.create_task(agent_id, description=req.description)

    @agents_router.get("/{agent_id}/tasks/{task_id}")
    async def get_task(agent_id: str, task_id: str) -> Dict[str, Any]:
        task = manager._get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @agents_router.patch("/{agent_id}/tasks/{task_id}")
    async def update_task(
        agent_id: str, task_id: str, req: UpdateTaskRequest
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if req.description is not None:
            kwargs["description"] = req.description
        if req.status is not None:
            kwargs["status"] = req.status
        if req.progress is not None:
            kwargs["progress"] = req.progress
        if req.findings is not None:
            kwargs["findings"] = req.findings
        return manager.update_task(task_id, **kwargs)

    @agents_router.delete("/{agent_id}/tasks/{task_id}")
    async def delete_task(agent_id: str, task_id: str) -> Dict[str, Any]:
        manager.delete_task(task_id)
        return {"status": "deleted"}

    add_channel_and_message_routes(agents_router, manager)
    # ── State inspection ─────────────────────────────────────

    @agents_router.get("/{agent_id}/state")
    def get_agent_state(agent_id: str) -> Dict[str, Any]:
        agent = manager.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {
            "agent": agent,
            "tasks": manager.list_tasks(agent_id),
            "channels": manager.list_channel_bindings(agent_id),
            "messages": manager.list_messages(agent_id),
            "checkpoint": manager.get_latest_checkpoint(agent_id),
        }

    # ── Learning ─────────────────────────────────────────────

    @agents_router.get("/{agent_id}/learning")
    def get_learning_log(agent_id: str) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"learning_log": manager.list_learning_log(agent_id)}

    @agents_router.post("/{agent_id}/learning/run")
    def trigger_learning(agent_id: str, request: Request) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        from openjarvis.core.events import EventType

        bus = _get_runtime_event_bus(request.app.state)
        bus.publish(EventType.AGENT_LEARNING_STARTED, {"agent_id": agent_id})
        return {"status": "triggered"}

    # ── Traces ───────────────────────────────────────────────

    @agents_router.get("/{agent_id}/traces")
    def list_traces(agent_id: str, limit: int = 20) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        try:
            from openjarvis.core.config import load_config
            from openjarvis.core.paths import get_config_dir
            from openjarvis.traces.store import TraceStore

            config = load_config()
            store = TraceStore(
                config.traces.db_path or str(get_config_dir() / "traces.db")
            )
            traces = store.list_traces(agent=agent_id, limit=limit)
            return {
                "traces": [
                    {
                        "id": t.trace_id,
                        "outcome": t.outcome,
                        "duration": t.total_latency_seconds,
                        "started_at": t.started_at,
                        "steps": len(t.steps),
                        "metadata": t.metadata,
                    }
                    for t in traces
                ]
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @agents_router.get("/{agent_id}/traces/{trace_id}")
    def get_trace(agent_id: str, trace_id: str) -> Dict[str, Any]:
        try:
            from openjarvis.core.config import load_config
            from openjarvis.core.paths import get_config_dir
            from openjarvis.traces.store import TraceStore

            config = load_config()
            store = TraceStore(
                config.traces.db_path or str(get_config_dir() / "traces.db")
            )
            trace = store.get(trace_id)
            if trace is None:
                raise HTTPException(status_code=404, detail="Trace not found")
            return {
                "id": trace.trace_id,
                "agent": trace.agent,
                "outcome": trace.outcome,
                "duration": trace.total_latency_seconds,
                "started_at": trace.started_at,
                "steps": [
                    {
                        "step_type": s.step_type.value,
                        "input": s.input,
                        "output": s.output,
                        "duration": s.duration_seconds,
                        "metadata": s.metadata,
                    }
                    for s in trace.steps
                ],
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Templates ────────────────────────────────────────────

    @templates_router.get("")
    async def list_templates() -> Dict[str, Any]:
        return {"templates": AgentManager.list_templates()}

    @templates_router.post("/{template_id}/instantiate")
    async def instantiate_template(
        template_id: str, req: CreateAgentRequest
    ) -> Dict[str, Any]:
        return manager.create_from_template(template_id, req.name, overrides=req.config)

    # ── Global agent endpoints ───────────────────────────────

    global_router = APIRouter(tags=["agents-global"])

    @global_router.get("/v1/agents/errors")
    def list_error_agents() -> Dict[str, Any]:
        all_agents = manager.list_agents()
        error_agents = [
            a
            for a in all_agents
            if a["status"] in ("error", "needs_attention", "stalled", "budget_exceeded")
        ]
        return {"agents": error_agents}

    @global_router.get("/v1/agents/health")
    def agents_health() -> Dict[str, Any]:
        all_agents = manager.list_agents()
        from collections import Counter

        counts = Counter(a["status"] for a in all_agents)
        return {
            "total": len(all_agents),
            "by_status": dict(counts),
        }

    @global_router.get("/v1/recommended-model")
    def recommended_model(request: Request) -> Dict[str, str]:
        engine = getattr(request.app.state, "engine", None)
        if engine is None:
            return {"model": "", "reason": "No engine available"}
        try:
            models = engine.list_models()
        except Exception:
            models = []
        return _pick_recommended_model(models)

    tools_router, sendblue_router = build_tools_routers()
    return (
        agents_router,
        templates_router,
        global_router,
        tools_router,
        sendblue_router,
    )


# Moved to their own module; they look their helpers up here.
from openjarvis.server.agent_manager_stream import (  # noqa: E402,I001
    _get_mcp_tools_locked as _get_mcp_tools_locked,
)
from openjarvis.server.agent_manager_stream import (  # noqa: E402,I001
    _stream_managed_agent as _stream_managed_agent,
)

# Only the moved code uses these; it looks them up on this module.
from openjarvis.agents.tool_resolver import resolve_agent_tools as resolve_agent_tools  # noqa: E402,I001
from fastapi.responses import StreamingResponse as StreamingResponse  # noqa: E402,I001

# Moved to their own module (it looks its helpers up here).
from openjarvis.server import agent_manager_tools as _agent_manager_tools  # noqa: E402,I001

build_tools_routers = _agent_manager_tools.build_tools_routers

# Moved to their own module (it looks its helpers up here).
from openjarvis.server import agent_manager_channels as _agent_manager_channels  # noqa: E402,I001

add_channel_and_message_routes = _agent_manager_channels.add_channel_and_message_routes

# Moved to their own module (it looks its helpers up here).
from openjarvis.server import agent_manager_helpers as _agent_manager_helpers  # noqa: E402,I001

_resolve_memory_backend = _agent_manager_helpers._resolve_memory_backend
_memory_backend_lock = _agent_manager_helpers._memory_backend_lock
_get_or_create_memory_backend = _agent_manager_helpers._get_or_create_memory_backend
_mcp_state_lock = _agent_manager_helpers._mcp_state_lock
_register_mcp_client = _agent_manager_helpers._register_mcp_client
_unregister_mcp_client = _agent_manager_helpers._unregister_mcp_client
_make_lightweight_system = _agent_manager_helpers._make_lightweight_system
_parse_param_count = _agent_manager_helpers._parse_param_count
_pick_recommended_model = _agent_manager_helpers._pick_recommended_model
build_tools_list = _agent_manager_helpers.build_tools_list
_resolve_tool_specs = _agent_manager_helpers._resolve_tool_specs
_build_managed_system_prompt = _agent_manager_helpers._build_managed_system_prompt
_sampler_kwargs = _agent_manager_helpers._sampler_kwargs
_replay_history_messages = _agent_manager_helpers._replay_history_messages
_instantiate_managed_tool = _agent_manager_helpers._instantiate_managed_tool
_build_deep_research_tools = _agent_manager_helpers._build_deep_research_tools
_merge_tool_call_fragments = _agent_manager_helpers._merge_tool_call_fragments
_get_mcp_tools = _agent_manager_helpers._get_mcp_tools
_sse_chunk = _agent_manager_helpers._sse_chunk
_tool_progress_label = _agent_manager_helpers._tool_progress_label


__all__ = [
    "BindChannelRequest",
    "create_agent_manager_router",
    "CreateAgentRequest",
    "CreateTaskRequest",
    "FeedbackRequest",
    "SendMessageRequest",
    "UpdateAgentRequest",
    "UpdateTaskRequest",
]

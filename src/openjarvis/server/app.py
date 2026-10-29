"""FastAPI application factory for the OpenJarvis API server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import pathlib
import re
import threading
import time
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from openjarvis.server.analytics_routes import router as analytics_router
from openjarvis.server.api_routes import include_all_routes
from openjarvis.server.connectors_router import create_connectors_router
from openjarvis.server.digest_routes import create_digest_router
from openjarvis.server.extensions_router import router as extensions_router
from openjarvis.server.research_router import router as research_router
from openjarvis.server.routes import router
from openjarvis.server.upload_router import router as upload_router

logger = logging.getLogger(__name__)
_MANAGED_SHUTDOWN_GRACE_SECONDS = 0.25
_MANAGED_SHUTDOWN_DRAIN_SECONDS = 10.0


def _restore_sendblue_bindings(app: FastAPI) -> None:
    """Restore SendBlue channel bindings from the database on startup.

    If a SendBlue binding was created via the Messaging tab and the server
    restarts, this ensures the ChannelBridge + DeepResearchAgent are wired
    up so incoming webhooks continue to work.
    """
    try:
        mgr = getattr(app.state, "agent_manager", None)
        if mgr is None:
            return

        # Check all agents for sendblue bindings
        for agent in mgr.list_agents():
            agent_id = agent.get("id", agent.get("agent_id", ""))
            bindings = mgr.list_channel_bindings(agent_id)
            for b in bindings:
                if b.get("channel_type") != "sendblue":
                    continue
                config = b.get("config", {})
                api_key_id = config.get("api_key_id", "")
                api_secret_key = config.get("api_secret_key", "")
                from_number = config.get("from_number", "")
                if not api_key_id or not api_secret_key:
                    continue

                from openjarvis.channels.sendblue import SendBlueChannel

                sb = SendBlueChannel(
                    api_key_id=api_key_id,
                    api_secret_key=api_secret_key,
                    from_number=from_number,
                )
                sb.connect()
                app.state.sendblue_channel = sb

                # Create ChannelBridge if none exists
                bridge = getattr(app.state, "channel_bridge", None)
                if bridge and hasattr(bridge, "_channels"):
                    bridge._channels["sendblue"] = sb
                else:
                    from openjarvis.server.channel_bridge import ChannelBridge
                    from openjarvis.server.session_store import SessionStore

                    session_store = SessionStore()
                    engine = getattr(app.state, "engine", None)
                    dr_agent = None
                    if engine:
                        from openjarvis.server.agent_manager_routes import (
                            _build_deep_research_tools,
                        )

                        tools = _build_deep_research_tools(engine=engine, model="")
                        if tools:
                            from openjarvis.agents.deep_research import (
                                DeepResearchAgent,
                            )

                            model_name = getattr(app.state, "model", "") or getattr(
                                engine, "_model", ""
                            )
                            dr_agent = DeepResearchAgent(
                                engine=engine,
                                model=model_name,
                                tools=tools,
                                bus=getattr(app.state, "bus", None),
                                capability_policy=getattr(
                                    app.state, "capability_policy", None
                                ),
                                rate_limiter=getattr(app.state, "rate_limiter", None),
                                agent_id=agent_id,
                            )

                    bus = getattr(app.state, "bus", None)
                    if bus is None:
                        from openjarvis.core.events import EventBus

                        bus = EventBus()

                    app.state.channel_bridge = ChannelBridge(
                        channels={"sendblue": sb},
                        session_store=session_store,
                        bus=bus,
                        agent_manager=mgr,
                        deep_research_agent=dr_agent,
                    )

                logger.info(
                    "Restored SendBlue channel binding: %s",
                    from_number,
                )
                return  # Only need one SendBlue binding
    except Exception as exc:
        logger.debug("SendBlue binding restore skipped: %s", exc)


# No-cache headers applied to static file responses
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}
# A file whose name carries its content hash never changes: the browser keeps it.
_IMMUTABLE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}


_HASHED_ASSET_RE = re.compile(
    r"^(?P<stem>[A-Za-z0-9_.-]+)-[A-Za-z0-9_-]{6,16}\.(?P<ext>js|css)$"
)


class _NoCacheStaticFiles(StaticFiles):
    """StaticFiles subclass that resolves updated chunk hashes: the exact hashed
    file is cached for good (its name changes with its content); anything else,
    an older name resolved to the new file included, is never cached."""

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        full_path, stat_result = super().lookup_path(path)
        if stat_result is not None or not self.directory:
            return full_path, stat_result
        name = pathlib.Path(path).name
        match = _HASHED_ASSET_RE.match(name)
        if match:
            stem = match.group("stem")
            ext = match.group("ext")
            base_dir = pathlib.Path(str(self.directory))
            candidates = sorted(
                base_dir.glob(f"{stem}-*.{ext}"),
                key=lambda p: p.stat().st_mtime if p.is_file() else 0.0,
                reverse=True,
            )
            for candidate in candidates:
                if candidate.is_file():
                    try:
                        return str(candidate), candidate.stat()
                    except OSError:
                        continue
        return full_path, stat_result

    def _exact_hashed(self, scope) -> bool:
        """The very file asked for, named by its hash (not an older name resolved)."""
        name = pathlib.Path(scope.get("path", "")).name
        if not _HASHED_ASSET_RE.match(name) or not self.directory:
            return False
        return (pathlib.Path(str(self.directory)) / name).is_file()

    async def __call__(self, scope, receive, send):
        headers = _IMMUTABLE_HEADERS if self._exact_hashed(scope) else _NO_CACHE_HEADERS

        async def _send_with_headers(message):
            if message["type"] == "http.response.start":
                extra = [(k.encode(), v.encode()) for k, v in headers.items()]
                # Remove etag and last-modified
                existing = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in (b"etag", b"last-modified")
                ]
                message = {**message, "headers": existing + extra}
            await send(message)

        await super().__call__(scope, receive, _send_with_headers)


def _warm_up() -> None:
    """Load at start what the first question would otherwise wait for (the
    fly brain, the prompt library, the memory, the own voice): before this,
    the first answer after starting took ~12 s instead of ~2 s."""
    import time as _time

    started = _time.monotonic()
    steps = (
        (
            "cerebro",
            lambda: __import__(
                "openjarvis.connectome.decision", fromlist=["think"]
            ).think("hola", "chat"),
        ),
        (
            "memoria",
            lambda: __import__(
                "openjarvis.connectome.brain", fromlist=["mind_context"]
            ).mind_context("hola"),
        ),
        (
            "voz propia",
            lambda: __import__(
                "openjarvis.speech.voz_propia", fromlist=["ready"]
            ).ready(),
        ),
    )
    for name, step in steps:
        try:
            step()
        except Exception as exc:  # noqa: BLE001 — warming never blocks anything
            logger.debug("warm-up %s skipped: %s", name, exc)
    logger.info("Sergio warmed up in %.1f s", _time.monotonic() - started)


def create_app(
    engine,
    model: str,
    *,
    agent=None,
    bus=None,
    engine_name: str = "",
    agent_name: str = "",
    channel_bridge=None,
    config=None,
    memory_backend=None,
    own_memory_backend: bool = False,
    memory_service=None,
    speech_backend=None,
    agent_manager=None,
    agent_scheduler=None,
    mcp_tools=None,
    mcp_clients=None,
    capability_policy=None,
    rate_limiter=None,
    audit_logger=None,
    api_key: str = "",
    webhook_config: dict | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    engine:
        The inference engine to use for completions.
    model:
        Default model name.
    agent:
        Optional agent instance for agent-mode completions.
    bus:
        Optional event bus for telemetry.
    channel_bridge:
        Optional channel bridge for multi-platform messaging.
    config:
        Optional JarvisConfig for other settings.
    """
    original_engine = engine
    security_enabled = config is not None and getattr(
        getattr(config, "security", None), "enabled", False
    )
    if security_enabled:
        if bus is None:
            from openjarvis.core.events import EventBus

            bus = EventBus(record_history=False)
        if any(
            primitive is None
            for primitive in (capability_policy, rate_limiter, audit_logger)
        ):
            # Programmatic factory callers must receive the same config-driven
            # enforcement as ``jarvis serve``. Explicitly injected primitives
            # remain authoritative; only missing pieces are derived.
            from openjarvis.security import setup_security

            derived_security = setup_security(config, engine, bus)
            engine = derived_security.engine
            if capability_policy is None:
                capability_policy = derived_security.capability_policy
            if rate_limiter is None:
                rate_limiter = derived_security.rate_limiter
            if audit_logger is None:
                audit_logger = derived_security.audit_logger

    # A pre-built tool-using agent is part of the factory's remote execution
    # surface too. Fill only missing executor fields so explicit per-agent
    # wiring remains authoritative.
    if agent is not None and getattr(agent, "_engine", None) is original_engine:
        agent._engine = engine
    from openjarvis.security.runtime import wire_agent_security

    wire_agent_security(
        agent,
        bus=bus,
        capability_policy=capability_policy,
        rate_limiter=rate_limiter,
        agent_id=(
            agent_name
            or getattr(agent, "_runtime_agent_id", "")
            or getattr(agent, "agent_id", "")
        ),
        overwrite=False,
        synchronize_runtime_cache=True,
    )

    # Shutdown work registered below (managed runtime, analytics, memory
    # service) runs in registration order when the lifespan ends; this
    # replaces FastAPI's deprecated shutdown event handlers.
    shutdown_hooks: list[Callable[[], Awaitable[None]]] = []

    def on_shutdown(
        hook: Callable[[], Awaitable[None]],
    ) -> Callable[[], Awaitable[None]]:
        shutdown_hooks.append(hook)
        return hook

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            for hook in shutdown_hooks:
                try:
                    await hook()
                except Exception:  # noqa: BLE001 - one failing hook must not skip the rest
                    logger.exception("Shutdown step %s failed", hook.__name__)

    app = FastAPI(
        title="Sergio API",
        description="OpenAI-compatible API server for Sergio",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.shutdown_hooks = shutdown_hooks

    from fastapi import Request as _Request
    from fastapi.responses import JSONResponse

    from openjarvis.cli.friendly import plain

    @app.exception_handler(Exception)
    async def _explain_unexpected_error(request: _Request, exc: Exception):
        # Without this an engine error (e.g. Ollama "model requires more
        # memory") reaches the user as a bare "500 Internal Server Error".
        logger.exception("Unhandled error on %s", request.url.path)
        from openjarvis.server.accounts_routes import is_local

        detail = plain(exc)
        # The technical detail (paths, hosts, library messages) only on the
        # owner's own computer; from outside, the calm sentence alone.
        if is_local(request):
            detail = f"{detail} Detalle: {type(exc).__name__}: {exc}"
        return JSONResponse(status_code=500, content={"detail": detail[:600]})

    from fastapi.middleware.cors import CORSMiddleware

    # Allow deployments to pin the exact browser origins via
    # OPENJARVIS_CORS_ORIGINS (comma-separated). On an exposed server this
    # should be set to your real frontend origin(s) only — never "*", which
    # combined with allow_credentials=True would let any website call the API
    # in the user's authenticated context.
    _env_origins = os.environ.get("OPENJARVIS_CORS_ORIGINS", "").strip()
    if cors_origins is not None:
        _origins = cors_origins
    elif _env_origins:
        _origins = [o.strip() for o in _env_origins.split(",") if o.strip()]
    else:
        _origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            # Tauri 2 production webview origins:
            #   macOS / Linux / iOS  -> tauri://localhost
            #   Windows / Android    -> http://tauri.localhost (default),
            #                           https://tauri.localhost when
            #                           windows.useHttpsScheme is enabled
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ]
    # Defense in depth: a literal "*" with credentials is unsafe. Refuse it.
    _origins = [o for o in _origins if o != "*"]
    # Store dependencies in app state
    app.state.engine = engine
    app.state.model = model
    app.state.agent = agent
    app.state.bus = bus
    app.state.engine_name = engine_name
    app.state.agent_name = agent_name or (
        getattr(agent, "agent_id", None) if agent else None
    )
    app.state.channel_bridge = channel_bridge
    app.state.config = config
    app.state._memory_backend_lock = threading.Lock()
    app.state.memory_backend = memory_backend
    app.state._owns_memory_backend = bool(own_memory_backend)
    app.state.memory_service = memory_service
    app.state.speech_backend = speech_backend
    app.state.agent_manager = agent_manager
    app.state.agent_scheduler = agent_scheduler
    # Security primitives for the managed-agent HTTP/SSE routes
    # (agent_manager_routes.py). Previously never passed here at all, so
    # every managed agent reached over the network ran with no RBAC gate,
    # no rate limiting, and no audit trail regardless of config.
    app.state.capability_policy = capability_policy
    app.state.rate_limiter = rate_limiter
    app.state.audit_logger = audit_logger
    app.state.mcp_tools = list(mcp_tools or [])
    app.state._mcp_discovery_lock = threading.Lock()
    app.state._mcp_clients_lock = threading.Lock()
    app.state._mcp_clients = list(mcp_clients or [])
    app.state._managed_worker_lock = threading.Lock()
    app.state._managed_workers: set[threading.Thread] = set()
    app.state._managed_runtime_stopping = False
    app.state.session_start = time.time()
    # Exposed so WebSocket handlers can authenticate the handshake (the HTTP
    # AuthMiddleware never sees WS upgrade requests). Empty = auth disabled.
    app.state.api_key = api_key

    @on_shutdown
    async def _shutdown_managed_runtime() -> None:
        # Quiesce every producer before touching the shared MCP pool. Route
        # workers are registered under this lock, so none can slip in after
        # the snapshot. The scheduler has a two-phase stop because closing an
        # MCP transport may be what releases an in-flight tick.
        with app.state._managed_worker_lock:
            app.state._managed_runtime_stopping = True
            managed_workers = list(app.state._managed_workers)

        # Stop external listener threads before draining ticks or closing the
        # shared MCP pool. Channel callbacks are wired to that same pool by
        # ``serve`` and otherwise could race teardown or survive app restart.
        channel_bridge = getattr(app.state, "channel_bridge", None)
        disconnect_channels = getattr(channel_bridge, "disconnect", None)
        if callable(disconnect_channels):
            try:
                disconnect_channels()
            except Exception:
                logger.debug("Channel bridge shutdown failed", exc_info=True)

        def _join_workers(timeout: float) -> None:
            deadline = time.monotonic() + timeout
            for thread in managed_workers:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                thread.join(timeout=remaining)

        scheduler = getattr(app.state, "agent_scheduler", None)
        scheduler_wait = None
        scheduler_drained = True
        if scheduler is not None:
            try:
                request_stop = getattr(scheduler, "request_stop", None)
                wait_stopped = getattr(scheduler, "wait_stopped", None)
                if callable(request_stop) and callable(wait_stopped):
                    request_stop()
                    scheduler_wait = wait_stopped
                    scheduler_drained = bool(
                        wait_stopped(timeout=_MANAGED_SHUTDOWN_GRACE_SECONDS)
                    )
                else:
                    scheduler.stop()
                    scheduler_drained = not bool(
                        getattr(scheduler, "is_running", False)
                    )
            except Exception:
                scheduler_drained = False
                logger.debug("Agent scheduler shutdown failed", exc_info=True)

        # Give normal work a brief chance to finish before cancellation.
        _join_workers(timeout=_MANAGED_SHUTDOWN_GRACE_SECONDS)
        with app.state._mcp_clients_lock:
            mcp_clients_to_close = list(app.state._mcp_clients)
        for client in mcp_clients_to_close:
            try:
                client.close()
            except Exception:
                logger.debug("MCP client shutdown failed", exc_info=True)

        # Transport closure interrupts blocked MCP reads. Drain the workers a
        # second time so shutdown does not return while they still own runtime
        # state. Any stragglers can no longer issue transport requests because
        # MCPClient marks itself closed before closing its transport.
        if scheduler_wait is not None:
            try:
                scheduler_drained = bool(
                    scheduler_wait(timeout=_MANAGED_SHUTDOWN_DRAIN_SECONDS)
                )
            except Exception:
                scheduler_drained = False
                logger.debug("Agent scheduler drain failed", exc_info=True)
        _join_workers(timeout=_MANAGED_SHUTDOWN_DRAIN_SECONDS)
        alive = [thread.name for thread in managed_workers if thread.is_alive()]
        if alive:
            logger.warning("Managed workers did not stop during shutdown: %s", alive)

        # A backend created by ``serve`` or lazily by a managed route belongs
        # to this app process. Close it only after every tracked consumer has
        # been drained; injected/borrowed backends remain the caller's concern.
        owned_memory_backend = None
        runtime_drained = scheduler_drained and not alive
        if runtime_drained:
            with app.state._memory_backend_lock:
                if app.state._owns_memory_backend:
                    owned_memory_backend = app.state.memory_backend
                    app.state.memory_backend = None
                    app.state._owns_memory_backend = False
        else:
            # A live worker may itself hold _memory_backend_lock while opening
            # the backend. Respect the bounded shutdown deadline: do not wait
            # on that lock or mutate ownership until every consumer is gone.
            logger.warning(
                "Skipping memory backend cleanup because managed runtime "
                "consumers did not stop"
            )
        close_memory = getattr(owned_memory_backend, "close", None)
        if callable(close_memory):
            try:
                close_memory()
            except Exception:
                logger.debug("Memory backend shutdown failed", exc_info=True)

    # Wire up trace store if traces are enabled.
    #
    # We deliberately do NOT subscribe the trace store to the bus. The chat
    # endpoints persist through a TraceCollector that calls store.save()
    # directly (mirroring system/orchestrator.py), and the collector ALSO
    # publishes TRACE_COMPLETE. A store subscribed to that same bus would
    # therefore save every agent trace twice — the second INSERT hitting the
    # UNIQUE constraint on trace_id (a 500 on every completion). Keeping the
    # collector the single writer is what makes the dual code path safe; only
    # the telemetry store is bus-subscribed (see system/builder.py).
    app.state.trace_store = None
    try:
        from openjarvis.core.config import load_config
        from openjarvis.traces.store import TraceStore

        cfg = config if config is not None else load_config()
        if cfg.traces.enabled:
            app.state.trace_store = TraceStore(db_path=cfg.traces.db_path)
    except Exception:
        pass  # traces are optional; don't block server startup

    # Wire up external analytics if enabled (PostHog) — never block startup.
    # Note: we do NOT fire app_opened here. The frontend owns that event
    # because "server started" (this code path) is not the same as "user
    # opened the app" — the server can run headless via cron, daemons,
    # or test suites.
    app.state.analytics_client = None
    app.state.analytics_bridge = None
    try:
        from openjarvis.analytics import (
            AnalyticsClient,
            EventBridge,
            is_analytics_enabled,
        )
        from openjarvis.core.config import load_config

        _cfg = config if config is not None else load_config()
        if is_analytics_enabled(_cfg.analytics):
            _client = AnalyticsClient(_cfg.analytics)
            app.state.analytics_client = _client
            _bus_ref = getattr(app.state, "bus", None)
            if _bus_ref is not None:
                _bridge = EventBridge(_bus_ref, _client)
                _bridge.start()
                app.state.analytics_bridge = _bridge

            @on_shutdown
            async def _shutdown_analytics() -> None:
                bridge = getattr(app.state, "analytics_bridge", None)
                if bridge is not None:
                    try:
                        bridge.stop()
                    except Exception:
                        pass
                client = getattr(app.state, "analytics_client", None)
                if client is not None:
                    try:
                        client.shutdown()
                    except Exception:
                        pass
    except Exception as _exc:
        logger.debug("Analytics init skipped: %s", _exc)

    # Stop the background memory service cleanly when the server shuts down.
    if memory_service is not None:

        @on_shutdown
        async def _shutdown_memory_service() -> None:
            svc = getattr(app.state, "memory_service", None)
            if svc is not None:
                try:
                    svc.stop()
                except Exception:
                    pass

    app.include_router(router)
    app.include_router(create_connectors_router())
    app.include_router(create_digest_router())
    app.include_router(upload_router)
    app.include_router(research_router)
    app.include_router(analytics_router)
    app.include_router(extensions_router)
    # Voice calls (Twilio webhooks + media stream). Pipecat loads lazily.
    from openjarvis.phone.routes import router as phone_router

    app.include_router(phone_router)
    # Local face recognition (Faces page). OpenCV loads lazily.
    from openjarvis.faces.routes import router as faces_router

    app.include_router(faces_router)
    from openjarvis.professional.routes import router as programs_router

    app.include_router(programs_router)
    # Screen help for the cursor companion (look and point, Clicky-style).
    from openjarvis.server.vision_routes import router as vision_router

    app.include_router(vision_router)
    # Minutes of meetings, video calls and conversations (who said what).
    from openjarvis.server.meeting_routes import router as meeting_router

    app.include_router(meeting_router)
    # The coach: profile, learning plans, video reviews, health, support.
    from openjarvis.server.coach_routes import router as coach_router

    app.include_router(coach_router)
    # Complex tasks: plans of foreground / background steps (checked).
    from openjarvis.server.tasks_routes import router as tasks_router

    app.include_router(tasks_router)
    # Nodes' goals, notes, audit and reviewed integrations (Browser-use,
    # OpenClaw). Registered before the Nodes router: its fixed paths
    # (/v1/nodes/capabilities, /api-key…) must win over /v1/nodes/{id}.
    from openjarvis.server.nodes_pro_routes import router as nodes_pro_router

    app.include_router(nodes_pro_router)

    from openjarvis.server.plans_routes import router as plans_router

    app.include_router(plans_router)

    # Creator: 3D, design, image, anatomy figures, plans and code.
    from openjarvis.creator.routes import router as creator_router

    app.include_router(creator_router)

    @on_shutdown
    async def _close_nodes() -> None:
        node_sessions = getattr(app.state, "nodes_mcp_sessions", None)
        if node_sessions is not None:
            await asyncio.to_thread(node_sessions.close_all)
        node_records = getattr(app.state, "nodes_records", None)
        if node_records is not None:
            node_records.close()

    from openjarvis.server.tasks_routes import skills_router

    app.include_router(skills_router)
    # Extensiones: plugins and skills in one place (connectors keep /v1/connectors).
    from openjarvis.server.hub_routes import router as hub_router

    app.include_router(hub_router)
    # Connectors like Claude's: remote MCP servers with OAuth, local ones,
    # per-tool permissions (/v1/mcp; `sergio mcp` is the same from the CLI).
    from openjarvis.server.mcp_routes import router as mcp_router

    app.include_router(mcp_router)
    # «Actualizar»: the owner's universal update command, from the app.
    from openjarvis.server.update_routes import router as update_router

    app.include_router(update_router)
    # Evolution: long-term memory (RAG + feedback) and the crewAI team.
    from openjarvis.server.evolution_routes import router as evolution_router

    app.include_router(evolution_router)
    # The same reasoning steps over a WebSocket (/v1/thinking/stream).
    from openjarvis.server.thinking_routes import router as thinking_router

    app.include_router(thinking_router)
    # OpenAI-compatible embeddings (Ollama, Gemini or the offline local one).
    from openjarvis.server.embeddings_routes import router as embeddings_router

    app.include_router(embeddings_router)
    # Background sync between devices ([sync] interval_minutes), if set up.
    try:
        from openjarvis.backup.sync import start_periodic
        from openjarvis.core.config import load_config as _load_config

        _sync_stop = start_periodic(config if config is not None else _load_config())
        if _sync_stop is not None:

            @on_shutdown
            async def _stop_sync() -> None:
                _sync_stop.set()

    except Exception as _exc:  # noqa: BLE001 - sync is optional
        logger.debug("Periodic sync not started: %s", _exc)
    # Cowork mode: describe an outcome, step away, Sergio does the rest.
    from openjarvis.server.cowork_routes import router as cowork_router

    app.include_router(cowork_router)
    # Native notch tabs: God's Eye View data and ECC guides.
    from openjarvis.server.notch_routes import router as notch_router

    app.include_router(notch_router)
    from openjarvis.server.usage_routes import router as usage_router

    app.include_router(usage_router)
    from openjarvis.server.desktop_routes import router as desktop_router

    app.include_router(desktop_router)
    # Salud: the owner's health data, insights and watch/ring/scale connections.
    from openjarvis.server.health_routes import router as health_data_router

    app.include_router(health_data_router)
    # The prompt library Sergio learns its technique from.
    from openjarvis.server.prompt_library_routes import router as prompt_library_router

    app.include_router(prompt_library_router)
    # Shortcuts wired like the fly brain: reflexes, learned paths, escape.
    from openjarvis.server.connectome_routes import router as connectome_router

    app.include_router(connectome_router)
    # The Workspace: local-first pages, files, search, export, share links.
    from openjarvis.server.workspace_routes import router as workspace_router

    app.include_router(workspace_router)
    # Agent Swarm (a burst of parallel sub-agents) and Nodes (24/7 agents).
    from openjarvis.server.swarm_routes import router as swarm_router

    app.include_router(swarm_router)
    from openjarvis.server.nodes_routes import router as nodes_router

    app.include_router(nodes_router)

    @on_shutdown
    async def _stop_nodes() -> None:
        worker = getattr(app.state, "node_worker", None)
        if worker is not None:
            worker.shutdown()

    # Sergio's Gemini voice (British gentleman) and ears.
    from openjarvis.server.voice_routes import router as voice_router

    app.include_router(voice_router)
    # Real-time conversation (Gemini Live), like a phone call.
    from openjarvis.server.live_routes import router as live_router

    app.include_router(live_router)
    # One app window: the desktop shows pages in the open window.
    from openjarvis.server.app_window_routes import router as app_window_router

    app.include_router(app_window_router)
    from openjarvis.server.reminder_routes import router as reminder_router

    app.include_router(reminder_router)
    from openjarvis.server.proyectos_routes import router as proyectos_router

    app.include_router(proyectos_router)
    from openjarvis.server.accounts_routes import router as accounts_router

    app.include_router(accounts_router)
    from openjarvis.server.pagos_routes import router as pagos_router

    app.include_router(pagos_router)
    from openjarvis.server.automatiza_routes import router as automatiza_router
    from openjarvis.server.automatiza_routes import start_loop as automatiza_loop

    app.include_router(automatiza_router)
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        from openjarvis.pagos import service as pagos_service

        pagos_service.start_expiry_loop()
        automatiza_loop()
        import threading as _threading

        _threading.Thread(target=_warm_up, name="sergio-warm", daemon=True).start()
        try:  # secret files back to owner-only if something opened them
            from openjarvis.security.permisos import tighten

            tighten()
        except Exception:  # noqa: BLE001 — never block the start
            pass
    from openjarvis.server.deep_research_routes import router as deep_research_router

    app.include_router(deep_research_router)
    # The person and their Sergio: profile, skills, model, what is running.
    from openjarvis.server.personal_routes import router as personal_router

    app.include_router(personal_router)
    try:  # videos made on a schedule (never posted without the owner)
        from openjarvis.video_essay import schedule as video_schedule

        video_schedule.start_loop()
    except Exception:  # noqa: BLE001
        logger.debug("video schedule not started", exc_info=True)
    include_all_routes(app)

    # Restore SendBlue channel bindings from database on startup
    _restore_sendblue_bindings(app)

    from openjarvis.server.upload_limits import UploadLimitsMiddleware

    @app.middleware("http")
    async def _customer_key(request, call_next):  # noqa: ANN001, ANN202
        """A signed-in customer (any approved account that is not the owner)
        is fenced in: only the customer routes answer (`customer_gate`), their
        plan and limits are their own, and their chats use their sub-key."""
        from openjarvis.accounts import provision
        from openjarvis.server.customer_gate import allowed, plan_of

        token = ""
        scheme, _, raw = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() == "bearer":
            token = raw
        user = None
        if token.startswith("sg_"):
            try:
                from openjarvis.server.accounts_routes import _store

                user = _store().session_user(token)
            except Exception:  # noqa: BLE001
                user = None
        if not user or user.get("role") == "dueño":
            return await call_next(request)
        if not allowed(request.method, request.url.path):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=403, content={"detail": "Esta parte es solo del dueño."}
            )
        marks = [
            (provision.CUSTOMER, provision.CUSTOMER.set(user["id"])),
            (
                provision.CUSTOMER_PLAN,
                provision.CUSTOMER_PLAN.set(plan_of(user["id"])),
            ),
            (
                provision.CUSTOMER_KEY,
                provision.CUSTOMER_KEY.set(provision.key_for(user["id"])),
            ),
        ]
        try:
            return await call_next(request)
        finally:
            for var, mark in reversed(marks):
                var.reset(mark)

    app.add_middleware(UploadLimitsMiddleware)
    # Answers travel compressed (the app's code is ~800 KB, ~230 KB gzipped):
    # the phone and the tunnel load it 3x faster. Live streams (SSE, audio)
    # and images are left alone by Starlette.
    from starlette.middleware.gzip import GZipMiddleware

    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)

    # Add security headers middleware
    try:
        from openjarvis.server.middleware import create_security_middleware

        middleware_cls = create_security_middleware()
        if middleware_cls is not None:
            app.add_middleware(middleware_cls)
    except Exception as exc:
        logger.debug("Security middleware init skipped: %s", exc)

    # API key authentication middleware
    if api_key:
        try:
            from openjarvis.server.auth_middleware import AuthMiddleware

            app.add_middleware(AuthMiddleware, api_key=api_key)
        except Exception as exc:
            logger.debug("Auth middleware init skipped: %s", exc)

    # Requests relayed by a tunnel or proxy (`sergio movil`) must carry the
    # phone token; requests made on this computer are unaffected.
    from openjarvis.server.mobile import RemoteAccessMiddleware

    app.add_middleware(RemoteAccessMiddleware, api_key=api_key)

    # Register CORS last so it is the outermost middleware. In addition to
    # handling preflights, this ensures browser clients can read 401 responses
    # produced directly by AuthMiddleware instead of seeing an opaque CORS
    # network error.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Outermost: through the public tunnel only the phone/WhatsApp webhooks
    # are reachable (the rest of the API stays local-only).
    from openjarvis.phone.public_guard import PublicExposureGuard

    def _guard_config() -> Any:
        from openjarvis.core.config import load_config

        return getattr(app.state, "config", None) or load_config()

    app.add_middleware(PublicExposureGuard, config_getter=_guard_config)

    # Mount webhook routes (always — SendBlue may be configured dynamically)
    if webhook_config:
        try:
            from openjarvis.server.webhook_routes import (
                create_webhook_router,
            )

            webhook_router = create_webhook_router(
                bridge=channel_bridge,
                twilio_auth_token=webhook_config.get("twilio_auth_token", ""),
                bluebubbles_password=webhook_config.get("bluebubbles_password", ""),
                whatsapp_verify_token=webhook_config.get("whatsapp_verify_token", ""),
                whatsapp_app_secret=webhook_config.get("whatsapp_app_secret", ""),
            )
            app.include_router(webhook_router)
        except Exception as exc:
            logger.debug("Webhook routes init skipped: %s", exc)

    # Serve static frontend assets if the static/ directory exists
    from openjarvis.server.webroot import web_dir

    static_dir = web_dir()
    if static_dir.is_dir():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount(
                "/assets",
                _NoCacheStaticFiles(directory=assets_dir),
                name="static-assets",
            )

        @app.get("/{full_path:path}")
        async def spa_catch_all(full_path: str):
            """Serve static files directly, fall back to index.html for SPA routes."""
            if full_path:
                candidate = (static_dir / full_path).resolve()
                # Path traversal prevention
                resolved_root = static_dir.resolve()
                if candidate.is_relative_to(resolved_root) and candidate.is_file():
                    return FileResponse(candidate, headers=_NO_CACHE_HEADERS)
            return FileResponse(
                static_dir / "index.html",
                headers=_NO_CACHE_HEADERS,
            )

    return app


__all__ = ["create_app"]

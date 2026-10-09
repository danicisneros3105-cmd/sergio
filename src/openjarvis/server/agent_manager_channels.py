"""Managed-agent channel bindings (``/{agent_id}/channels``) and messaging
(``/{agent_id}/messages``, including streamed replies).

Split out of ``agent_manager_routes.py``; its helpers are looked up on that
module at call time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

import openjarvis.server.agent_manager_routes as _amr
from openjarvis.agents.manager import AgentManager


def add_channel_and_message_routes(
    agents_router: APIRouter, manager: AgentManager
) -> None:
    """Channel bindings and messaging routes of a managed agent."""
    # ── Channel bindings ─────────────────────────────────────

    @agents_router.get("/{agent_id}/channels")
    async def list_channels(agent_id: str) -> Dict[str, Any]:
        return {"bindings": manager.list_channel_bindings(agent_id)}

    @agents_router.post("/{agent_id}/channels")
    async def bind_channel(
        agent_id: str,
        req: _amr.BindChannelRequest,
        request: Request,
    ) -> Dict[str, Any]:
        if not manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")
        binding = manager.bind_channel(
            agent_id,
            channel_type=req.channel_type,
            config=req.config,
            routing_mode=req.routing_mode,
        )

        # Start iMessage daemon if binding iMessage
        if req.channel_type == "imessage":
            identifier = (req.config or {}).get("identifier", "")
            if identifier:
                try:
                    from openjarvis.channels.imessage_daemon import (
                        is_running,
                        run_daemon,
                    )

                    if not is_running():
                        import threading

                        engine = getattr(request.app.state, "engine", None)
                        if engine:
                            tools = _amr._build_deep_research_tools(
                                engine=engine, model=""
                            )
                            if tools:
                                from openjarvis.agents.deep_research import (
                                    DeepResearchAgent,
                                )

                                agent_inst = DeepResearchAgent(
                                    engine=engine,
                                    model=getattr(engine, "_model", ""),
                                    tools=tools,
                                    bus=getattr(request.app.state, "bus", None),
                                    capability_policy=getattr(
                                        request.app.state,
                                        "capability_policy",
                                        None,
                                    ),
                                    rate_limiter=getattr(
                                        request.app.state, "rate_limiter", None
                                    ),
                                    agent_id=agent_id,
                                    interactive=True,
                                    confirm_callback=lambda _prompt: True,
                                )

                                def handler(text: str) -> str:
                                    result = agent_inst.run(text)
                                    return result.content or "No results."

                                t = threading.Thread(
                                    target=run_daemon,
                                    kwargs={
                                        "chat_identifier": identifier,
                                        "handler": handler,
                                    },
                                    daemon=True,
                                )
                                t.start()
                except Exception as exc:
                    _amr.logger.warning("Failed to start iMessage daemon: %s", exc)

        # Initialize SendBlue channel if binding sendblue
        if req.channel_type == "sendblue":
            config = req.config or {}
            api_key_id = config.get("api_key_id", "")
            api_secret_key = config.get("api_secret_key", "")
            from_number = config.get("from_number", "")
            if api_key_id and api_secret_key:
                try:
                    from openjarvis.channels.sendblue import (
                        SendBlueChannel,
                    )

                    sb_channel = SendBlueChannel(
                        api_key_id=api_key_id,
                        api_secret_key=api_secret_key,
                        from_number=from_number,
                    )
                    sb_channel.connect()
                    # Store on app state so webhook route can use it
                    request.app.state.sendblue_channel = sb_channel

                    # Create or update the channel bridge
                    bridge = getattr(request.app.state, "channel_bridge", None)
                    if bridge and hasattr(bridge, "_channels"):
                        bridge._channels["sendblue"] = sb_channel
                    else:
                        # Create a new ChannelBridge with DeepResearch
                        from openjarvis.server.channel_bridge import (
                            ChannelBridge,
                        )
                        from openjarvis.server.session_store import (
                            SessionStore,
                        )

                        session_store = SessionStore()
                        engine = getattr(request.app.state, "engine", None)
                        dr_agent = None
                        if engine:
                            tools = _amr._build_deep_research_tools(
                                engine=engine, model=""
                            )
                            if tools:
                                from openjarvis.agents.deep_research import (
                                    DeepResearchAgent,
                                )

                                model_name = getattr(engine, "_model", "") or getattr(
                                    request.app.state,
                                    "model",
                                    "",
                                )
                                dr_agent = DeepResearchAgent(
                                    engine=engine,
                                    model=model_name,
                                    tools=tools,
                                    bus=getattr(request.app.state, "bus", None),
                                    capability_policy=getattr(
                                        request.app.state,
                                        "capability_policy",
                                        None,
                                    ),
                                    rate_limiter=getattr(
                                        request.app.state, "rate_limiter", None
                                    ),
                                    agent_id=agent_id,
                                    interactive=True,
                                    confirm_callback=lambda _prompt: True,
                                )
                        bus = getattr(request.app.state, "bus", None)
                        if bus is None:
                            from openjarvis.core.events import EventBus

                            bus = EventBus()
                        bridge = ChannelBridge(
                            channels={"sendblue": sb_channel},
                            session_store=session_store,
                            bus=bus,
                            agent_manager=manager,
                            deep_research_agent=dr_agent,
                        )
                        request.app.state.channel_bridge = bridge

                    _amr.logger.info(
                        "SendBlue channel connected: %s",
                        from_number,
                    )
                except Exception as exc:
                    _amr.logger.warning("Failed to init SendBlue channel: %s", exc)

        # Start Slack via slack-bolt Socket Mode
        if req.channel_type == "slack":
            config = req.config or {}
            bot_token = config.get("bot_token", "")
            app_token = config.get("app_token", "")
            if bot_token and app_token:
                try:
                    from openjarvis.channels.slack_daemon import (
                        start_slack_daemon,
                    )
                    from openjarvis.channels.slack_daemon import (
                        stop_daemon as stop_slack,
                    )

                    # Stop any existing daemon first
                    stop_slack()

                    # Spawn as subprocess (reliable)
                    srv_model = (
                        getattr(
                            getattr(
                                request.app.state,
                                "engine",
                                None,
                            ),
                            "_model",
                            "qwen3.5:9b",
                        )
                        or "qwen3.5:9b"
                    )
                    pid = start_slack_daemon(
                        bot_token=bot_token,
                        app_token=app_token,
                        model=srv_model,
                    )
                    _amr.logger.info(
                        "Slack daemon started (PID %d)",
                        pid,
                    )
                except Exception as exc:
                    _amr.logger.warning(
                        "Failed to start Slack: %s",
                        exc,
                    )

        return binding

    @agents_router.delete("/{agent_id}/channels/{binding_id}")
    async def unbind_channel(
        agent_id: str,
        binding_id: str,
        request: Request,
    ) -> Dict[str, Any]:
        try:
            binding = manager._get_binding(binding_id)
            if binding:
                ch_type = binding.get("channel_type")
                if ch_type == "imessage":
                    from openjarvis.channels.imessage_daemon import (
                        stop_daemon,
                    )

                    stop_daemon()
                elif ch_type == "slack":
                    from openjarvis.channels.slack_daemon import (
                        stop_daemon as stop_slack_daemon,
                    )

                    stop_slack_daemon()
        except Exception:
            pass
        manager.unbind_channel(binding_id)
        return {"status": "unbound"}

    # ── Messaging ────────────────────────────────────────────

    @agents_router.get("/{agent_id}/messages")
    def list_messages(agent_id: str) -> Dict[str, Any]:
        return {"messages": manager.list_messages(agent_id)}

    @agents_router.post("/{agent_id}/messages")
    async def send_message(
        agent_id: str, req: _amr.SendMessageRequest, request: Request
    ) -> Any:
        agent_record = manager.get_agent(agent_id)
        if not agent_record:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Auto-recover error-state agents on immediate messages
        if req.mode == "immediate" and agent_record["status"] in (
            "error",
            "needs_attention",
        ):
            manager.update_agent(agent_id, status="idle")

        stream_tick_acquired = False
        stream_engine = None
        if req.stream:
            stream_engine = getattr(request.app.state, "engine", None)
            if stream_engine is not None:
                # Unlike the queued/immediate paths, streaming runs directly
                # in the request, so it must acquire the same tick guard here.
                try:
                    manager.start_tick(agent_id)
                    stream_tick_acquired = True
                except ValueError:
                    raise HTTPException(
                        status_code=409,
                        detail="Agent is already running",
                    )

        # Store user message in DB (always, regardless of stream mode)
        try:
            msg = manager.send_message(agent_id, req.content, mode=req.mode)
        except Exception:
            if stream_tick_acquired:
                manager.end_tick(agent_id)
            raise

        if not req.stream and req.mode != "immediate":
            return msg

        if not req.stream and req.mode == "immediate":
            # Non-streaming immediate: trigger a background tick so the
            # agent processes the message, then return the stored msg.
            # Re-use the server's existing system (correct model/engine).
            import time as _time

            from openjarvis.agents.executor import AgentExecutor

            _app_state = request.app.state
            _srv_engine = getattr(_app_state, "engine", None)
            _srv_model = getattr(_app_state, "model", "")
            _srv_config = getattr(_app_state, "config", None)
            _srv_bus = _amr._get_runtime_event_bus(_app_state)

            def _immediate_tick() -> None:
                _start = _time.time()
                _amr.logger.info(
                    "Immediate tick starting for agent %s (model=%s)",
                    agent_id,
                    _srv_model,
                )
                try:
                    _ts2 = getattr(_app_state, "trace_store", None)
                    executor = AgentExecutor(
                        manager=manager,
                        event_bus=_srv_bus,
                        trace_store=_ts2,
                    )
                    system = _amr._make_lightweight_system(
                        _srv_engine,
                        _srv_model,
                        _srv_config,
                        _app_state,
                    )
                    executor.set_system(system)
                    _amr.logger.info(
                        "Immediate tick: system ready in %.1fs, "
                        "executing tick for agent %s",
                        _time.time() - _start,
                        agent_id,
                    )
                    executor.execute_tick(agent_id)
                    _amr.logger.info(
                        "Immediate tick completed for agent %s in %.1fs",
                        agent_id,
                        _time.time() - _start,
                    )
                except Exception as exc:
                    _amr.logger.error(
                        "Immediate tick failed for agent %s: %s",
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
                _amr._start_managed_worker(
                    _app_state,
                    _immediate_tick,
                    name=f"managed-agent-immediate-{agent_id}",
                )
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc))
            return msg

        # --- Streaming mode: run agent and return SSE response ---
        engine = stream_engine
        bus = getattr(request.app.state, "bus", None)
        if engine is None:
            raise HTTPException(
                status_code=503,
                detail="Engine not available for streaming",
            )

        try:
            return await _amr._stream_managed_agent(
                manager=manager,
                agent_record=agent_record,
                user_content=req.content,
                message_id=msg["id"],
                engine=engine,
                bus=bus,
                app_state=request.app.state,
                on_complete=lambda: manager.end_tick(agent_id),
            )
        except Exception:
            if stream_tick_acquired:
                manager.end_tick(agent_id)
            raise


__all__ = ["add_channel_and_message_routes"]

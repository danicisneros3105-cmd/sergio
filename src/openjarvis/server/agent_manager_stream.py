"""Streaming chat with a managed agent (SSE): tool resolution with cached MCP
tools, deep-research mode, real token streaming, tick bookkeeping.

Split out of ``agent_manager_routes.py``; its helpers are looked up on that
module at call time, so behaviour (and anything patched there) is
unchanged.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

import openjarvis.server.agent_manager_routes as _amr
from openjarvis.agents.manager import AgentManager


async def _stream_managed_agent(
    *,
    manager: AgentManager,
    agent_record: Dict[str, Any],
    user_content: str,
    message_id: str,
    engine: Any,
    bus: Any,
    app_state: Any = None,
    on_complete: Optional[Callable[[], None]] = None,
) -> _amr.StreamingResponse:
    """Run a managed agent with real LLM token streaming via SSE.

    Uses ``engine.stream_full()`` to yield tokens as they arrive from the
    LLM. Supports multi-turn tool-calling: when the model emits tool_calls,
    they are executed and the results fed back for the next turn. When
    ``on_complete`` is provided, it runs after either streaming branch has
    finished its response-local cleanup.
    """
    import json
    import uuid

    from starlette.background import BackgroundTask

    from openjarvis.core.types import Message, Role

    agent_id = agent_record["id"]

    completion_lock = _amr.threading.Lock()
    completion_called = False

    def _complete_stream() -> None:
        nonlocal completion_called
        with completion_lock:
            if completion_called or on_complete is None:
                return
            completion_called = True
        try:
            on_complete()
        except Exception:
            _amr.logger.warning("Managed agent stream cleanup failed", exc_info=True)

    config = agent_record.get("config", {})
    # Resolve the model: prefer the agent's own config, then the server's
    # resolved model (app.state.model — what the engine was booted with),
    # and only then the legacy engine._model attr. OllamaEngine takes the
    # model per-call and exposes no _model attr, so without the app_state
    # fallback this resolved to "" and Ollama 400'd on an empty model.
    model = (
        config.get("model")
        or getattr(app_state, "model", None)
        or getattr(engine, "_model", "")
    )
    system_prompt = config.get("system_prompt")
    temperature = config.get("temperature", 0.7)
    max_tokens = config.get("max_tokens", 1024)
    max_turns = config.get("max_turns", 10)

    # Build conversation messages from history + current input
    llm_messages: List[Message] = []

    # Wire the SystemPromptBuilder to inject SOUL.md / MEMORY.md / USER.md
    # persona files (parity with the CLI/ask path) — see #431.
    app_config = getattr(app_state, "config", None)
    if app_config is None:
        from openjarvis.core.config import load_config

        app_config = load_config()

    final_system_prompt = _amr._build_managed_system_prompt(
        system_prompt or "", app_config
    )

    if final_system_prompt and final_system_prompt.strip():
        llm_messages.append(
            Message(role=Role.SYSTEM, content=final_system_prompt.strip())
        )

    # Resolve one live toolkit for every managed-agent path.  The same
    # instances are advertised to the model and used for execution below.
    agent_type = agent_record.get("agent_type", "")
    mcp_adapters: Dict[str, Any] = {}
    mcp_clients: list[Any] = []
    if app_state is not None and config.get("mcp_tools", True) is not False:
        try:
            _, mcp_adapters = _amr._get_mcp_tools(app_state)
            mcp_clients = list(getattr(app_state, "_mcp_clients", []))
        except Exception as exc:
            _amr.logger.warning(
                "Failed to get MCP tools for managed agent: %s",
                exc,
                exc_info=True,
            )

    memory_backend = _amr._get_or_create_memory_backend(app_state, app_config)
    channel_backend = getattr(app_state, "channel_backend", None) or getattr(
        app_state, "channel_bridge", None
    )
    resolved_toolkit = _amr.resolve_agent_tools(
        agent_record,
        engine=engine,
        model=model,
        memory_backend=memory_backend,
        channel_backend=channel_backend,
        mcp_tools=mcp_adapters.values(),
        mcp_clients=mcp_clients,
        knowledge_db_path=getattr(app_state, "knowledge_db_path", None),
    )

    # Load prior conversation context (DESC order, reverse for chronological).
    # Replaying recorded tool_calls (assistant tool-use + tool results) keeps
    # multi-turn tool behaviour from regressing to fabricated output (#382).
    history = manager.list_messages(agent_id, limit=50)
    llm_messages.extend(_amr._replay_history_messages(history, message_id))

    # Append the current user message
    llm_messages.append(Message(role=Role.USER, content=user_content))

    # Mark the user message as delivered
    manager.mark_message_delivered(message_id)

    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # For deep_research agents: run the full agent loop, not raw streaming
    if agent_type == "deep_research":
        dr_tools = resolved_toolkit.instances
        if dr_tools:
            worker_owns_tick = _amr.threading.Event()

            def _complete_research_response() -> None:
                # A disconnected/timed-out response cannot release a tick
                # while its synchronous research worker is still executing.
                if not worker_owns_tick.is_set():
                    try:
                        resolved_toolkit.close()
                    finally:
                        _complete_stream()

            async def generate_deep_research() -> AsyncIterator[str]:
                """Run DeepResearchAgent in thread, stream progress + result."""
                import asyncio
                import queue
                import time as _dr_time

                from openjarvis.agents.deep_research import DeepResearchAgent

                progress_q: queue.Queue = queue.Queue()

                # Log query start
                _dr_start = _dr_time.time()
                try:
                    manager.add_learning_log(
                        agent_id,
                        "query_start",
                        f"Query: {user_content[:100]}",
                        {"full_query": user_content},
                    )
                except Exception as _log_exc:
                    _amr.logger.warning(
                        "Failed to log query_start: %s",
                        _log_exc,
                    )

                # Patch the agent's tool executor to emit progress
                dr_agent = DeepResearchAgent(
                    engine=engine,
                    model=model,
                    tools=dr_tools,
                    bus=getattr(app_state, "bus", None),
                    capability_policy=getattr(app_state, "capability_policy", None),
                    rate_limiter=getattr(app_state, "rate_limiter", None),
                    agent_id=agent_id,
                    max_turns=int(config.get("max_turns", 8)),
                    temperature=float(config.get("temperature", 0.3)),
                    interactive=True,
                    confirm_callback=lambda _prompt: True,
                )
                if resolved_toolkit.mcp_clients:
                    dr_agent._mcp_clients = resolved_toolkit.mcp_clients

                # Wrap the executor to capture tool calls
                original_execute = dr_agent._executor.execute

                def _tracked_execute(tc: Any) -> Any:
                    tool_name = tc.name
                    full_args = tc.arguments or ""
                    args_str = full_args[:80]
                    # Log tool call start
                    try:
                        manager.add_learning_log(
                            agent_id,
                            "tool_call",
                            f"Calling {tool_name}: {args_str}",
                            {"tool": tool_name, "arguments": full_args},
                        )
                    except Exception as _tc_exc:
                        _amr.logger.warning("Log tool_call failed: %s", _tc_exc)

                    progress_q.put(
                        {
                            "type": "tool_start",
                            "tool": tool_name,
                            "args": args_str,
                            "full_args": full_args,
                        }
                    )
                    _tool_start = _dr_time.monotonic()
                    result = original_execute(tc)
                    _tool_latency_ms = (_dr_time.monotonic() - _tool_start) * 1000

                    # Log tool result
                    try:
                        _ok = "succeeded" if result.success else "failed"
                        _clen = len(result.content) if result.content else 0
                        manager.add_learning_log(
                            agent_id,
                            "tool_result",
                            f"{tool_name} {_ok} ({_clen} chars)",
                            {
                                "tool": tool_name,
                                "success": result.success,
                                "output_length": _clen,
                            },
                        )
                    except Exception as _tr_exc:
                        _amr.logger.warning("Log tool_result failed: %s", _tr_exc)

                    progress_q.put(
                        {
                            "type": "tool_end",
                            "tool": tool_name,
                            "arguments": full_args,
                            "success": result.success,
                            "latency": _tool_latency_ms,
                            "result": result.content or "",
                        }
                    )
                    return result

                dr_agent._executor.execute = _tracked_execute

                def _run_agent() -> None:
                    agent_metadata = {}
                    try:
                        result = dr_agent.run(user_content)
                        content = result.content or "No results found."
                        agent_metadata = result.metadata or {}
                    except Exception as exc:
                        content = f"Error: {exc}"
                    finally:
                        resolved_toolkit.close()

                    elapsed = _dr_time.time() - _dr_start

                    # Log BEFORE queue put (put triggers SSE end)
                    try:
                        is_err = content.startswith("Error:")
                        manager.add_learning_log(
                            agent_id,
                            "query_error" if is_err else "query_complete",
                            f"{'Error' if is_err else 'Response'}: "
                            f"{len(content)} chars in {elapsed:.1f}s",
                            {
                                "response_length": len(content),
                                "elapsed_seconds": round(elapsed, 2),
                            },
                        )
                    except Exception as _qc_exc:
                        _amr.logger.warning(
                            "Log failed: %s",
                            _qc_exc,
                        )

                    progress_q.put(
                        {
                            "type": "error" if content.startswith("Error:") else "done",
                            "content": content,
                            "metadata": agent_metadata,
                            "elapsed": elapsed,
                        }
                    )

                def _run_with_tick_cleanup() -> None:
                    try:
                        _run_agent()
                    finally:
                        _complete_stream()

                worker_owns_tick.set()
                try:
                    _amr._start_managed_worker(
                        app_state,
                        _run_with_tick_cleanup,
                        name=f"managed-agent-deep-research-{agent_id}",
                    )
                except Exception as exc:
                    worker_owns_tick.clear()
                    _complete_research_response()
                    progress_q.put(
                        {
                            "type": "error",
                            "content": f"Error: {exc}",
                            "metadata": {},
                            "elapsed": _dr_time.time() - _dr_start,
                        }
                    )

                # Collect tool calls from deep-research so we can persist them
                # alongside the final response (and the UI can re-render them
                # after a page reload).
                dr_tool_calls: List[Dict[str, Any]] = []
                _pending_dr_starts: Dict[str, str] = {}

                # Stream progress events and final content
                while True:
                    try:
                        event = await asyncio.to_thread(progress_q.get, timeout=600)
                    except Exception:
                        # Timeout
                        yield _amr._sse_chunk(chunk_id, model, "Agent timed out.")
                        break

                    if event["type"] == "tool_start":
                        tool = event["tool"]
                        args = event.get("args", "")
                        full_args = event.get("full_args", "")
                        _pending_dr_starts[tool] = full_args
                        # Structured event so the UI can render a tool_call
                        # message card (same shape as the non-DR path).
                        _start_payload = json.dumps(
                            {"tool": tool, "arguments": full_args}
                        )
                        yield f"event: tool_call_start\ndata: {_start_payload}\n\n"
                        # Keep the human-readable progress label for the
                        # thinking-bubble fallback.
                        label = _amr._tool_progress_label(tool, args)
                        progress_data = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": None,
                                    "tool_progress": label,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(progress_data)}\n\n"

                    elif event["type"] == "tool_end":
                        tool = event["tool"]
                        dr_tool_calls.append(
                            {
                                "tool": tool,
                                "arguments": event.get(
                                    "arguments", _pending_dr_starts.get(tool, "")
                                ),
                                "result": event.get("result", ""),
                                "success": bool(event.get("success", False)),
                                "latency": float(event.get("latency", 0.0)),
                            }
                        )
                        _pending_dr_starts.pop(tool, None)
                        _end_payload = json.dumps(
                            {
                                "tool": tool,
                                "success": bool(event.get("success", False)),
                                "latency": float(event.get("latency", 0.0)),
                                "result": event.get("result", ""),
                            }
                        )
                        yield f"event: tool_call_end\ndata: {_end_payload}\n\n"

                    elif event["type"] in ("done", "error"):
                        content = event["content"]
                        meta = event.get("metadata", {})
                        elapsed_s = event.get("elapsed", 0)

                        # Stream content word-by-word
                        words = content.split(" ")
                        for i, word in enumerate(words):
                            token = word if i == 0 else " " + word
                            yield _amr._sse_chunk(chunk_id, model, token)

                        # Build usage + telemetry
                        prompt_tok = meta.get("prompt_tokens", 0)
                        comp_tok = meta.get("completion_tokens", 0)
                        total_tok = meta.get("total_tokens", 0)
                        word_count = len(words)
                        speed = round(word_count / elapsed_s) if elapsed_s > 0 else 0

                        # Final chunk with usage + telemetry
                        finish_data = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": prompt_tok,
                                "completion_tokens": comp_tok,
                                "total_tokens": total_tok or (prompt_tok + comp_tok),
                            },
                            "telemetry": {
                                "engine": "ollama",
                                "model_id": model,
                                "total_ms": round(elapsed_s * 1000),
                                "tokens_per_sec": speed,
                                "tool_calls": len(meta.get("sources", [])),
                            },
                        }
                        yield f"data: {json.dumps(finish_data)}\n\n"
                        yield "data: [DONE]\n\n"

                        # Persist (with the tool calls captured during
                        # the deep-research turn so they survive reload).
                        manager.store_agent_response(
                            agent_id,
                            content,
                            tool_calls=dr_tool_calls or None,
                        )
                        break

            async def guarded_deep_research() -> AsyncIterator[str]:
                try:
                    async for chunk in generate_deep_research():
                        yield chunk
                finally:
                    _complete_research_response()

            return _amr.StreamingResponse(
                guarded_deep_research(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
                background=BackgroundTask(_complete_research_response),
            )

    # The canonical resolver exposes the same live instances as OpenAI specs
    # for engines that run the generic streaming loop.
    stream_kwargs: Dict[str, Any] = {}
    if resolved_toolkit.openai_specs:
        stream_kwargs["tools"] = resolved_toolkit.openai_specs

    from openjarvis.tools._stubs import ToolExecutor

    resolved_by_name = resolved_toolkit.by_name
    # Previously constructed with no capability_policy/rate_limiter/agent_id
    # at all — this is the live SSE chat path for managed agents (what
    # Tailscale/remote exposure actually hits), so tool calls made here ran
    # with zero RBAC gating and zero rate limiting regardless of config.
    stream_tool_executor = ToolExecutor(
        tools=resolved_toolkit.instances,
        bus=bus,
        interactive=True,
        confirm_callback=lambda _prompt: True,
        capability_policy=getattr(app_state, "capability_policy", None),
        rate_limiter=getattr(app_state, "rate_limiter", None),
        agent_id=agent_id,
    )
    # The executor is request-local, but the conversation is not: seed taint
    # from replayed history so data returned by a tool in an earlier request
    # remains protected in this turn.
    stream_tool_executor.begin_session(
        [message.text for message in llm_messages if message.text]
    )

    # Forward any per-agent sampler params (repetition_penalty, top_p, …) so
    # locally-hosted models can be tuned per agent (#386).
    stream_kwargs.update(_amr._sampler_kwargs(config))

    # Shared state between the generator and the BackgroundTask that
    # runs after the SSE response completes (or the client disconnects
    # mid-stream). Starlette guarantees the BackgroundTask runs in both
    # cases, so we use it as the single, reliable persistence point.
    persist_state: Dict[str, Any] = {
        "content": "",
        "tool_calls": [],
        "persisted": False,
    }

    def _persist_final() -> None:
        if persist_state["persisted"]:
            return
        persist_state["persisted"] = True
        if persist_state["content"]:
            try:
                manager.store_agent_response(
                    agent_id,
                    persist_state["content"],
                    tool_calls=persist_state["tool_calls"] or None,
                )
            except Exception as store_exc:
                _amr.logger.error(
                    "Failed to store agent response: %s",
                    store_exc,
                    exc_info=True,
                )
        try:
            content = persist_state["content"] or ""
            manager.add_learning_log(
                agent_id,
                "query_complete",
                f"Response: {len(content)} chars, "
                f"{len(persist_state['tool_calls'])} tool calls",
                {
                    "response_length": len(content),
                    "tool_calls": len(persist_state["tool_calls"]),
                },
            )
        except Exception as _qc_exc:
            _amr.logger.warning("Log query_complete failed: %s", _qc_exc)

    def _finalize_stream() -> None:
        try:
            _persist_final()
        finally:
            try:
                resolved_toolkit.close()
            finally:
                _complete_stream()

    async def generate() -> AsyncIterator[str]:
        """Async generator yielding SSE-formatted chunks with real token streaming."""

        collected_content = ""
        collected_tool_calls: List[Dict[str, Any]] = []
        messages_for_llm = list(llm_messages)
        turns = 0

        import time as _lgtime

        _query_start_ts = _lgtime.time()
        try:
            manager.add_learning_log(
                agent_id,
                "query_start",
                f"Query: {user_content[:100]}",
                {"full_query": user_content},
            )
        except Exception as _qs_exc:
            _amr.logger.warning("Log query_start failed: %s", _qs_exc)

        while turns < max_turns:
            turns += 1
            turn_content = ""
            tool_call_fragments: Dict[int, Dict[str, Any]] = {}
            current_finish_reason = None

            try:
                async for chunk in engine.stream_full(
                    messages_for_llm,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **stream_kwargs,
                ):
                    # Stream content tokens immediately to the client
                    if chunk.content:
                        turn_content += chunk.content
                        # Mirror partial content so a disconnect during
                        # generation still saves what we've produced.
                        persist_state["content"] = collected_content + turn_content
                        chunk_data = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": chunk.content},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n"

                    # Accumulate tool_call fragments
                    if chunk.tool_calls:
                        _amr._merge_tool_call_fragments(
                            tool_call_fragments,
                            chunk.tool_calls,
                        )

                    if chunk.finish_reason:
                        current_finish_reason = chunk.finish_reason

            except Exception as exc:
                _amr.logger.error("Managed agent stream error: %s", exc, exc_info=True)
                error_data = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": f"Error: {exc}"},
                            "finish_reason": "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Handle tool calls: execute tools and loop for next turn
            if tool_call_fragments and current_finish_reason == "tool_calls":
                # Build the assistant message with tool_calls
                sorted_tcs = [
                    tool_call_fragments[i] for i in sorted(tool_call_fragments.keys())
                ]

                # Add assistant message with tool_calls to conversation
                from openjarvis.core.types import ToolCall as MsgToolCall

                assistant_msg = Message(
                    role=Role.ASSISTANT,
                    content=turn_content or None,
                    tool_calls=[
                        MsgToolCall(
                            id=tc["id"],
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"],
                        )
                        for tc in sorted_tcs
                    ],
                )
                messages_for_llm.append(assistant_msg)

                # Execute each tool call and append results. Emit
                # tool_call_start/tool_call_end around each call so the UI
                # can render them live (same event names as the main chat
                # in stream_bridge.py).
                import time as _time

                for tc in sorted_tcs:
                    tool_name = tc["function"]["name"]
                    tool_args = tc["function"]["arguments"]
                    tool_result_content = f"Tool '{tool_name}' not available"
                    tool_succeeded = False

                    _start_payload = json.dumps(
                        {"tool": tool_name, "arguments": tool_args}
                    )
                    yield f"event: tool_call_start\ndata: {_start_payload}\n\n"
                    try:
                        manager.add_learning_log(
                            agent_id,
                            "tool_call",
                            f"Calling {tool_name}: {tool_args[:80]}",
                            {"tool": tool_name, "arguments": tool_args or ""},
                        )
                    except Exception as _tc_exc:
                        _amr.logger.warning("Log tool_call failed: %s", _tc_exc)
                    tool_start_ms = _time.monotonic() * 1000

                    try:
                        if tool_name in resolved_by_name:
                            result = stream_tool_executor.execute(
                                MsgToolCall(
                                    id=tc["id"],
                                    name=tool_name,
                                    arguments=tool_args,
                                )
                            )
                            tool_result_content = result.content
                            tool_succeeded = bool(result.success)
                        else:
                            _amr.logger.warning(
                                "Tool '%s' was not included in the resolved toolkit",
                                tool_name,
                            )
                    except Exception as tool_exc:
                        _amr.logger.error(
                            "Tool execution error for %s: %s",
                            tool_name,
                            tool_exc,
                            exc_info=True,
                        )
                        tool_result_content = f"Error executing {tool_name}: {tool_exc}"

                    tool_latency_ms = (_time.monotonic() * 1000) - tool_start_ms
                    collected_tool_calls.append(
                        {
                            "tool": tool_name,
                            "arguments": tool_args,
                            "result": tool_result_content,
                            "success": tool_succeeded,
                            "latency": tool_latency_ms,
                        }
                    )
                    # Update the shared persist state so mid-stream
                    # disconnects still capture already-executed tools.
                    persist_state["tool_calls"] = list(collected_tool_calls)
                    try:
                        _ok = "succeeded" if tool_succeeded else "failed"
                        _clen = len(tool_result_content) if tool_result_content else 0
                        manager.add_learning_log(
                            agent_id,
                            "tool_result",
                            f"{tool_name} {_ok} ({_clen} chars)",
                            {
                                "tool": tool_name,
                                "success": tool_succeeded,
                                "output_length": _clen,
                            },
                        )
                    except Exception as _tr_exc:
                        _amr.logger.warning("Log tool_result failed: %s", _tr_exc)
                    _end_payload = json.dumps(
                        {
                            "tool": tool_name,
                            "success": tool_succeeded,
                            "latency": tool_latency_ms,
                            "result": tool_result_content,
                        }
                    )
                    yield f"event: tool_call_end\ndata: {_end_payload}\n\n"

                    # Add tool result message to conversation
                    messages_for_llm.append(
                        Message(
                            role=Role.TOOL,
                            content=tool_result_content,
                            tool_call_id=tc["id"],
                            name=tool_name,
                        )
                    )

                # Continue to next turn (loop back to stream_full)
                collected_content += turn_content
                # Mirror to shared state so BackgroundTask can persist
                # even if the client disconnects mid-stream.
                persist_state["content"] = collected_content
                persist_state["tool_calls"] = list(collected_tool_calls)
                continue

            # No tool calls — this is the final response
            collected_content += turn_content
            persist_state["content"] = collected_content
            persist_state["tool_calls"] = list(collected_tool_calls)
            break

        # Final chunk with finish_reason
        final_data = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(final_data)}\n\n"
        yield "data: [DONE]\n\n"

    return _amr.StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        background=BackgroundTask(_finalize_stream),
    )


def _get_mcp_tools_locked(
    app_state: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Discover MCP tools while the runtime's discovery lock is held."""

    if getattr(app_state, "_managed_runtime_stopping", False):
        return [], {}

    cached = getattr(app_state, "_mcp_tools_cache", None)
    if cached is not None:
        return cached

    preloaded = list(getattr(app_state, "mcp_tools", []) or [])
    if preloaded:
        adapters_by_name: Dict[str, Any] = {}
        for tool in preloaded:
            spec = getattr(tool, "spec", None)
            if spec is not None and spec.name not in adapters_by_name:
                adapters_by_name[spec.name] = tool
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.spec.name,
                    "description": tool.spec.description,
                    "parameters": tool.spec.parameters,
                },
            }
            for tool in adapters_by_name.values()
        ]
        app_state._mcp_tools_cache = (openai_tools, adapters_by_name)
        return app_state._mcp_tools_cache

    from openjarvis.core.config import load_config, resolve_mcp_servers

    openai_tools: List[Dict[str, Any]] = []
    adapters_by_name: Dict[str, Any] = {}

    try:
        app_config = load_config()
    except Exception as exc:
        _amr.logger.warning("Failed to load config for MCP discovery: %s", exc)
        return openai_tools, adapters_by_name

    if not app_config.tools.mcp.enabled or not app_config.tools.mcp.servers:
        return openai_tools, adapters_by_name

    from openjarvis.mcp.client import MCPClient
    from openjarvis.mcp.transport import StdioTransport, StreamableHTTPTransport
    from openjarvis.tools.mcp_adapter import MCPToolProvider

    try:
        server_list = resolve_mcp_servers(
            app_config.tools.mcp.servers,
            app_config._config_dir,
        )
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        _amr.logger.warning("Failed to parse MCP server config: %s", exc)
        return openai_tools, adapters_by_name

    for server_cfg in server_list:
        cfg = server_cfg
        name = cfg.get("name", "<unnamed>")
        url = cfg.get("url")
        # Bearer token from config — mirrors the builder.py fix for #461.
        token = cfg.get("token")
        command = cfg.get("command", "")
        args = cfg.get("args", [])

        client = None
        try:
            if url:
                transport = StreamableHTTPTransport(url=url, token=token)
            elif command:
                transport = StdioTransport(command=[command] + args)
            else:
                _amr.logger.warning(
                    "MCP server '%s' has neither 'url' nor 'command' — skipping",
                    name,
                )
                continue

            client = MCPClient(transport)
            if not _amr._register_mcp_client(app_state, client):
                client.close()
                client = None
                break
            client.initialize()

            provider = MCPToolProvider(client)
            discovered = provider.discover()

            # Per-server tool filtering
            include_tools = set(cfg.get("include_tools", []))
            exclude_tools = set(cfg.get("exclude_tools", []))
            if include_tools:
                discovered = [t for t in discovered if t.spec.name in include_tools]
            if exclude_tools:
                discovered = [t for t in discovered if t.spec.name not in exclude_tools]

            staged: list[tuple[Any, Any]] = []
            staged_names = set(adapters_by_name)
            for adapter in discovered:
                spec = adapter.spec
                if spec.name in staged_names:
                    continue
                staged.append((adapter, spec))
                staged_names.add(spec.name)

            for adapter, spec in staged:
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": spec.name,
                            "description": spec.description,
                            "parameters": spec.parameters,
                        },
                    }
                )
                adapters_by_name[spec.name] = adapter

            if not staged:
                client.close()
                _amr._unregister_mcp_client(app_state, client)
            client = None

            _amr.logger.info(
                "Discovered %d MCP tools from server '%s'",
                len(staged),
                name,
            )
        except Exception as exc:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    _amr.logger.debug(
                        "Failed to close unusable MCP client", exc_info=True
                    )
                else:
                    _amr._unregister_mcp_client(app_state, client)
            _amr.logger.warning(
                "Failed to discover MCP tools from '%s': %s",
                name,
                exc,
            )

    if openai_tools:
        clients_lock = _amr._mcp_state_lock(app_state, "_mcp_clients_lock")
        with clients_lock:
            if not getattr(app_state, "_managed_runtime_stopping", False):
                app_state._mcp_tools_cache = (openai_tools, adapters_by_name)
                return openai_tools, adapters_by_name
    return [], {}


__all__ = ["_stream_managed_agent", "_get_mcp_tools_locked"]

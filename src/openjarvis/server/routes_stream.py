"""Server-sent-event streaming for /v1/chat/completions: plain token
streams, streams with tool calls, and agent streams.

Split out of ``routes.py``; its helpers are looked up on that module at
call time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

import openjarvis.server.routes as _routes
from openjarvis.server.models import ChatCompletionRequest


async def _handle_stream(
    engine,
    model: str,
    req: ChatCompletionRequest,
    complexity_info=None,
    *,
    trace_store=None,
    app_config=None,
    bus=None,
    memory_service=None,
):
    """Stream response using SSE format.

    This no-agent fallback streams straight from the engine, bypassing the
    ``TraceCollector``. When *trace_store* is set we accumulate the streamed
    tokens and record a minimal ``Trace`` once the stream completes
    successfully.
    """
    import time

    from openjarvis.server.cloud_router import stream_cloud, stream_local

    messages = _routes._to_messages(req.messages)
    messages = _routes._ensure_identity_prompt(messages, app_config)
    chunk_id = f"chatcmpl-{_routes.uuid.uuid4().hex[:12]}"

    # Last user message — recorded as the trace query.
    query_text = ""
    for _m in reversed(req.messages):
        if _m.role == "user" and _m.content:
            query_text = _m.content
            break

    # Route directly to the right backend — bypasses engine routing entirely
    # so broken MultiEngine state can never misdirect requests.
    use_cloud = _routes._uses_direct_cloud_router(engine, model)
    telemetry_engine = (
        "cloud"
        if use_cloud
        else (_routes._engine_key_for_model(engine, model) or "ollama")
    )

    async def generate():
        started_at = time.time()
        full_content = ""
        # Start with the configured route, then correct it below if the
        # MultiEngine safety path deliberately bypasses that route.
        actual_telemetry_engine = telemetry_engine
        # Send role chunk first
        first_chunk = _routes.ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                _routes.StreamChoice(
                    delta=_routes.DeltaMessage(role="assistant"),
                )
            ],
        )
        yield f"data: {first_chunk.model_dump_json()}\n\n"

        try:
            # Cloud models → direct cloud API (reads keys from disk).
            # Local models → engine.stream() first so mock engines work in
            # tests.  Fall back to stream_local() only when the engine would
            # mis-route the request to a cloud backend (MultiEngine routing
            # confusion), which is detected by checking the routed engine's
            # is_cloud attribute.
            if use_cloud:
                token_iter = stream_cloud(
                    model, messages, req.temperature, req.max_tokens
                )
            else:
                # Use engine.stream() by default (preserves mock-engine
                # compatibility in tests).  Only fall back to stream_local()
                # when a real MultiEngine would mis-route the local model to a
                # cloud backend — detected via isinstance so mocks are not
                # accidentally matched.
                _use_local_fallback = False
                try:
                    from openjarvis.engine.multi import MultiEngine

                    _inner = getattr(engine, "_inner", engine)
                    if isinstance(_inner, MultiEngine):
                        _routed = _inner._engine_for(model)
                        if _routed is not None and getattr(_routed, "is_cloud", False):
                            _use_local_fallback = True
                except Exception:
                    pass
                if _use_local_fallback:
                    actual_telemetry_engine = "ollama"
                    token_iter = stream_local(
                        model, messages, req.temperature, req.max_tokens
                    )
                else:
                    token_iter = engine.stream(
                        messages,
                        model=model,
                        temperature=req.temperature,
                        max_tokens=req.max_tokens,
                    )
            async for token in token_iter:
                full_content += token
                chunk = _routes.ChatCompletionChunk(
                    id=chunk_id,
                    model=model,
                    choices=[
                        _routes.StreamChoice(
                            delta=_routes.DeltaMessage(content=token),
                        )
                    ],
                )
                yield f"data: {chunk.model_dump_json()}\n\n"
        except Exception as exc:
            # Surface errors as a content chunk so the frontend can
            # display them instead of silently failing.
            import logging

            logging.getLogger("openjarvis.server").error(
                "Stream error: %s",
                exc,
                exc_info=True,
            )
            error_chunk = _routes.ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[
                    _routes.StreamChoice(
                        delta=_routes.DeltaMessage(
                            content=f"\n\nError during generation: {exc}",
                        ),
                        finish_reason="stop",
                    )
                ],
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Record a trace for the completed stream (best-effort; never breaks
        # the response). Mirrors the agent path so streamed chats also
        # populate traces.db.
        if trace_store is not None and full_content:
            from openjarvis.traces.collector import record_response_trace

            record_response_trace(
                trace_store,
                query=query_text,
                result=full_content,
                model=model,
                engine=actual_telemetry_engine,
                started_at=started_at,
                ended_at=time.time(),
            )

        if full_content:
            _routes._record_completed_exchange(
                memory_service,
                query_text,
                full_content,
                bus=bus,
                source="server.chat.stream",
            )

        # Send finish chunk with usage data if available
        import json as _json

        finish_data = _routes.ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                _routes.StreamChoice(
                    delta=_routes.DeltaMessage(),
                    finish_reason="stop",
                )
            ],
        )
        finish_dict = _json.loads(finish_data.model_dump_json())

        # Tag the finish chunk with the backend that actually yielded tokens,
        # including the explicit local fallback around a stale MultiEngine map.
        finish_dict.setdefault("telemetry", {})
        finish_dict["telemetry"]["engine"] = actual_telemetry_engine

        if complexity_info is not None:
            finish_dict["complexity"] = complexity_info.model_dump()

        yield f"data: {_json.dumps(finish_dict)}\n\n"
        yield "data: [DONE]\n\n"

    return _routes.StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _handle_stream_tools(
    engine,
    model: str,
    req: ChatCompletionRequest,
    complexity_info=None,
    *,
    app_config=None,
    bus=None,
    memory_service=None,
):
    """Stream a raw OpenAI-compat function-calling response via SSE.

    Used when the client passes `tools` together with `stream:true`.  Sources
    tool_calls from ``engine.stream_full()`` (which forwards the tools to the
    backend and parses tool_calls out of the streamed response) and emits them
    as SSE deltas, bypassing the agent entirely.  This is the streaming mirror
    of the non-streaming ``_handle_direct`` tool path.

    Engines without a tool-aware ``stream_full`` override fall back to the
    base-class default (content tokens + a ``stop`` finish_reason, no
    tool_calls) — identical to the prior plain-stream behaviour, so this never
    regresses non-tool-capable engines.
    """
    messages = _routes._to_messages(req.messages)
    messages = _routes._ensure_identity_prompt(messages, app_config)
    chunk_id = f"chatcmpl-{_routes.uuid.uuid4().hex[:12]}"
    use_cloud = _routes._uses_direct_cloud_router(engine, model)
    telemetry_engine = (
        "cloud"
        if use_cloud
        else (_routes._engine_key_for_model(engine, model) or "ollama")
    )
    query_text = ""
    for _m in reversed(req.messages):
        if _m.role == "user" and _m.content:
            query_text = _m.content
            break

    async def generate():
        full_content = ""
        # Send the role chunk first (OpenAI convention).
        first_chunk = _routes.ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                _routes.StreamChoice(delta=_routes.DeltaMessage(role="assistant"))
            ],
        )
        yield f"data: {first_chunk.model_dump_json()}\n\n"

        finish_reason = "stop"
        try:
            async for sc in engine.stream_full(
                messages,
                model=model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                tools=req.tools,
            ):
                if sc.content:
                    full_content += sc.content
                    content_chunk = _routes.ChatCompletionChunk(
                        id=chunk_id,
                        model=model,
                        choices=[
                            _routes.StreamChoice(
                                delta=_routes.DeltaMessage(content=sc.content)
                            )
                        ],
                    )
                    yield f"data: {content_chunk.model_dump_json()}\n\n"
                if sc.tool_calls:
                    tc_chunk = _routes.ChatCompletionChunk(
                        id=chunk_id,
                        model=model,
                        choices=[
                            _routes.StreamChoice(
                                delta=_routes.DeltaMessage(tool_calls=sc.tool_calls)
                            )
                        ],
                    )
                    yield f"data: {tc_chunk.model_dump_json()}\n\n"
                if sc.finish_reason:
                    finish_reason = sc.finish_reason
        except Exception as exc:
            import logging

            logging.getLogger("openjarvis.server").error(
                "Tool stream error: %s",
                exc,
                exc_info=True,
            )
            error_chunk = _routes.ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[
                    _routes.StreamChoice(
                        delta=_routes.DeltaMessage(
                            content=f"\n\nError during generation: {exc}",
                        ),
                        finish_reason="stop",
                    )
                ],
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
            return

        import json as _json

        finish_data = _routes.ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                _routes.StreamChoice(
                    delta=_routes.DeltaMessage(), finish_reason=finish_reason
                )
            ],
        )
        finish_dict = _json.loads(finish_data.model_dump_json())
        # Tag the finish chunk with the engine label, matching _handle_stream
        # so UI/telemetry consumers see the same field on the tools path.
        finish_dict.setdefault("telemetry", {})
        finish_dict["telemetry"]["engine"] = telemetry_engine
        if complexity_info is not None:
            finish_dict["complexity"] = complexity_info.model_dump()
        yield f"data: {_json.dumps(finish_dict)}\n\n"
        if full_content:
            _routes._record_completed_exchange(
                memory_service,
                query_text,
                full_content,
                bus=bus,
                source="server.chat.stream",
            )
        yield "data: [DONE]\n\n"

    return _routes.StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _handle_agent_stream(
    agent,
    model: str,
    req: ChatCompletionRequest,
    complexity_info=None,
    *,
    trace_store=None,
    bus=None,
    memory_service=None,
):
    """Run the configured agent and return its result as an SSE response.

    Agents own the tool-execution loop, which is synchronous today.  Run that
    loop in a worker thread and stream its final answer once complete.  This
    keeps ``stream:true`` clients (including the desktop UI) on the same agent
    and configured toolkit as non-streaming requests instead of bypassing the
    agent and silently dropping server-side tools.

    Requests that explicitly supply OpenAI ``tools`` continue to use
    ``_handle_stream_tools`` so their raw tool-call deltas are preserved.
    """
    chunk_id = f"chatcmpl-{_routes.uuid.uuid4().hex[:12]}"
    query_text = ""
    for message in reversed(req.messages):
        if message.role == "user" and message.content:
            query_text = message.content
            break

    async def generate():
        first_chunk = _routes.ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                _routes.StreamChoice(delta=_routes.DeltaMessage(role="assistant"))
            ],
        )
        yield f"data: {first_chunk.model_dump_json()}\n\n"

        # The answer as it is written (agents/_stubs.stream_tokens): before,
        # the whole reply arrived at once when the agent had finished.
        loop = _routes.asyncio.get_running_loop()
        live: _routes.asyncio.Queue = _routes.asyncio.Queue()
        streamed = [False]

        def sink(text: str) -> None:
            loop.call_soon_threadsafe(live.put_nowait, text)

        def piece(text: str) -> str:
            chunk = _routes.ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[
                    _routes.StreamChoice(delta=_routes.DeltaMessage(content=text))
                ],
            )
            return f"data: {chunk.model_dump_json()}\n\n"

        task = _routes.asyncio.ensure_future(
            _routes.asyncio.to_thread(
                _routes._handle_agent,
                agent,
                model,
                req,
                complexity_info,
                trace_store=trace_store,
                bus=bus,
                sink=sink,
            )
        )
        try:
            while not task.done() or not live.empty():
                try:
                    text = await _routes.asyncio.wait_for(live.get(), timeout=0.25)
                except _routes.asyncio.TimeoutError:
                    continue
                if text:
                    streamed[0] = True
                    yield piece(text)
            response = task.result()
        except Exception as exc:
            _routes.logging.getLogger("openjarvis.server").error(
                "Agent stream error: %s",
                exc,
                exc_info=True,
            )
            error_chunk = _routes.ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[
                    _routes.StreamChoice(
                        delta=_routes.DeltaMessage(
                            content=f"Sorry, an error occurred: {exc}",
                        ),
                        finish_reason="stop",
                    )
                ],
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
            return

        content = _routes._response_content(response)
        if content and not streamed[0]:
            yield piece(content)

        import json as _json

        finish_chunk = _routes.ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                _routes.StreamChoice(
                    delta=_routes.DeltaMessage(), finish_reason="stop"
                ),
            ],
        )
        finish_data = _json.loads(finish_chunk.model_dump_json())
        finish_data["usage"] = response.usage.model_dump()
        if complexity_info is not None:
            finish_data["complexity"] = complexity_info.model_dump()
        yield f"data: {_json.dumps(finish_data)}\n\n"

        _routes._record_completed_exchange(
            memory_service,
            query_text,
            content,
            bus=bus,
            source="server.chat.stream",
        )
        yield "data: [DONE]\n\n"

    return _routes.StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


__all__ = ["_handle_stream", "_handle_stream_tools", "_handle_agent_stream"]

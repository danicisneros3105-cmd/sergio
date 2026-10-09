"""The streaming chat WebSocket (``/v1/chat/stream``) and the helpers that
bridge a synchronous token stream into it.

Split out of ``api_routes.py``, which owns the router; its names are looked
up on that module, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket

import openjarvis.server.api_routes as _api


async def _next_sync_stream(iterator: Any) -> Any:
    """Fetch one sync-stream item without blocking or racing cancellation."""
    next_task = _api.asyncio.create_task(
        _api.asyncio.to_thread(next, iterator, _api._SYNC_STREAM_END)
    )
    try:
        return await _api.asyncio.shield(next_task)
    except _api.asyncio.CancelledError:
        # ``to_thread`` cannot stop a running ``next()``. Wait for it before
        # allowing the iterator to be closed so cancellation cannot race a
        # generator that is still executing in the worker thread.
        try:
            await next_task
        except Exception:
            pass
        raise


async def _iterate_sync_stream(iterator: Any):
    """Adapt a blocking iterator to an async generator, closing it safely."""
    try:
        while True:
            item = await _api._next_sync_stream(iterator)
            if item is _api._SYNC_STREAM_END:
                return
            yield item
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            try:
                await _api.asyncio.to_thread(close)
            except Exception as exc:
                _api.logger.warning(
                    "Failed to close synchronous engine stream: %s", exc
                )


def _record_ws_trace(
    trace_store,
    *,
    query: str,
    result: str,
    model: str,
    started_at: float,
    ended_at: float,
) -> None:
    """Record a trace for a completed WebSocket chat (best-effort)."""
    if trace_store is None or not result:
        return
    from openjarvis.traces.collector import record_response_trace

    record_response_trace(
        trace_store,
        query=query,
        result=result,
        model=model,
        started_at=started_at,
        ended_at=ended_at,
    )


@_api.websocket_router.websocket("/v1/chat/stream")
async def websocket_chat_stream(websocket: WebSocket):
    """Stream chat responses over a WebSocket connection.

    Accepts JSON messages of the form::

        {"message": "...", "model": "...", "agent": "..."}

    Sends back JSON chunks::

        {"type": "chunk", "content": "..."}   -- per-token streaming
        {"type": "done",  "content": "..."}   -- final assembled response
        {"type": "error", "detail": "..."}    -- on failure
    """
    from openjarvis.server.auth_middleware import authenticate_websocket

    expected_key = getattr(websocket.app.state, "api_key", "")
    authorized, subprotocol = authenticate_websocket(websocket, expected_key)
    if not authorized:
        # Closing before accept rejects the HTTP upgrade request.
        await websocket.close(code=1008)
        return
    await websocket.accept(subprotocol=subprotocol)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = _api.json.loads(raw)
            except (_api.json.JSONDecodeError, ValueError):
                await websocket.send_json(
                    {"type": "error", "detail": "Invalid JSON"},
                )
                continue

            message = data.get("message")
            if not message:
                await websocket.send_json(
                    {"type": "error", "detail": "Missing 'message' field"},
                )
                continue

            model = data.get("model") or getattr(
                websocket.app.state,
                "model",
                "default",
            )
            engine = getattr(websocket.app.state, "engine", None)
            if engine is None:
                await websocket.send_json(
                    {"type": "error", "detail": "No engine configured"},
                )
                continue

            messages = [{"role": "user", "content": message}]

            # This WS path streams straight from the engine (no agent /
            # TraceCollector), so record the interaction directly once it
            # finishes — otherwise WebSocket chats never reach traces.db.
            import time as _time

            trace_store = getattr(websocket.app.state, "trace_store", None)
            _ws_started_at = _time.time()

            try:
                # Prefer streaming if the engine supports it
                stream_fn = getattr(engine, "stream", None)
                if stream_fn is not None and (
                    _api.inspect.isasyncgenfunction(stream_fn) or callable(stream_fn)
                ):
                    full_content = ""
                    try:
                        gen = stream_fn(messages, model=model)
                        # Handle both async and sync generators
                        if _api.inspect.isasyncgen(gen):
                            async for token in gen:
                                full_content += token
                                await websocket.send_json(
                                    {"type": "chunk", "content": token},
                                )
                        else:
                            # Each ``next()`` can perform a blocking upstream
                            # read, so offload iteration one item at a time.
                            async for token in _api._iterate_sync_stream(iter(gen)):
                                full_content += token
                                await websocket.send_json(
                                    {"type": "chunk", "content": token},
                                )
                    except TypeError:
                        # stream() didn't return an iterable; fall back to
                        # generate(). It makes a blocking upstream call, so run
                        # it in a worker thread to keep the event loop free.
                        result = await _api.asyncio.to_thread(
                            engine.generate, messages, model=model
                        )
                        content = (
                            result.get("content", "")
                            if isinstance(
                                result,
                                dict,
                            )
                            else str(result)
                        )
                        full_content = content
                        await websocket.send_json(
                            {"type": "chunk", "content": content},
                        )
                    await websocket.send_json(
                        {"type": "done", "content": full_content},
                    )
                    _api._record_ws_trace(
                        trace_store,
                        query=message,
                        result=full_content,
                        model=model,
                        started_at=_ws_started_at,
                        ended_at=_time.time(),
                    )
                else:
                    # No stream method — single-shot generate. Blocking upstream
                    # call, so run in a worker thread to keep the event loop free.
                    result = await _api.asyncio.to_thread(
                        engine.generate, messages, model=model
                    )
                    content = (
                        result.get("content", "")
                        if isinstance(
                            result,
                            dict,
                        )
                        else str(result)
                    )
                    await websocket.send_json(
                        {"type": "chunk", "content": content},
                    )
                    await websocket.send_json(
                        {"type": "done", "content": content},
                    )
                    _api._record_ws_trace(
                        trace_store,
                        query=message,
                        result=content,
                        model=model,
                        started_at=_ws_started_at,
                        ended_at=_time.time(),
                    )
            except _api.WebSocketDisconnect:
                raise
            except Exception as exc:
                await websocket.send_json(
                    {"type": "error", "detail": str(exc)},
                )
    except _api.WebSocketDisconnect:
        pass  # Client disconnected — nothing to clean up


__all__ = [
    "_next_sync_stream",
    "_iterate_sync_stream",
    "_record_ws_trace",
    "websocket_chat_stream",
]

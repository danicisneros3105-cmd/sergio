"""``/v1/thinking/stream``: deep thinking over a WebSocket.

Send ``{"question": "…", "strategy": "auto"}`` (strategy optional); every
reasoning step comes back as one JSON message, the same events as
``POST /v1/evolve/think/stream``, ending with ``answer`` or ``error``. Send
another question on the same socket to think again; ``{"stop": true}`` or
closing the socket ends it. Authentication is the same as the chat
WebSocket (server key or a paired phone's token).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from openjarvis.server.evolution_routes import think_events

router = APIRouter(tags=["thinking"])
STRATEGIES = ("auto", "reflection", "tot", "consistency", "causal", "direct")


def _request(message: Any) -> Dict[str, str]:
    if not isinstance(message, dict):
        raise ValueError("envíe un objeto JSON con «question»")
    question = str(message.get("question") or "").strip()
    if not question:
        raise ValueError("question is empty")
    strategy = str(message.get("strategy") or "auto")
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {', '.join(STRATEGIES)}")
    return {"question": question, "strategy": strategy}


@router.websocket("/v1/thinking/stream")
async def thinking_stream(websocket: WebSocket) -> None:
    from openjarvis.server.auth_middleware import authenticate_websocket

    expected_key = getattr(websocket.app.state, "api_key", "")
    authorized, subprotocol = authenticate_websocket(websocket, expected_key)
    if not authorized:
        await websocket.close(code=1008)
        return
    await websocket.accept(subprotocol=subprotocol)
    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("stop"):
                break
            try:
                req = _request(message)
            except ValueError as exc:
                await websocket.send_json({"stage": "error", "message": str(exc)})
                continue
            stream = think_events(req["question"], req["strategy"])
            try:
                async for event in stream:
                    await websocket.send_json(event)
            finally:
                with contextlib.suppress(Exception):
                    await stream.aclose()
    except (WebSocketDisconnect, asyncio.CancelledError):
        return
    with contextlib.suppress(Exception):
        await websocket.close()


__all__ = ["router"]

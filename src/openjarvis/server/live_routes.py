"""``/v1/live``: talk with Sergio in real time, like a phone call.

The Windows companion streams its microphone here; the server keeps the
Gemini Live session (the key never leaves this machine) and runs Sergio's
tools when the model calls them. See :mod:`openjarvis.speech.gemini_live`
for the message protocol.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, WebSocket

from openjarvis.server.auth_middleware import authenticate_websocket

log = logging.getLogger(__name__)
router = APIRouter(tags=["live"])

# One voice at a time. Two windows (the app, a browser tab, the phone) with
# an open conversation would each hear the other's Sergio, answer it and cut
# each other off. The newest conversation takes over; the older one is told
# and does not reconnect by itself.
_active: Any = None


async def _take_over(call: Any) -> None:
    global _active
    old, _active = _active, call
    if old is None or old is call or getattr(old, "closed", True):
        return
    old.closed = True
    try:
        await old.send_json(
            {"type": "replaced", "message": "Otra ventana tomó la conversación."}
        )
        await old.ws.close()
    except Exception:  # noqa: BLE001 — it was already gone
        pass


def _owner() -> str:
    """The owner's name for Sergio's instructions (who he works for)."""
    name = os.environ.get("SERGIO_OWNER_NAME", "").strip()
    if name:
        return name
    try:
        from openjarvis.tools.desktop_tools import _config_owner

        name = _config_owner()
    except Exception:  # noqa: BLE001
        name = ""
    if name:
        return name
    try:
        from openjarvis.faces.routes import _get_book

        people = [p["name"] for p in _get_book().people()]
        return people[0] if len(people) == 1 else ""
    except Exception:  # noqa: BLE001
        return ""


@router.get("/v1/live/status")
async def live_status() -> dict[str, Any]:
    from openjarvis.speech.gemini_live import LIVE_MODELS, api_key

    try:
        from google import genai
        from google.genai import types

        sdk = bool(genai.Client and types.LiveConnectConfig)
    except ImportError:
        sdk = False
    key = bool(api_key())
    return {
        "available": sdk and key,
        "sdk_installed": sdk,
        "key_configured": key,
        "models": list(LIVE_MODELS),
        "reason": "missing_sdk" if not sdk else "missing_key" if not key else "ready",
    }


@router.websocket("/v1/live")
async def live(websocket: WebSocket) -> None:
    from openjarvis.speech.gemini_live import LiveCall, make_executor

    expected = getattr(websocket.app.state, "api_key", "")
    allowed, subprotocol = authenticate_websocket(websocket, expected)
    if not allowed:
        await websocket.close(code=1008)
        return
    await websocket.accept(subprotocol=subprotocol)
    try:
        start = json.loads(await websocket.receive_text())
    except Exception:  # noqa: BLE001 — not our client
        await websocket.close(code=1003)
        return
    if not isinstance(start, dict) or start.get("type") != "start":
        await websocket.send_json({"type": "error", "message": "Falta start."})
        await websocket.close(code=1003)
        return
    from openjarvis import quota

    try:
        quota.check("voz")
    except quota.QuotaExceeded as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=1008)
        return
    execute, tools = make_executor(getattr(websocket.app.state, "agent", None))
    call = LiveCall(
        websocket, start, execute=execute, openai_tools=tools, owner=_owner()
    )
    await _take_over(call)
    try:
        await call.run()
    except Exception as exc:  # noqa: BLE001 — tell the companion, then close
        log.warning("live call ended with an error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)[:500]})
        except Exception:  # noqa: BLE001 — already gone
            pass
    finally:
        global _active
        if _active is call:
            _active = None
        # Counted per spoken exchange in gemini_live (the web keeps the call
        # open all day: connected time says nothing about use).
    try:
        await websocket.close()
    except Exception:  # noqa: BLE001
        pass


__all__ = ["router"]

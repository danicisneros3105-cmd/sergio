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
# each other off. The windows of one computer share a lock in the browser
# (lib/liveSession.ts), so they never fight here. Between devices the newest
# conversation takes over and the older one is told. The desktop companion
# ("client": "desktop") never takes the voice from an open app window: the
# window already hears the owner, and both answering was the «otra ventana
# tomó la conversación» loop. It waits and comes back when the window closes.
_active: Any = None
_active_client = ""


async def _take_over(call: Any, client: str = "web", force: bool = False) -> bool:
    """Make *call* the conversation; False if the desktop must wait instead.

    *force*: the owner called him on purpose (said «Sergio», pressed the
    shortcut). Then the desktop takes the voice even from an app window —
    otherwise «di Sergio para volver aquí» could never work while any window
    (a background tab, the phone) kept the conversation open."""
    global _active, _active_client
    old = _active
    live = old is not None and old is not call and not getattr(old, "closed", True)
    if client == "desktop" and live and _active_client != "desktop" and not force:
        return False
    _active, _active_client = call, client
    if not live:
        return True
    old.closed = True
    try:
        await old.send_json(
            {
                "type": "replaced",
                "by": client,
                "message": "Ahora hablamos en otra ventana o en otro equipo.",
            }
        )
        await old.ws.close()
    except Exception:  # noqa: BLE001 — it was already gone
        pass
    return True


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


def _customer_of(websocket: WebSocket) -> dict:
    """The customer (approved account that is not the owner) on this call."""
    from openjarvis.server.auth_middleware import websocket_session_token

    token = websocket_session_token(websocket)
    if not token:
        return {}
    try:
        from openjarvis.server.accounts_routes import _store

        user = _store().session_user(token) or {}
    except Exception:  # noqa: BLE001
        return {}
    return user if user and user.get("role") != "dueño" else {}


async def _customer_call(websocket: WebSocket, user: dict) -> None:
    """A customer's voice: their own plan and limits, no tools (never the
    owner's PC, files or connectors) and never the owner's voice slot."""
    from openjarvis import quota
    from openjarvis.accounts import provision
    from openjarvis.speech.gemini_live import LiveCall

    marks = [
        (provision.CUSTOMER, provision.CUSTOMER.set(user["id"])),
        (
            provision.CUSTOMER_PLAN,
            provision.CUSTOMER_PLAN.set(_customer_plan(user["id"])),
        ),
    ]
    try:
        try:
            start = json.loads(await websocket.receive_text())
        except Exception:  # noqa: BLE001
            await websocket.close(code=1003)
            return
        if not isinstance(start, dict) or start.get("type") != "start":
            await websocket.close(code=1003)
            return
        try:
            quota.check("voz")
        except quota.QuotaExceeded as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=1008)
            return
        call = LiveCall(websocket, start, execute=None, openai_tools=[], owner="")
        try:
            await call.run()
        except Exception as exc:  # noqa: BLE001
            log.warning("customer live call ended with an error: %s", exc)
    finally:
        for var, mark in reversed(marks):
            var.reset(mark)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


def _customer_plan(uid: str) -> str:
    from openjarvis.server.customer_gate import plan_of

    return plan_of(uid)


@router.websocket("/v1/live")
async def live(websocket: WebSocket) -> None:
    from openjarvis.speech.gemini_live import LiveCall, make_executor

    expected = getattr(websocket.app.state, "api_key", "")
    allowed, subprotocol = authenticate_websocket(websocket, expected)
    if not allowed:
        await websocket.close(code=1008)
        return
    customer = _customer_of(websocket)
    await websocket.accept(subprotocol=subprotocol)
    if customer:
        await _customer_call(websocket, customer)
        return
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
    client = "desktop" if start.get("client") == "desktop" else "web"
    if not await _take_over(call, client, force=start.get("force") is True):
        await websocket.send_json(
            {"type": "busy", "message": "La ventana de Sergio ya le escucha."}
        )
        await websocket.close()
        return
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

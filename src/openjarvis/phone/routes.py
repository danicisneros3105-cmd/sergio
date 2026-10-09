"""HTTP/WebSocket endpoints Twilio talks to, plus the call list for the UI.

* ``POST /phone/incoming`` — someone calls Sergio's number. Only owner
  numbers are connected; everyone else hears a short message and the call
  ends. Requests must carry a valid Twilio signature.
* ``POST /phone/status`` — Twilio reports a finished call (no answer, busy…).
* ``WS /phone/ws`` — the call audio; see :mod:`openjarvis.phone.bot`.
* ``GET /v1/phone/calls`` — recent calls with transcripts (no secrets).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Request, Response, WebSocket

from openjarvis.phone import calls
from openjarvis.phone.numbers import is_owner

logger = logging.getLogger(__name__)

router = APIRouter(tags=["phone"])

_TWIML = "application/xml"


def _config(request_or_ws: Any) -> Any:
    from openjarvis.core.config import load_config

    return getattr(request_or_ws.app.state, "config", None) or load_config()


async def _verified_form(request: Request, config: Any) -> dict[str, str] | None:
    """Form fields if the Twilio signature is valid for our public URL."""
    from openjarvis.server.webhook_routes import _validate_twilio_signature

    form = {k: str(v) for k, v in (await request.form()).items()}
    try:
        _, auth_token, _ = calls.credentials()
        base = calls.public_base(config)
    except calls.PhoneConfigError as exc:
        logger.error("Phone webhook rejected: %s", exc)
        return None
    # Twilio signs the public URL it called, not the local one behind the tunnel.
    url = base + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    signature = request.headers.get("X-Twilio-Signature", "")
    if not _validate_twilio_signature(auth_token, url, form, signature):
        logger.warning("Phone webhook with an invalid Twilio signature")
        return None
    return form


@router.post("/phone/incoming")
async def incoming_call(request: Request) -> Response:
    config = _config(request)
    form = await _verified_form(request, config)
    if form is None:
        return Response("Forbidden", status_code=403)
    caller = form.get("From", "")
    if not config.phone.enabled or not is_owner(caller, config.phone.owner_numbers):
        return Response(
            calls.reject_twiml(
                "Hola. Este número es de un asistente personal y no recibe "
                "llamadas. Gracias."
            ),
            media_type=_TWIML,
        )
    record = calls.new_call(calls.INBOUND_OWNER, to=caller, from_=form.get("To", ""))
    calls.update(record.id, twilio_sid=form.get("CallSid", ""))
    return Response(calls.stream_twiml(config, record), media_type=_TWIML)


@router.post("/phone/status")
async def call_status(request: Request, call_id: str = "") -> Response:
    config = _config(request)
    form = await _verified_form(request, config)
    if form is None:
        return Response("Forbidden", status_code=403)
    record = calls.load(call_id) if call_id.isalnum() else None
    if record is not None and not record.done:
        status = form.get("CallStatus", "")
        if status == "completed":
            # Connected but the media stream never finished on our side.
            if record.status == calls.QUEUED:
                calls.update(record.id, status=calls.FAILED, error="no audio stream")
        else:
            calls.update(
                record.id,
                status=calls.FAILED,
                error=status or "unknown",
                ended_at=time.time(),
            )
    return Response("OK")


@router.websocket("/phone/ws")
async def call_audio(websocket: WebSocket) -> None:
    from openjarvis.phone.bot import run_call

    await websocket.accept()
    try:
        await run_call(websocket, _config(websocket))
    except Exception:  # noqa: BLE001 — keep the server alive
        logger.exception("Phone websocket failed")


@router.get("/v1/phone/calls")
async def list_calls(limit: int = 20) -> dict[str, Any]:
    rows = []
    for record in calls.list_calls(limit=max(1, min(limit, 100))):
        rows.append(
            {
                "id": record.id,
                "kind": record.kind,
                "to": record.to,
                "goal": record.goal,
                "status": record.status,
                "created_at": record.created_at,
                "summary": record.summary,
                "error": record.error,
                "transcript": record.transcript,
            }
        )
    return {"calls": rows}


__all__ = [
    "call_audio",
    "call_status",
    "incoming_call",
    "list_calls",
]

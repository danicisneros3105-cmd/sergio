"""Call records and Twilio call placement.

A call record is a small JSON file in ``~/.openjarvis/extensions/calls/``.
Each record carries a random one-time ``token``; the media-stream websocket
only accepts a connection that presents the matching ``call_id`` + ``token``,
so nobody can open a voice session on the public tunnel by guessing URLs.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

# Call statuses
QUEUED = "queued"
IN_PROGRESS = "in_progress"
COMPLETED = "completed"
FAILED = "failed"

# Call kinds
OUTBOUND = "outbound"  # Sergio calls someone (owner or third party)
INBOUND_OWNER = "inbound_owner"  # the owner calls Sergio


class PhoneConfigError(RuntimeError):
    """Calls are not configured (credentials, number or public URL missing)."""


@dataclass
class CallRecord:
    id: str
    token: str
    kind: str
    to: str
    from_: str = ""
    goal: str = ""
    status: str = QUEUED
    created_at: float = field(default_factory=time.time)
    ended_at: float = 0.0
    twilio_sid: str = ""
    transcript: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    error: str = ""

    @property
    def done(self) -> bool:
        return self.status in (COMPLETED, FAILED)


def calls_dir() -> Path:
    from openjarvis.unified.paths import state_dir

    path = state_dir() / "calls"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(call_id: str) -> Path:
    if not call_id.isalnum():
        raise ValueError("invalid call id")
    return calls_dir() / f"{call_id}.json"


def new_call(kind: str, to: str, *, goal: str = "", from_: str = "") -> CallRecord:
    record = CallRecord(
        id=secrets.token_hex(8),
        token=secrets.token_urlsafe(24),
        kind=kind,
        to=to,
        from_=from_,
        goal=goal,
    )
    save(record)
    return record


def save(record: CallRecord) -> None:
    path = _path(record.id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(record), ensure_ascii=False))
    tmp.replace(path)  # atomic: readers never see half a file


def load(call_id: str) -> CallRecord | None:
    try:
        data = json.loads(_path(call_id).read_text())
    except (OSError, ValueError):
        return None
    return CallRecord(**data)


def list_calls(limit: int = 20) -> list[CallRecord]:
    records = [load(p.stem) for p in calls_dir().glob("*.json")]
    found = [r for r in records if r is not None]
    return sorted(found, key=lambda r: r.created_at, reverse=True)[:limit]


def update(call_id: str, **changes: Any) -> CallRecord | None:
    record = load(call_id)
    if record is None:
        return None
    for key, value in changes.items():
        setattr(record, key, value)
    save(record)
    return record


# ----------------------------------------------------------------------
# Twilio
# ----------------------------------------------------------------------


def credentials(environ: dict | None = None) -> tuple[str, str, str]:
    env = os.environ if environ is None else environ
    sid = env.get("TWILIO_ACCOUNT_SID", "").strip()
    token = env.get("TWILIO_AUTH_TOKEN", "").strip()
    number = env.get("TWILIO_PHONE_NUMBER", "").strip()
    missing = [
        name
        for name, value in (
            ("TWILIO_ACCOUNT_SID", sid),
            ("TWILIO_AUTH_TOKEN", token),
            ("TWILIO_PHONE_NUMBER", number),
        )
        if not value
    ]
    if missing:
        raise PhoneConfigError(
            "Calls need " + ", ".join(missing) + " in ~/.openjarvis/sergio.env"
        )
    return sid, token, number


def public_base(config: Any) -> str:
    url = (getattr(config.phone, "public_url", "") or "").strip().rstrip("/")
    if not url.startswith("https://"):
        raise PhoneConfigError(
            "Set [phone] public_url to the https address of your tunnel "
            "(see `sergio servicio` and the guide in LEEME.md)."
        )
    return url


def stream_twiml(config: Any, record: CallRecord) -> str:
    """TwiML that connects the call audio to Sergio's websocket."""
    ws_url = "wss://" + public_base(config).removeprefix("https://") + "/phone/ws"
    return (
        "<Response><Connect>"
        f"<Stream url={quoteattr(ws_url)}>"
        f'<Parameter name="call_id" value={quoteattr(record.id)}/>'
        f'<Parameter name="token" value={quoteattr(record.token)}/>'
        "</Stream></Connect></Response>"
    )


def reject_twiml(message: str) -> str:
    return (
        f'<Response><Say language="es-MX">{escape(message)}</Say><Hangup/></Response>'
    )


def place_call(config: Any, record: CallRecord, *, client: Any = None) -> CallRecord:
    """Ask Twilio to dial ``record.to``; audio is bridged to /phone/ws."""
    sid, token, number = credentials()
    if client is None:
        from twilio.rest import Client

        client = Client(sid, token)
    base = public_base(config)
    call = client.calls.create(
        to=record.to,
        from_=number,
        twiml=stream_twiml(config, record),
        time_limit=int(config.phone.max_call_minutes) * 60,
        status_callback=f"{base}/phone/status?call_id={record.id}",
        status_callback_event=["completed"],
    )
    return update(record.id, twilio_sid=call.sid, from_=number) or record


__all__ = [
    "CallRecord",
    "calls_dir",
    "COMPLETED",
    "credentials",
    "FAILED",
    "IN_PROGRESS",
    "INBOUND_OWNER",
    "list_calls",
    "load",
    "new_call",
    "OUTBOUND",
    "PhoneConfigError",
    "place_call",
    "public_base",
    "QUEUED",
    "reject_twiml",
    "save",
    "stream_twiml",
    "update",
]

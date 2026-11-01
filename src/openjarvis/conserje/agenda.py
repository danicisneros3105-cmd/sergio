"""«Sergio, ¿qué tengo hoy?»: calendar, reminders and trips of the day, together."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Callable, List, Optional


def _calendar() -> str:
    try:
        from openjarvis.tools.apple_calendar import CalendarUpcomingTool

        out = CalendarUpcomingTool().execute(days_ahead=1)
        return out.content if out.success else ""
    except Exception:  # noqa: BLE001 — no calendar on this computer
        return ""


def _connected_calendar(hub=None, day: Optional[str] = None) -> str:
    """Today's events from a calendar connector he connected (Google Calendar
    and the like): its own «list events» tool, read-only."""
    import json as _json

    try:
        from openjarvis.mcp.hub import get_hub

        hub = hub or get_hub()
        servers = [
            s for s in hub.list()
            if "calendar" in f"{s.get('name', '')} {s.get('directory_id', '')}".lower()
            and s.get("connected") and s.get("enabled", True)
        ]  # fmt: skip
    except Exception:  # noqa: BLE001 — no hub: nothing to read
        return ""
    d = day or date.today().isoformat()
    for s in servers:
        tools = [str(x.get("name", "")) for x in s.get("tools") or []]
        name = next(
            (n for n in tools if "list" in n.lower() and "event" in n.lower()), ""
        )
        if not name:
            continue
        try:
            got = hub.call(
                s["id"], name, {"timeMin": f"{d}T00:00:00", "timeMax": f"{d}T23:59:59"}
            )
        except Exception:  # noqa: BLE001 — ask-permission declined, offline
            continue
        texts = [
            str(c.get("text", ""))
            for c in (got.get("content") if isinstance(got, dict) else None) or []
            if isinstance(c, dict)
        ]
        text = "\n".join(x for x in texts if x).strip()
        if not text and isinstance(got, dict) and got.get("structuredContent"):
            text = _json.dumps(got["structuredContent"], ensure_ascii=False)
        if text:
            return f"({s.get('name')}) " + text[:1500]
    return ""


def _reminders() -> str:
    try:
        from openjarvis.tools.reminders_tool import RemindersTool

        out = RemindersTool().execute(action="list")
        return out.content if out.success else ""
    except Exception:  # noqa: BLE001
        return ""


def _trips(today: str, root: Optional[Path] = None) -> List[str]:
    base = (
        root
        or Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")
        / "viajes"
    )
    out = []
    for f in sorted(Path(base).glob("*.json")) if Path(base).is_dir() else []:
        try:
            t = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if t.get("fecha") == today:
            out.append(f"Hoy empieza su viaje a {t.get('destino')}.")
    return out


def today(
    *,
    calendar: Callable[[], str] = _calendar,
    reminders: Callable[[], str] = _reminders,
    connected: Optional[Callable[[], str]] = None,
    root: Optional[Path] = None,
    day: Optional[str] = None,
) -> str:
    d = day or date.today().isoformat()
    parts = []
    cal = (calendar() or "").strip()
    if cal and "No upcoming" not in cal:
        parts.append("Agenda:\n" + cal[:1500])
    online = (
        connected() if connected is not None else _connected_calendar(day=d)
    ) or ""
    if online.strip():
        parts.append("Calendario conectado:\n" + online.strip())
    rem = (reminders() or "").strip()
    if rem:
        parts.append("Recordatorios:\n" + rem[:800])
    parts += _trips(d, root)
    if not parts:
        return (
            "No veo nada para hoy en su calendario ni en sus recordatorios. Si usa "
            "Google Calendar, conéctelo en Conectores y se lo leo también."
        )
    return "\n\n".join(parts)


__all__ = ["today"]

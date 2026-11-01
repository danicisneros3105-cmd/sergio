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
    root: Optional[Path] = None,
    day: Optional[str] = None,
) -> str:
    d = day or date.today().isoformat()
    parts = []
    cal = (calendar() or "").strip()
    if cal and "No upcoming" not in cal:
        parts.append("Agenda:\n" + cal[:1500])
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

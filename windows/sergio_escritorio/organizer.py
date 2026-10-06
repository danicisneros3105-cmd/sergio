"""Organizer: alarms, digital sticky notes and reminders in one place.

* **Alarms** ring at a time, once or on chosen weekdays ("pon una alarma a
  las 6:30 de lunes a viernes"), with snooze; they survive restarts.
* **Sticky notes** live on the desktop like paper ones: drag them, type in
  them, pick a colour; "nota: comprar leche" makes one.
* **Reminders** are the existing timers (``jarvis.Reminders``).

The logic is plain Python (tested without a screen); the widgets are at the
end.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

DAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
DAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
SNOOZE_MIN = 5
NOTE_COLORS = {
    "amarillo": "#FFE873",
    "rosa": "#FFB3D1",
    "verde": "#B8F2A6",
    "azul": "#A9D8FF",
    "naranja": "#FFC98A",
    "morado": "#D5B8FF",
}


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def _write(path: Path | None, data: Any) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _read(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# -- alarms ---------------------------------------------------------------------
@dataclass
class Alarm:
    id: str
    hour: int
    minute: int
    days: list[int] = field(default_factory=list)  # 0 = lunes; empty: once
    label: str = ""
    enabled: bool = True
    snoozed_until: float = 0.0  # epoch, while snoozed
    last_rang: float = 0.0

    def next_time(self, now: datetime) -> datetime | None:
        """When it rings next (None if switched off)."""
        if not self.enabled:
            return None
        if self.snoozed_until and self.snoozed_until > now.timestamp():
            return datetime.fromtimestamp(self.snoozed_until)
        base = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        for add in range(8):
            when = base + timedelta(days=add)
            if when <= now or when.timestamp() <= self.last_rang + 1:
                continue
            if not self.days or when.weekday() in self.days:
                return when
        return None

    def describe(self) -> str:
        when = f"{self.hour:02d}:{self.minute:02d}"
        if not self.days:
            days = "una vez"
        elif sorted(self.days) == list(range(7)):
            days = "todos los días"
        elif sorted(self.days) == [0, 1, 2, 3, 4]:
            days = "de lunes a viernes"
        elif sorted(self.days) == [5, 6]:
            days = "fines de semana"
        else:
            days = ", ".join(DAY_NAMES[d] for d in sorted(self.days))
        label = f" · {self.label}" if self.label else ""
        return f"{when} ({days}){label}"


def parse_days(text: str) -> list[int]:
    """Weekdays in "de lunes a viernes", "los martes y jueves", "todos los días"."""
    t = _plain(text)
    if re.search(r"\b(todos los dias|cada dia|diario|diaria|a diario)\b", t):
        return list(range(7))
    if re.search(r"\b(entre semana|dias laborables|dias de semana)\b", t):
        return [0, 1, 2, 3, 4]
    if re.search(r"\b(fines? de semana|finde)\b", t):
        return [5, 6]
    m = re.search(r"\bde (\w+) a (\w+)\b", t)
    if m and m.group(1) in DAYS and m.group(2) in DAYS:
        a, b = DAYS.index(m.group(1)), DAYS.index(m.group(2))
        return list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
    return sorted({DAYS.index(d) for d in DAYS if re.search(rf"\b{d}s?\b", t)})


def parse_alarm(text: str, now: datetime) -> tuple[int, int, list[int], str] | None:
    """(hour, minute, days, label) for "alarma a las 6:30 de lunes a viernes
    para ir al gym"; None if it is not an alarm with a time."""
    from sergio_escritorio.jarvis import parse_clock

    t = _plain(text)
    if not re.search(r"\b(alarma|despiertame|despertador)\b", t):
        return None
    when = parse_clock(t, now)
    if when is None:
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
        if not m:
            return None
        when = now.replace(hour=int(m.group(1)) % 24, minute=int(m.group(2)) % 60)
    said = re.search(r"\b(\d{1,2})(?::\d{2})?\b", t)
    if said and int(said.group(1)) < 12 and when.hour >= 12 and not re.search(r"\b(tarde|noche|pm)\b", t):
        when = when.replace(hour=when.hour - 12)  # "alarma a las 7": 7:00, not 19:00
    days = parse_days(t)
    m = re.search(r"\b(?:para|que diga|con el texto)\s+(.+)$", text.strip(), re.I)
    label = m.group(1).strip(" .") if m else ""
    return when.hour, when.minute, days, label


class Alarms:
    """The alarms, saved; ``check`` rings the due ones (call every second)."""

    def __init__(self, path: Path | None, on_ring: Callable[[Alarm], None], clock: Callable[[], float] = time.time):
        self.path, self.on_ring, self.clock = path, on_ring, clock
        self._lock = threading.Lock()
        data = _read(path) or []
        self.items: list[Alarm] = []
        for item in data if isinstance(data, list) else []:
            try:
                self.items.append(Alarm(**item))
            except TypeError:
                continue

    def _save(self) -> None:
        _write(self.path, [asdict(a) for a in self.items])

    def add(self, hour: int, minute: int, days: list[int] | None = None, label: str = "") -> Alarm:
        alarm = Alarm(uuid.uuid4().hex[:8], int(hour) % 24, int(minute) % 60, sorted(set(days or [])), label.strip())
        with self._lock:
            self.items.append(alarm)
            self.items.sort(key=lambda a: (a.hour, a.minute))
            self._save()
        return alarm

    def remove(self, alarm_id: str) -> bool:
        with self._lock:
            before = len(self.items)
            self.items = [a for a in self.items if a.id != alarm_id]
            self._save()
            return len(self.items) < before

    def remove_at(self, hour: int, minute: int | None = None) -> int:
        with self._lock:
            keep = [a for a in self.items if not (a.hour == hour and (minute is None or a.minute == minute))]
            gone = len(self.items) - len(keep)
            self.items = keep
            self._save()
            return gone

    def toggle(self, alarm_id: str, on: bool | None = None) -> None:
        with self._lock:
            for a in self.items:
                if a.id == alarm_id:
                    a.enabled = (not a.enabled) if on is None else on
            self._save()

    def snooze(self, alarm_id: str, minutes: int = SNOOZE_MIN) -> None:
        with self._lock:
            for a in self.items:
                if a.id == alarm_id:
                    a.snoozed_until = self.clock() + minutes * 60
                    a.enabled = True
            self._save()

    def upcoming(self) -> list[tuple[datetime, Alarm]]:
        now = datetime.fromtimestamp(self.clock())
        with self._lock:
            pairs = [(a.next_time(now), a) for a in self.items]
        return sorted([(w, a) for w, a in pairs if w is not None], key=lambda p: p[0])

    def check(self) -> list[Alarm]:
        now_ts = self.clock()
        now = datetime.fromtimestamp(now_ts)
        ringing = []
        with self._lock:
            for a in self.items:
                if not a.enabled:
                    continue
                if a.snoozed_until:
                    if a.snoozed_until <= now_ts:
                        a.snoozed_until = 0.0
                        a.last_rang = now_ts
                        ringing.append(a)
                    continue
                target = now.replace(hour=a.hour, minute=a.minute, second=0, microsecond=0)
                # Rings within its minute (also if the PC woke up a bit late).
                late = (now - target).total_seconds()
                if 0 <= late < 120 and now_ts - a.last_rang > 120 and (not a.days or target.weekday() in a.days):
                    a.last_rang = now_ts
                    if not a.days:
                        a.enabled = False  # a one-off alarm switches itself off
                    ringing.append(a)
            if ringing:
                self._save()
        for a in ringing:
            self.on_ring(a)
        return ringing


# -- sticky notes ------------------------------------------------------------------
@dataclass
class Note:
    id: str
    text: str
    color: str = "amarillo"
    x: int = -1  # -1: placed automatically
    y: int = -1
    w: int = 230
    h: int = 190
    created: float = field(default_factory=time.time)
    on_top: bool = True


class Notes:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        data = _read(path) or []
        self.items: list[Note] = []
        for item in data if isinstance(data, list) else []:
            try:
                self.items.append(Note(**item))
            except TypeError:
                continue

    def save(self) -> None:
        _write(self.path, [asdict(n) for n in self.items])

    def add(self, text: str, color: str = "amarillo") -> Note:
        note = Note(uuid.uuid4().hex[:8], text.strip(), color if color in NOTE_COLORS else "amarillo")
        n = len(self.items)
        note.x, note.y = -1 - n, -1  # the widget places it (cascade)
        self.items.append(note)
        self.save()
        return note

    def get(self, note_id: str) -> Note | None:
        return next((n for n in self.items if n.id == note_id), None)

    def update(self, note_id: str, **changes: Any) -> None:
        note = self.get(note_id)
        if note is not None:
            for key, value in changes.items():
                if hasattr(note, key):
                    setattr(note, key, value)
            self.save()

    def remove(self, note_id: str) -> bool:
        before = len(self.items)
        self.items = [n for n in self.items if n.id != note_id]
        self.save()
        return len(self.items) < before

    def find(self, words: str) -> list[Note]:
        w = _plain(words)
        return [n for n in self.items if w and w in _plain(n.text)]


def parse_note(text: str) -> tuple[str, str] | None:
    """(text, colour) for "nota: comprar leche", "crea una nota rosa que diga X"."""
    t = text.strip()
    plain = _plain(t)
    m = re.match(r"^(?:sergio[, ]+)?(?:nota|apunta|anota|post-?it)\s*[:,]\s*(.+)$", t, re.I)
    if not m:
        m = re.match(
            r"^(?:sergio[, ]+)?(?:crea|pon|haz|hazme|pega|agrega|anade|añade|escribe)(?:me)?\s+(?:una\s+)?"
            r"(?:nota(?:\s+adhesiva)?|post-?it|sticky(?:\s+note)?)(?:\s+\w+)?\s+(?:que\s+diga|con|:|diciendo|para)\s*:?\s*(.+)$",
            t,
            re.I,
        )
    if not m:
        return None
    colour = next((c for c in NOTE_COLORS if re.search(rf"\b(nota|post-?it)\s+{c}", plain)), "amarillo")
    return m.group(1).strip(" ."), colour


__all__ = [
    "Alarm",
    "Alarms",
    "NOTE_COLORS",
    "Note",
    "Notes",
    "parse_alarm",
    "parse_days",
    "parse_note",
]

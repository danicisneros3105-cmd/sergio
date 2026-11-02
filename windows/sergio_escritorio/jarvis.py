"""Gentleman-assistant abilities that run on the laptop itself.

* :func:`system_status` — battery, CPU, memory, disk and uptime (Windows API
  through ctypes, nothing to install) and :func:`status_sentence` to say it.
* :class:`Reminders` — timers and reminders that survive a restart
  ("recuérdame en 10 minutos sacar la ropa", "alarma a las 7 y media").
* Protocols — one phrase runs several actions ("protocolo trabajo").
* :func:`briefing` — the morning report when Sergio first sees you.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import threading
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s:]", " ", text).split())


# -- system status -------------------------------------------------------------
def _windows_probe() -> dict[str, Any]:
    import ctypes
    from ctypes import wintypes

    class PowerStatus(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", wintypes.DWORD),
            ("BatteryFullLifeTime", wintypes.DWORD),
        ]

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    k32 = ctypes.windll.kernel32
    out: dict[str, Any] = {}
    power = PowerStatus()
    if k32.GetSystemPowerStatus(ctypes.byref(power)):
        if power.BatteryLifePercent != 255 and power.BatteryFlag != 128:
            out["battery"] = int(power.BatteryLifePercent)
            out["charging"] = power.ACLineStatus == 1
            if power.BatteryLifeTime not in (0xFFFFFFFF, 0):
                out["battery_minutes"] = int(power.BatteryLifeTime) // 60
        else:
            out["charging"] = True  # a desktop on mains
    memory = MemoryStatus()
    memory.dwLength = ctypes.sizeof(MemoryStatus)
    if k32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        out["memory"] = int(memory.dwMemoryLoad)
        out["memory_total_gb"] = round(memory.ullTotalPhys / 2**30, 1)

    def cpu_times() -> tuple[int, int]:
        idle, kernel, user = (wintypes.FILETIME() for _ in range(3))
        k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))

        def value(ft: Any) -> int:
            return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

        return value(idle), value(kernel) + value(user)

    idle1, total1 = cpu_times()
    time.sleep(0.25)
    idle2, total2 = cpu_times()
    busy = total2 - total1
    if busy > 0:
        out["cpu"] = int(round(100 * (1 - (idle2 - idle1) / busy)))
    k32.GetTickCount64.restype = ctypes.c_ulonglong
    out["uptime_hours"] = round(k32.GetTickCount64() / 3_600_000, 1)
    return out


def system_status(probe: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Battery %, charging, CPU %, memory %, free disk (GB), uptime (h)."""
    data: dict[str, Any] = {}
    try:
        if probe is not None:
            data.update(probe())
        elif sys.platform == "win32":
            data.update(_windows_probe())
    except Exception:  # noqa: BLE001 — report what we have
        pass
    if "disk_free_gb" not in data:
        try:
            usage = shutil.disk_usage("C:\\" if sys.platform == "win32" else "/")
            data["disk_free_gb"] = round(usage.free / 2**30)
            data["disk_used"] = int(round(100 * usage.used / usage.total))
        except OSError:
            pass
    return data


def status_sentence(data: dict[str, Any]) -> str:
    parts = []
    if "battery" in data:
        charge = ", cargando" if data.get("charging") else ""
        left = data.get("battery_minutes")
        rest = ""
        if left and not charge:
            rest = (
                f" (unos {left} minutos)"
                if left < 60
                else f" (unas {left // 60} h {left % 60} min)"
            )
        parts.append(f"batería al {data['battery']}%{charge}{rest}")
    if "cpu" in data:
        parts.append(f"procesador al {data['cpu']}%")
    if "memory" in data:
        parts.append(f"memoria al {data['memory']}%")
    if "disk_free_gb" in data:
        parts.append(f"{data['disk_free_gb']} GB libres en el disco")
    if not parts:
        return "No pude leer el estado del sistema."
    text = ", ".join(parts)
    warn = ""
    if data.get("battery", 100) <= 20 and not data.get("charging"):
        warn = " Le sugiero conectar el cargador."
    elif data.get("memory", 0) >= 90:
        warn = " La memoria está casi llena; convendría cerrar algo."
    return f"Todo en orden: {text}.{warn}" if not warn else f"{text[0].upper()}{text[1:]}.{warn}"


# -- timers and reminders --------------------------------------------------------
_UNITS = {
    "segundo": 1,
    "segundos": 1,
    "minuto": 60,
    "minutos": 60,
    "min": 60,
    "hora": 3600,
    "horas": 3600,
}
_NUMBERS = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "quince": 15,
    "veinte": 20,
    "veinticinco": 25,
    "treinta": 30,
    "cuarenta": 40,
    "cuarenta y cinco": 45,
    "cincuenta": 50,
    "sesenta": 60,
    "noventa": 90,
}
_NUM = r"(\d+(?:[.,]\d+)?|" + "|".join(sorted(_NUMBERS, key=len, reverse=True)) + ")"


def _number(word: str) -> float:
    word = word.strip()
    if word in _NUMBERS:
        return float(_NUMBERS[word])
    return float(word.replace(",", "."))


def parse_duration(text: str) -> int | None:
    """Seconds in "10 minutos", "una hora y media", "media hora", "90 segundos"."""
    t = _plain(text)
    if re.search(r"\bmedia hora\b", t):
        return 1800
    if re.search(r"\b(un )?cuarto de hora\b", t):
        return 900
    total = 0.0
    for amount, unit in re.findall(
        _NUM + r"\s+(segundos?|minutos?|min|horas?)\b", t
    ):
        total += _number(amount) * _UNITS[unit]
        if unit.startswith("hora") and re.search(
            rf"{re.escape(amount)}\s+{unit}\s+y\s+media", t
        ):
            total += 1800
    return int(total) if total > 0 else None


def parse_clock(text: str, now: datetime) -> datetime | None:
    """"a las 7", "a las 7 y media", "a las 19:30", "a las 8 de la noche"."""
    t = _plain(text)
    m = re.search(
        r"\ba las? (\d{1,2})(?::(\d{2}))?(?: y (media|cuarto|\d{1,2}))?"
        r"(?: (de la manana|de la tarde|de la noche|am|pm))?",
        t,
    )
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    extra = m.group(3)
    if extra == "media":
        minute = 30
    elif extra == "cuarto":
        minute = 15
    elif extra:
        minute = int(extra)
    part = m.group(4) or ""
    if part in ("de la tarde", "de la noche", "pm") and hour < 12:
        hour += 12
    if hour > 23 or minute > 59:
        return None
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when <= now:
        if not part and hour < 12 and when + timedelta(hours=12) > now:
            when += timedelta(hours=12)  # "a las 7" said at 15:00 = 19:00
        else:
            when += timedelta(days=1)
    return when


_ORDER = (
    r"(?:pon(?:me|er)?\s+)?(?:(?:un|una|el|la)\s+)?(?:temporizador|alarma|timer)"
)
_TRIGGERS = (
    r"recu[eé]rdame|recordarme|av[ií]same|despi[eé]rtame|por favor|sergio"
)
_TIME_WORDS = (
    r"(?:en|de|dentro de)\s+(?:\d+(?:[.,]\d+)?|[a-zñáéíóú ]+?)\s+"
    r"(?:segundos?|minutos?|min|horas?)(?:\s+y\s+media)?"
    r"|(?:en|de|dentro de)\s+(?:media hora|(?:un )?cuarto de hora)"
    r"|a las? \d{1,2}(?::\d{2})?(?: y (?:media|cuarto|\d{1,2}))?"
    r"(?: de la (?:ma[nñ]ana|tarde|noche)| am| pm)?"
)


def parse_reminder(text: str, now: datetime) -> tuple[datetime, str] | None:
    """(when, what) for "recuérdame en 10 minutos sacar la ropa" & co."""
    t = _plain(text)
    if not re.search(
        r"\b(recuerdame|recordarme|avisame|temporizador|alarma|despiertame|"
        r"timer)\b",
        t,
    ):
        return None
    seconds = parse_duration(t)
    when = now + timedelta(seconds=seconds) if seconds else parse_clock(t, now)
    if when is None:
        return None
    # What to remember: the sentence without the order and the time.
    what = re.sub(r"[¡!¿?.,;:]", " ", text.lower())
    what = re.sub(_TIME_WORDS, " ", what)
    what = re.sub(rf"\b{_ORDER}\b", " ", what)
    what = re.sub(rf"\b(?:{_TRIGGERS})\b", " ", what)
    what = " ".join(what.split())
    what = re.sub(r"^(?:que|de|para|a)\s+", "", what)
    return when, what


@dataclass
class Reminder:
    id: str
    due: float  # epoch seconds
    text: str


class Reminders:
    """Timers and reminders, saved to disk so a restart does not lose them."""

    def __init__(
        self,
        path: Path | None,
        on_due: Callable[[Reminder], None],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = path
        self.on_due = on_due
        self.clock = clock
        self._lock = threading.Lock()
        self.items: list[Reminder] = self._load()
        self._running = False

    def _load(self) -> list[Reminder]:
        if self.path is None or not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [Reminder(**item) for item in data]
        except (OSError, ValueError, TypeError):
            return []

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.write_text(
                json.dumps([asdict(r) for r in self.items], ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def add(self, when: float, text: str) -> Reminder:
        item = Reminder(uuid.uuid4().hex[:8], float(when), text.strip())
        with self._lock:
            self.items.append(item)
            self.items.sort(key=lambda r: r.due)
            self._save()
        return item

    def cancel_all(self) -> int:
        with self._lock:
            count = len(self.items)
            self.items = []
            self._save()
        return count

    def pending(self) -> list[Reminder]:
        with self._lock:
            return list(self.items)

    def check(self) -> list[Reminder]:
        """Fire everything that is due (call it every second or so)."""
        now = self.clock()
        with self._lock:
            due = [r for r in self.items if r.due <= now]
            if due:
                self.items = [r for r in self.items if r.due > now]
                self._save()
        for item in due:
            self.on_due(item)
        return due

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        def loop() -> None:
            while self._running:
                try:
                    self.check()
                except Exception:  # noqa: BLE001 — never kill the timer
                    pass
                time.sleep(1.0)

        threading.Thread(target=loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False


def when_phrase(when: datetime, now: datetime) -> str:
    seconds = int((when - now).total_seconds())
    if seconds < 90:
        return f"en {max(1, seconds)} segundos"
    if seconds < 3600:
        return f"en {round(seconds / 60)} minutos"
    hour = when.hour % 12 or 12
    day = "" if when.date() == now.date() else " mañana"
    minutes = "" if when.minute == 0 else f" y {when.minute}"
    return f"a las {hour}{minutes}{day}"


# -- protocols -------------------------------------------------------------------
# Each protocol: what to say and the actions (control-server format).
PROTOCOLS: dict[str, dict[str, Any]] = {
    "trabajo": {
        "say": "Protocolo trabajo: su correo y su agenda, señor.",
        "actions": [
            {"action": "open", "target": "https://mail.google.com"},
            {"action": "open", "target": "https://calendar.google.com"},
        ],
    },
    "concentracion": {
        "say": "Protocolo concentración: escritorio despejado y música para enfocarse.",
        "actions": [
            {"action": "key", "keys": "win+d"},
            {
                "action": "open",
                "target": "https://www.youtube.com/results?search_query=lofi+focus+music",
            },
        ],
    },
    "musica": {
        "say": "Un poco de música, señor.",
        "actions": [{"action": "open_app", "target": "Spotify"}],
    },
    "fiesta": {
        "say": "Protocolo fiesta activado. Que empiece la música.",
        "actions": [{"action": "open_app", "target": "Spotify"}]
        + [{"action": "key", "keys": "volumeup"}] * 8,
    },
    "descanso": {
        "say": "Protocolo descanso: todo minimizado. Estírese un poco, señor.",
        "actions": [{"action": "key", "keys": "win+d"}],
    },
}
_PROTOCOL_ALIASES = {
    "enfoque": "concentracion",
    "estudio": "concentracion",
    "estudiar": "concentracion",
    "relax": "musica",
    "relajacion": "musica",
    "pausa": "descanso",
    "fiesta en casa": "fiesta",
}


def find_protocol(text: str, protocols: dict[str, Any] | None = None) -> str | None:
    protocols = protocols if protocols is not None else PROTOCOLS
    t = _plain(text)
    m = re.search(r"\b(?:protocolo|modo)\s+(.+)$", t)
    if not m:
        return None
    name = m.group(1).strip()
    name = _PROTOCOL_ALIASES.get(name, name)
    if name in protocols:
        return name
    for key in protocols:
        if name.startswith(key) or key.startswith(name):
            return key
    return None


# -- briefing ----------------------------------------------------------------------
def greeting_for(now: datetime) -> str:
    if now.hour < 12:
        return "Buenos días"
    if now.hour < 19:
        return "Buenas tardes"
    return "Buenas noches"


def briefing(
    now: datetime,
    status: dict[str, Any],
    reminders: list[Reminder],
    name: str = "",
) -> str:
    from sergio_escritorio.quick import spoken_date, spoken_time

    who = f", {name}" if name else ""
    parts = [f"{greeting_for(now)}{who}. {spoken_time(now)} {spoken_date(now)}"]
    if "battery" in status:
        charge = " y cargando" if status.get("charging") else ""
        parts.append(f"La batería está al {status['battery']}%{charge}.")
    today = [
        r
        for r in reminders
        if datetime.fromtimestamp(r.due).date() == now.date() and r.text
    ]
    if today:
        first = today[0]
        when = datetime.fromtimestamp(first.due)
        more = f" y {len(today) - 1} más" if len(today) > 1 else ""
        parts.append(f"Hoy tiene pendiente: {first.text}, {when_phrase(when, now)}{more}.")
    return " ".join(parts)


__all__ = [
    "PROTOCOLS",
    "Reminder",
    "Reminders",
    "briefing",
    "find_protocol",
    "parse_clock",
    "parse_duration",
    "parse_reminder",
    "status_sentence",
    "system_status",
    "when_phrase",
]

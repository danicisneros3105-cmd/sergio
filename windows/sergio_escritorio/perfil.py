"""Your profile: Sergio learns who you are and adapts everything to you.

* **Usage schedule**: every minute you are at the PC adds to a week grid
  (day x quarter hour, slowly forgetting old weeks); it says when you are
  usually free, so practices and lessons land at the right time.
* **Key update**: at least 2.5 times a week (every ``UPDATE_DAYS`` days, at a
  moment you are not busy) Sergio gathers what it knows (gym, health,
  learning, organizer, conversation topics) and the coach rewrites the
  profile: traits, goals, best hours, how to talk to you, gym priorities.
* **Applying it**: the profile tunes the voice (detail, humour), the gym
  (priorities, favourite exercises, difficulty) and the coach's plans.

Everything stays on this PC in ``perfil.json``; only the summary needed for
an update goes to the server.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sergio_escritorio import secure

logger = logging.getLogger(__name__)

UPDATE_DAYS = 2.5  # 7 / 2.5 = 2.8 key updates a week (asked: at least 2.5)
SLOTS = 7 * 96  # quarter hours in a week
DECAY = 0.985  # per day: a week ago counts ~90 %, three months ago ~25 %
DAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def slot_of(when: datetime) -> int:
    return when.weekday() * 96 + when.hour * 4 + when.minute // 15


def slot_label(slot: int) -> str:
    day, rest = divmod(slot, 96)
    return f"{DAY_NAMES[day]} {rest // 4:02d}:{(rest % 4) * 15:02d}"


@dataclass
class Usage:
    """When you are at the computer, learnt over the weeks."""

    grid: list[float] = field(default_factory=lambda: [0.0] * SLOTS)
    last_decay: float = 0.0
    last_seen: float = 0.0

    def record(self, now: float) -> None:
        """One minute of activity (call once a minute while you use the PC)."""
        if self.last_decay == 0.0:
            self.last_decay = now
        days = (now - self.last_decay) / 86400
        if days >= 1:
            k = DECAY**days
            self.grid = [v * k for v in self.grid]
            self.last_decay = now
        self.grid[slot_of(datetime.fromtimestamp(now))] += 1.0
        self.last_seen = now

    def busy_level(self, when: datetime) -> float:
        """0..1: how usually you are here at this time (vs your busiest slot)."""
        top = max(self.grid) or 1.0
        return self.grid[slot_of(when)] / top

    def free_windows(self, minimum: float = 0.35, limit: int = 8) -> list[str]:
        """Your usual times at the PC as readable windows ("lunes 19:00-21:00")."""
        top = max(self.grid) or 0.0
        if top <= 0:
            return []
        on = [v >= minimum * top for v in self.grid]
        windows = []
        i = 0
        while i < SLOTS:
            if on[i]:
                j = i
                while j + 1 < SLOTS and on[j + 1] and (j + 1) % 96:
                    j += 1
                if j - i >= 1:  # at least half an hour
                    weight = sum(self.grid[i : j + 1])
                    end = j + 1
                    end_label = "24:00" if end % 96 == 0 else slot_label(end).split()[1]
                    windows.append((weight, f"{slot_label(i)}-{end_label}"))
                i = j + 1
            else:
                i += 1
        windows.sort(key=lambda w: -w[0])
        return [w for _weight, w in windows[:limit]]

    def next_good_time(
        self, after: float, minutes: int = 20, horizon_days: int = 7
    ) -> float:
        """The next usual-presence slot after *after* (epoch), for a practice."""
        start = datetime.fromtimestamp(after)
        top = max(self.grid) or 0.0
        if top <= 0:
            return after + 3600  # nothing learnt yet: in an hour
        base = start.replace(second=0, microsecond=0)
        base = base.replace(minute=(base.minute // 15) * 15)
        need = max(1, minutes // 15)
        for step in range(1, horizon_days * 96):
            ts = base.timestamp() + step * 900
            s = slot_of(datetime.fromtimestamp(ts))
            if all(self.grid[(s + k) % SLOTS] >= 0.5 * top for k in range(need)):
                return ts
        return after + 86400

    def to_json(self) -> dict[str, Any]:
        return {
            "grid": [round(v, 3) for v in self.grid],
            "last_decay": self.last_decay,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_json(cls, data: Any) -> "Usage":
        if not isinstance(data, dict) or len(data.get("grid") or []) != SLOTS:
            return cls()
        return cls(
            [float(v) for v in data["grid"]],
            float(data.get("last_decay", 0)),
            float(data.get("last_seen", 0)),
        )


class Profile:
    """The profile on disk, its update schedule and how it is applied."""

    def __init__(
        self, path: Path | None, clock: Callable[[], float] = time.time
    ) -> None:
        self.path, self.clock = path, clock
        self._lock = threading.Lock()
        data: dict[str, Any] = {}
        if path is not None and path.exists():
            loaded = secure.read_json(path, {})
            data = loaded if isinstance(loaded, dict) else {}
        self.data: dict[str, Any] = data.get("perfil") or {}
        self.updates: list[float] = [
            float(t) for t in data.get("actualizaciones") or []
        ]
        self.usage = Usage.from_json(data.get("uso"))
        self.topics: list[dict[str, Any]] = list(data.get("temas") or [])[-200:]
        self.facts: list[str] = list(data.get("hechos") or [])[-200:]

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            payload = {
                "perfil": self.data,
                "actualizaciones": self.updates[-60:],
                "uso": self.usage.to_json(),
                "temas": self.topics[-200:],
                "hechos": self.facts[-200:],
            }
            try:
                secure.write_json(self.path, payload)
            except OSError:
                logger.exception("No se pudo guardar el perfil personal")

    # -- what Sergio notices ------------------------------------------------------
    def seen_active(self) -> None:
        self.usage.record(self.clock())

    def note_topic(self, text: str) -> None:
        """A short trace of what you talk about (first words only, no answers)."""
        words = " ".join(text.split()[:12])
        if len(words) >= 8:
            self.topics.append({"t": round(self.clock()), "tema": words})
            del self.topics[:-200]

    def remember(self, fact: str) -> None:
        """Something you told Sergio about yourself ("soy zurdo", "estudio medicina")."""
        fact = fact.strip()
        if fact and fact not in self.facts:
            self.facts.append(fact)
            del self.facts[:-200]
            self.save()

    # -- the key update ---------------------------------------------------------------
    def due(self) -> bool:
        last = self.updates[-1] if self.updates else 0.0
        return self.clock() - last >= UPDATE_DAYS * 86400

    def per_week(self) -> float:
        week = [t for t in self.updates if self.clock() - t <= 7 * 86400]
        return float(len(week))

    def context(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """What the update looks at (a summary, not raw conversations)."""
        recent = [t["tema"] for t in self.topics if self.clock() - t["t"] <= 14 * 86400]
        return {
            "fecha": datetime.fromtimestamp(self.clock()).strftime("%Y-%m-%d %H:%M"),
            "horario_de_uso": self.usage.free_windows(),
            "lo_que_me_contó": self.facts[-40:],
            "temas_recientes": recent[-60:],
            **(extra or {}),
        }

    def update(
        self,
        think: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the key update now (``think`` asks the server's coach)."""
        new = think(self.context(extra), self.data)
        if not isinstance(new, dict) or not new.get("resumen"):
            raise ValueError("Actualización de perfil vacía")
        with self._lock:
            self.data = new
            self.updates.append(self.clock())
        self.save()
        return new

    # -- using it ---------------------------------------------------------------------
    def voice_line(self) -> str:
        """One line for the voice style from the profile (how to talk to you)."""
        com = self.data.get("comunicacion") or {}
        parts = []
        detail = com.get("detalle")
        if detail == "breve":
            parts.append("Answer very briefly.")
        elif detail == "detallado":
            parts.append("The user likes detailed answers.")
        humour = com.get("humor")
        if humour == "poco":
            parts.append("Keep jokes rare.")
        elif humour == "mucho":
            parts.append("The user enjoys your humour: use it freely (still kind).")
        if com.get("nota"):
            parts.append(f"User preference: {com['nota']}.")
        if self.data.get("resumen"):
            parts.append(f"What you know about the user: {self.data['resumen']}")
        return " ".join(parts)

    def gym_prefs(self) -> dict[str, Any]:
        gym = self.data.get("gimnasio") or {}
        try:
            bias = max(-1, min(1, int(gym.get("dificultad") or 0)))
        except (TypeError, ValueError):
            bias = 0
        return {
            "prioridad": [str(s).lower() for s in gym.get("prioridad") or []],
            "preferidos": [str(s).lower() for s in gym.get("preferidos") or []],
            "dificultad": bias,
        }

    def summary(self) -> str:
        """What Sergio knows about you, said aloud."""
        if not self.data:
            return (
                "Aún no tengo su perfil: lo armo con el uso. La primera actualización llega "
                "en cuanto tenga datos, y luego al menos dos veces y media por semana."
            )
        last = (
            datetime.fromtimestamp(self.updates[-1]).strftime("%d/%m")
            if self.updates
            else "—"
        )
        return f"{self.data.get('resumen', '')} Última actualización: {last}."


def idle_seconds() -> float:
    """Seconds since the last keyboard or mouse input (Windows); 0 elsewhere."""
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):  # type: ignore[attr-defined]
            return 0.0
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — not Windows
        return 0.0


__all__ = ["Profile", "UPDATE_DAYS", "Usage", "idle_seconds", "slot_label", "slot_of"]

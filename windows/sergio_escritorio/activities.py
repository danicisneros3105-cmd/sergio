"""Live Activities: what Sergio is doing right now, like on an iPhone.

Every long job (a background task, Blender Pro, Video Pro, a meeting being
recorded, a timer, a flight being followed) registers here with a title, an
icon, a colour and its progress. The notch shows them the way the Dynamic
Island does: one activity rides in the pill, and when a second one runs at
the same time the island splits in two (the «dúo»): a small round bubble
beside the pill, each with its own progress ring. Finished activities show
a check (or a cross) for a moment and merge back.

Thread-safe: workers call ``start``/``update``/``finish`` from any thread;
the notch reads ``snapshot()`` on the Qt thread every frame.
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Callable

LINGER = 4.0  # seconds a finished activity stays to show its check
KINDS = {  # icon -> colour (the island's accents)
    "task": "#0a84ff",
    "screen": "#bf5af2",
    "blender": "#ff9f0a",
    "video": "#ff375f",
    "meeting": "#30d158",
    "timer": "#ffd60a",
    "flight": "#64d2ff",
    "search": "#5e5ce6",
}


@dataclass(frozen=True)
class Activity:
    id: int
    title: str
    kind: str = "task"
    progress: float | None = None  # 0..1, or None = indeterminate (spinner)
    detail: str = ""
    state: str = "running"  # running | done | failed
    started: float = field(default_factory=time.monotonic)
    ended: float = 0.0

    @property
    def colour(self) -> str:
        if self.state == "failed":
            return "#ff453a"
        return KINDS.get(self.kind, KINDS["task"])


class Activities:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._items: dict[int, Activity] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.clock = clock
        self.listeners: list[Callable[[], None]] = []

    def start(self, title: str, kind: str = "task", detail: str = "") -> int:
        with self._lock:
            aid = next(self._ids)
            self._items[aid] = Activity(aid, title[:60], kind, None, detail[:120], started=self.clock())
        self._changed()
        return aid

    def update(self, aid: int, *, progress: float | None = None, detail: str | None = None,
               title: str | None = None) -> None:
        with self._lock:
            item = self._items.get(aid)
            if item is None or item.state != "running":
                return
            changes: dict = {}
            if progress is not None:
                changes["progress"] = max(0.0, min(1.0, float(progress)))
            if detail is not None:
                changes["detail"] = detail[:120]
            if title is not None:
                changes["title"] = title[:60]
            self._items[aid] = replace(item, **changes)
        self._changed()

    def finish(self, aid: int, ok: bool = True, detail: str = "") -> None:
        with self._lock:
            item = self._items.get(aid)
            if item is None:
                return
            self._items[aid] = replace(
                item, state="done" if ok else "failed", progress=1.0 if ok else item.progress,
                detail=(detail or item.detail)[:120], ended=self.clock(),
            )
        self._changed()

    def snapshot(self) -> list[Activity]:
        """A just-finished one first (its check is the news), then the running, oldest first."""
        now = self.clock()
        with self._lock:
            for aid in [a.id for a in self._items.values() if a.state != "running" and now - a.ended > LINGER]:
                del self._items[aid]
            items = list(self._items.values())
        return sorted(items, key=lambda a: (a.state == "running", a.started))

    def running(self) -> list[Activity]:
        return [a for a in self.snapshot() if a.state == "running"]

    def describe(self) -> str:
        """For «¿qué estás haciendo?»."""
        items = self.running()
        if not items:
            return "Ahora mismo no tengo nada en marcha."
        parts = []
        for a in items:
            pct = f" ({round(a.progress * 100)} %)" if a.progress is not None else ""
            parts.append(f"{a.title}{pct}" + (f": {a.detail}" if a.detail else ""))
        head = "Tengo una cosa en marcha: " if len(items) == 1 else f"Tengo {len(items)} cosas en marcha: "
        return head + "; ".join(parts) + "."

    def _changed(self) -> None:
        for listener in list(self.listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001 — a listener never breaks a worker
                continue


class Spring:
    """A damped spring (the iOS feel: quick, with a soft overshoot).

    ``response`` is the period in seconds, ``damping`` the ratio (1 = no
    overshoot, ~0.72 = Apple's bouncy default)."""

    def __init__(self, value: float = 0.0, response: float = 0.42, damping: float = 0.72) -> None:
        self.value = self.target = value
        self.velocity = 0.0
        self.response, self.damping = response, damping

    def step(self, dt: float) -> float:
        import math

        dt = min(dt, 1 / 30)
        omega = 2 * math.pi / self.response
        force = -omega * omega * (self.value - self.target) - 2 * self.damping * omega * self.velocity
        self.velocity += force * dt
        self.value += self.velocity * dt
        if abs(self.value - self.target) < 1e-3 and abs(self.velocity) < 1e-3:
            self.value, self.velocity = self.target, 0.0
        return self.value

    def settled(self) -> bool:
        return self.value == self.target and self.velocity == 0.0


__all__ = ["Activities", "Activity", "KINDS", "Spring"]

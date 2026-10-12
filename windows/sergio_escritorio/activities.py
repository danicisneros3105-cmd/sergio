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
import math
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
            self._items[aid] = Activity(
                aid, title[:60], kind, None, detail[:120], started=self.clock()
            )
        self._changed()
        return aid

    def update(
        self,
        aid: int,
        *,
        progress: float | None = None,
        detail: str | None = None,
        title: str | None = None,
    ) -> None:
        with self._lock:
            item = self._items.get(aid)
            if item is None or item.state != "running":
                return
            changes: dict = {}
            if progress is not None:
                value = float(progress)
                if not math.isfinite(value):
                    raise ValueError("El progreso debe ser finito")
                changes["progress"] = max(0.0, min(1.0, value))
            if detail is not None:
                changes["detail"] = detail[:120]
            if title is not None:
                changes["title"] = title[:60]
            self._items[aid] = replace(item, **changes)
        self._changed()

    def finish(self, aid: int, ok: bool = True, detail: str = "") -> None:
        with self._lock:
            item = self._items.get(aid)
            if item is None or item.state != "running":
                return
            self._items[aid] = replace(
                item,
                state="done" if ok else "failed",
                progress=1.0 if ok else item.progress,
                detail=(detail or item.detail)[:120],
                ended=self.clock(),
            )
        self._changed()

    def snapshot(self) -> list[Activity]:
        """A just-finished one first (its check is the news), then the running, oldest first."""
        now = self.clock()
        with self._lock:
            for aid in [
                a.id
                for a in self._items.values()
                if a.state != "running" and now - a.ended > LINGER
            ]:
                del self._items[aid]
            items = list(self._items.values())
        return sorted(items, key=lambda a: (a.state == "running", a.started))

    def lines(self) -> list[str]:
        """One readable line per running task (the panel's Agent Swarm list)."""
        out = []
        for a in self.running():
            done = f" · {int(round(a.progress * 100))}%" if a.progress is not None else ""
            more = f" — {a.detail}" if a.detail else ""
            out.append(f"{a.title}{done}{more}")
        return out

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
        head = (
            "Tengo una cosa en marcha: "
            if len(items) == 1
            else f"Tengo {len(items)} cosas en marcha: "
        )
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

    def __init__(
        self, value: float = 0.0, response: float = 0.42, damping: float = 0.72
    ) -> None:
        self.value = self.target = value
        self.velocity = 0.0
        self.response, self.damping = response, damping

    def step(self, dt: float) -> float:
        import math

        dt = max(0.0, min(dt, 0.25))
        omega = 2 * math.pi / self.response
        y, v, z = self.value - self.target, self.velocity, self.damping
        if z < 1:
            damped = omega * math.sqrt(1 - z * z)
            decay = math.exp(-z * omega * dt)
            c, s = math.cos(damped * dt), math.sin(damped * dt)
            self.value = self.target + decay * (y*c + (v+z*omega*y)/damped*s)
            self.velocity = decay * (v*c - (z*omega*v+omega*omega*y)/damped*s)
        elif z == 1:
            decay, b = math.exp(-omega * dt), v + omega*y
            self.value = self.target + decay * (y+b*dt)
            self.velocity = decay * (v-omega*b*dt)
        else:
            root = math.sqrt(z*z - 1)
            r1, r2 = -omega*(z-root), -omega*(z+root)
            a = (v-r2*y)/(r1-r2)
            b = y-a
            self.value = self.target + a*math.exp(r1*dt) + b*math.exp(r2*dt)
            self.velocity = r1*a*math.exp(r1*dt) + r2*b*math.exp(r2*dt)
        if abs(self.value - self.target) < 1e-3 and abs(self.velocity) < 1e-3:
            self.value, self.velocity = self.target, 0.0
        return self.value

    def settled(self) -> bool:
        return self.value == self.target and self.velocity == 0.0


class Fold:
    """Duo-open's inner-pane frost mapping, adapted to a timed desktop fold.

    The 20..172 degree mapping and 45 degree visual tilt cap follow
    marcoazeem/duo-open's DuoShader.kt (MIT; see docs/third-party).
    No display capture or Android service is needed for our own 36px pane.
    """

    DURATION = 0.65
    PANEL_ON_HINGE = 20.0
    FLAT_HINGE = 172.0
    MAX_TILT = 45.0

    def __init__(self, opened: bool = False) -> None:
        self.angle = self.target = 180.0 if opened else 0.0
        self._from = self.angle
        self._elapsed: float | None = None

    def open(self, want: bool) -> None:
        target = 180.0 if want else 0.0
        if target != self.target:
            # Starting from wherever it is now, so a quick change of mind
            # reverses smoothly instead of jumping.
            self._from, self.target, self._elapsed = self.angle, target, 0.0

    def settle(self) -> None:
        """Respect reduced motion without restarting an unfinished fold."""
        self.angle = self.target
        self._elapsed = None

    def step(self, dt: float) -> float:
        if not math.isfinite(dt):
            raise ValueError("El intervalo debe ser finito")
        if self._elapsed is None:
            return self.angle
        self._elapsed += max(0.0, dt)
        p = min(self._elapsed / self.DURATION, 1.0)
        ease = p * p * (3 - 2 * p)
        self.angle = self._from + (self.target - self._from) * ease
        if p >= 1.0:
            self.angle, self._elapsed = self.target, None
        return self.angle

    def settled(self) -> bool:
        return self._elapsed is None

    def reach(self) -> float:
        """Where the far edge is, in panel widths from the hinge (-1 .. 1)."""
        import math

        return -math.cos(math.radians(self.angle))

    def facing(self) -> bool:
        """True once the panel's face (not its back) is towards you."""
        return self.angle > 90.0

    def effect(self) -> float:
        """Normalized tilt; frost resolves throughout the visible unfold."""
        return min(1.0, max(0.0, (self.FLAT_HINGE - self.angle)
                            / (self.FLAT_HINGE - self.PANEL_ON_HINGE)))

    def tilt(self) -> float:
        return self.effect() * self.MAX_TILT

    def snap(self, opened: bool) -> None:
        """Accessibility: reach the endpoint without motion or frost."""
        self.angle = self.target = self._from = 180.0 if opened else 0.0
        self._elapsed = None

    def darken(self) -> float:
        return min(1.0, 2.0 * self.effect())


class Vanish:
    """Hiding the notch: it collapses like a black hole, then rises away.

    ``t`` runs 0 (shown) .. 1 (gone). The first ``COLLAPSE`` of it the island
    falls into a small ball (ease-in, faster and faster, as if pulled in);
    the rest the ball rises off the top of the screen. Showing it plays the
    same film backwards."""

    DURATION = 1.15
    COLLAPSE = 0.6  # share of the film spent collapsing

    def __init__(self, hidden: bool = False) -> None:
        self.t = 1.0 if hidden else 0.0
        self.target = self.t

    def hide(self) -> None:
        self.target = 1.0

    def show(self) -> None:
        self.target = 0.0

    def step(self, dt: float) -> float:
        rate = max(0.0, dt) / self.DURATION
        if self.t < self.target:
            self.t = min(self.target, self.t + rate)
        elif self.t > self.target:
            self.t = max(self.target, self.t - rate)
        return self.t

    @property
    def hidden(self) -> bool:
        return self.t >= 1.0

    @property
    def active(self) -> bool:
        """True while it is anything but fully shown."""
        return self.t > 0.0

    def collapse(self) -> float:
        """0 the whole island .. 1 a small ball (cubic ease-in)."""
        k = min(1.0, self.t / self.COLLAPSE)
        return k * k * k

    def rise(self) -> float:
        """0 the ball in place .. 1 gone above the screen (quadratic ease-in)."""
        k = max(0.0, (self.t - self.COLLAPSE) / (1.0 - self.COLLAPSE))
        return min(1.0, k * k)

    def glow(self) -> float:
        """How bright the accretion disc is: it lights up as the island falls
        in, burns brightest around the small ball and fades as it rises."""
        k = min(1.0, max(0.0, (self.collapse() - 0.12) / 0.7))
        return k * k * (3 - 2 * k) * (1.0 - self.rise())


def _ease_out(k: float) -> float:
    k = min(1.0, max(0.0, k))
    return 1 - (1 - k) ** 3


class Pour:
    """Bringing the notch back with the cursor: a drop of liquid.

    The cursor touches the top edge; a black drop seeps out of the edge right
    there, follows the cursor sideways (viscous, a little late) and leans
    toward it; it lets go and falls slowly into the notch's place, where
    invisible walls (the island's shape) hold it like a lake: it splashes,
    spreads to the walls and fills them up, its surface rocking until it is
    still, and then the island appears in it. ``t`` runs 0 .. 1."""

    DURATION = 2.1
    FORM, FALL, SPREAD, FILL = 0.2, 0.5, 0.7, 0.92  # where each part ends
    RADIUS = 8.0

    def __init__(self) -> None:
        self.t = 1.0
        self.x = 0.0
        self.vx = 0.0
        self.land_x = 0.0
        self.basin = (0.0, 0.0, 0.0)  # left, right, bottom

    @property
    def active(self) -> bool:
        return self.t < 1.0

    def start(self, x: float, left: float, right: float, bottom: float) -> None:
        self.t, self.vx = 0.0, 0.0
        self.basin = (left, right, bottom)
        self.x = self.land_x = self._clamp(x)

    def _clamp(self, x: float) -> float:
        left, right, _ = self.basin
        margin = self.RADIUS + 10
        return min(right - margin, max(left + margin, x))

    def phase(self) -> str:
        if self.t < self.FORM:
            return "form"
        if self.t < self.FALL:
            return "fall"
        if self.t < self.SPREAD:
            return "spread"
        if self.t < self.FILL:
            return "fill"
        return "settle" if self.t < 1.0 else "done"

    def step(self, dt: float, cursor_x: float | None = None) -> float:
        dt = max(0.0, min(dt, 0.05))
        self.t = min(1.0, self.t + dt / self.DURATION)
        if self.phase() in ("form", "fall") and cursor_x is not None:
            # A damped spring toward the cursor: liquid, not a pointer.
            stiff = 38.0 if self.phase() == "form" else 16.0
            self.vx += (self._clamp(cursor_x) - self.x) * stiff * dt
            self.vx *= math.exp(-9.0 * dt)
            self.x = self._clamp(self.x + self.vx * dt)
            self.land_x = self.x
        return self.t

    def _k(self, start: float, end: float) -> float:
        return min(1.0, max(0.0, (self.t - start) / (end - start)))

    def pendant(self) -> float:
        """How far the forming drop hangs from the edge (px)."""
        k = self._k(0.0, self.FORM)
        return self.RADIUS * 2.6 * (k * k * (3 - 2 * k))

    def drop(self) -> tuple[float, float, float]:
        """While falling: (centre y, radius, stretch). Slow, gently speeding up."""
        k = self._k(self.FORM, self.FALL)
        _, _, bottom = self.basin
        start, end = self.RADIUS * 1.7, bottom - self.RADIUS * 0.9
        y = start + (end - start) * (k ** 1.6)
        stretch = 0.12 + 0.32 * k  # longer as it speeds up
        return y, self.RADIUS, stretch

    def spread(self) -> float:
        """0 a fresh splash .. 1 the liquid reaches both walls."""
        return _ease_out(self._k(self.FALL, self.SPREAD))

    def level(self) -> float:
        """How full the lake is: 0 a puddle on the floor .. 1 brim full."""
        if self.t < self.SPREAD:
            return 0.0
        k = self._k(self.SPREAD, self.FILL)
        return k * k * (3 - 2 * k)  # even, like water poured into a basin

    def wave(self, x: float) -> float:
        """The surface's height offset at x (px): waves from where it landed,
        dying out as it settles."""
        if self.t < self.FALL:
            return 0.0
        since = (self.t - self.FALL) * self.DURATION
        amp = 3.2 * math.exp(-2.6 * since)
        d = x - self.land_x
        return amp * math.cos(d * 0.11 - since * 9.0) * math.exp(-abs(d) * 0.012)

    def fade(self) -> float:
        """The island's own picture fading in once the lake is still."""
        return self._k(self.FILL, 1.0)

    def splash(self) -> list[tuple[float, float, float]]:
        """Little droplets thrown up at impact: (x, y, radius)."""
        k = self._k(self.FALL, self.FALL + (self.SPREAD - self.FALL) * 0.9)
        if k <= 0.0 or k >= 1.0:
            return []
        _, _, bottom = self.basin
        out = []
        for i, (vx, vy, r) in enumerate(((-34.0, 26.0, 2.2), (27.0, 30.0, 1.8), (-12.0, 36.0, 1.5), (16.0, 22.0, 1.4))):
            tt = k * 0.55
            y = bottom - self.RADIUS * 0.6 - (vy * tt - 60.0 * tt * tt)
            out.append((self.land_x + vx * tt, min(bottom - 1.0, y), r * (1.0 - 0.6 * k) + 0.2 * (i % 2)))
        return out


def lean(cx: float, cy: float, cursor: tuple[float, float] | None, reach: float = 56.0) -> tuple[float, float, float]:
    """A drop leaning toward a nearby cursor, as surface tension would let it:
    (angle in degrees, stretch 0..0.22, shift px)."""
    if cursor is None:
        return 0.0, 0.0, 0.0
    dx, dy = cursor[0] - cx, cursor[1] - cy
    d = math.hypot(dx, dy)
    if d >= reach or d < 1e-6:
        return 0.0, 0.0, 0.0
    near = 1.0 - d / reach
    return math.degrees(math.atan2(dy, dx)), 0.22 * near, min(4.0, 4.0 * near)


__all__ = ["Activities", "Activity", "Fold", "KINDS", "Pour", "Spring", "Vanish", "lean"]

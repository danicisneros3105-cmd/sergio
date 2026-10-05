"""Mouse and keyboard like a person, not like a bot.

A bot jumps the pointer in a straight line at constant speed, clicks in
zero milliseconds and pastes text in one go. Sergio moves the way a hand
does, so the user can follow every step:

* Curved paths (a Bézier with a random bend), minimum-jerk speed (slow
  start, fast middle, gentle stop) and a duration that follows Fitts' law
  (longer for far or small targets); long moves overshoot a little and
  correct, with a faint tremor that fades as the hand arrives.
* Clicks are held for a human 60-120 ms; double clicks have a real gap.
* Text is typed key by key (accents, ñ and emojis included) at a natural,
  uneven rhythm, with short pauses between words.

Pure planning here (testable); ``WindowsHands`` sends the real input.
"""

from __future__ import annotations

import math
import random
import sys
import time
from typing import Callable

HZ = 120  # pointer updates per second
# "rapido" (default): no waiting. The pointer still glides (about a tenth of
# a second, so you see where it goes), clicks are crisp and text appears at
# once. "humano": the slow, human-looking hand (for screen recordings).
FAST = "rapido"
FAST_MOVE = (0.05, 0.16)  # shortest and longest glide, seconds


def fast_seconds(distance: float) -> float:
    return min(FAST_MOVE[1], max(FAST_MOVE[0], 0.04 + distance / 12000))


def _min_jerk(t: float) -> float:
    return t * t * t * (10 - 15 * t + 6 * t * t)


def move_seconds(distance: float, rng: random.Random, width: float = 24.0) -> float:
    """Fitts' law: a + b·log2(D/W + 1), with human variability."""
    base = 0.16 + 0.105 * math.log2(distance / max(width, 4.0) + 1)
    return min(1.2, max(0.09, base * rng.uniform(0.85, 1.15)))


def _bezier(p0, p1, p2, p3, t):  # noqa: ANN001, ANN202
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
    )


def _segment(
    start: tuple[float, float],
    end: tuple[float, float],
    seconds: float,
    rng: random.Random,
    tremor: float,
) -> list[tuple[float, float, float]]:
    (x0, y0), (x1, y1) = start, end
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 1:
        return [(seconds, x1, y1)]
    nx, ny = -dy / dist, dx / dist  # perpendicular
    bend = dist * rng.uniform(0.04, 0.16) * rng.choice((-1, 1))
    c1 = (x0 + dx * 0.3 + nx * bend, y0 + dy * 0.3 + ny * bend)
    c2 = (x0 + dx * 0.7 + nx * bend * 0.6, y0 + dy * 0.7 + ny * bend * 0.6)
    steps = max(2, int(seconds * HZ))
    out = []
    for i in range(1, steps + 1):
        frac = i / steps
        x, y = _bezier((x0, y0), c1, c2, (x1, y1), _min_jerk(frac))
        shake = tremor * (1 - frac)  # steadier as the hand arrives
        if i < steps:
            x += rng.gauss(0, shake)
            y += rng.gauss(0, shake)
        out.append((seconds * frac, x, y))
    return out


def human_path(
    start: tuple[float, float],
    end: tuple[float, float],
    rng: random.Random | None = None,
    width: float = 24.0,
) -> list[tuple[float, int, int]]:
    """[(seconds since start, x, y), ...] ending exactly on *end*."""
    rng = rng or random.Random()
    dist = math.hypot(end[0] - start[0], end[1] - start[1])
    total = move_seconds(dist, rng, width)
    points: list[tuple[float, float, float]] = []
    if dist > 280:
        # Overshoot a little past the target, then a small correction.
        over = rng.uniform(0.015, 0.04)
        ox = end[0] + (end[0] - start[0]) * over + rng.uniform(-3, 3)
        oy = end[1] + (end[1] - start[1]) * over + rng.uniform(-3, 3)
        main = total * 0.86
        points += _segment(start, (ox, oy), main, rng, tremor=0.9)
        fix = _segment(
            (ox, oy), end, total - main + rng.uniform(0.04, 0.08), rng, tremor=0.3
        )
        points += [(main + t, x, y) for t, x, y in fix]
    else:
        points += _segment(start, end, total, rng, tremor=0.6)
    return [(t, round(x), round(y)) for t, x, y in points]


def typing_delays(text: str, rng: random.Random | None = None) -> list[float]:
    """Seconds to wait before each character: an uneven, human rhythm."""
    rng = rng or random.Random()
    fast = len(text) > 400  # long texts: a fast typist
    median = 0.035 if fast else 0.085
    delays = []
    previous = ""
    for ch in text:
        d = median * math.exp(rng.gauss(0, 0.35))  # log-normal around the median
        if previous in " \n":
            d += rng.uniform(0.02, 0.09)  # a beat between words
            if rng.random() < 0.06 and not fast:
                d += rng.uniform(0.15, 0.4)  # thinking of the next word
        if ch in ".,;:!?¡¿":
            d += rng.uniform(0.03, 0.1)
        if ch.isupper():
            d += 0.03  # shift
        delays.append(min(d, 0.9))
        previous = ch
    return delays


class WindowsHands:
    """Real input on Windows (SendInput), following the human plans."""

    def __init__(
        self,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        speed: str = FAST,
    ) -> None:
        self.sleep = sleep
        self.rng = rng or random.Random()
        self.speed = speed
        self.last: tuple[int, int] | None = None  # where we left the pointer

    # -- low level ---------------------------------------------------------
    def position(self) -> tuple[int, int]:
        import ctypes
        from ctypes import wintypes

        point = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def _set(self, x: int, y: int) -> None:
        import ctypes

        ctypes.windll.user32.SetCursorPos(int(x), int(y))

    def _mouse(self, flags: int) -> None:
        import ctypes

        ctypes.windll.user32.mouse_event(flags, 0, 0, 0, 0)

    def _unicode(self, ch: str) -> None:
        """One character, any language (accents, ñ, emojis)."""
        self._send_text(ch)

    def _send_text(self, text: str) -> None:
        """Any text in ONE SendInput call: it appears at once, accents and
        emojis included (no clipboard)."""
        import ctypes
        from ctypes import wintypes

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]

            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        events = []
        for ch in text.replace("\r\n", "\n"):
            if ch == "\n":  # Enter as a real key (new line, send)
                for flags in (0, 0x0002):
                    events.append(KEYBDINPUT(0x0D, 0, flags, 0, None))
                continue
            units = ch.encode("utf-16-le")
            for i in range(0, len(units), 2):
                code = int.from_bytes(units[i : i + 2], "little")
                for flags in (0x0004, 0x0004 | 0x0002):  # KEYEVENTF_UNICODE (+ KEYUP)
                    events.append(KEYBDINPUT(0, code, flags, 0, None))
        for start in range(0, len(events), 400):  # big texts in a few calls
            chunk = events[start : start + 400]
            batch = (INPUT * len(chunk))()
            for slot, ki in zip(batch, chunk):
                slot.type, slot.ki = 1, ki
            ctypes.windll.user32.SendInput(len(chunk), batch, ctypes.sizeof(INPUT))

    # -- what Sergio does ----------------------------------------------------
    def move(self, x: int, y: int, width: float = 24.0) -> None:
        start = self.position()
        if start[0] <= 1 and start[1] <= 1:
            # The user slammed the pointer into the corner: stop at once.
            raise PermissionError("Control detenido por el usuario (esquina).")
        began = time.monotonic()
        if self.speed == FAST:
            dist = math.hypot(x - start[0], y - start[1])
            path = [
                (t, round(px), round(py))
                for t, px, py in _segment(start, (x, y), fast_seconds(dist), self.rng, tremor=0.0)
            ]
        else:
            path = human_path(start, (x, y), self.rng, width)
        for t, px, py in path:
            wait = began + t - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._set(px, py)
        self.last = (x, y)

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        self.move(x, y)
        fast = self.speed == FAST
        self.sleep(0.01 if fast else self.rng.uniform(0.05, 0.13))  # aim, then press
        down, up = (0x0008, 0x0010) if button == "right" else (0x0002, 0x0004)
        for i in range(clicks):
            self._mouse(down)
            self.sleep(0.015 if fast else self.rng.uniform(0.06, 0.12))
            self._mouse(up)
            if i + 1 < clicks:
                self.sleep(0.04 if fast else self.rng.uniform(0.08, 0.13))

    def type_text(self, text: str) -> None:
        if self.speed == FAST:
            self._send_text(text)  # all at once
            return
        for ch, delay in zip(text, typing_delays(text, self.rng)):
            self.sleep(delay)
            self._unicode(ch)

    def user_took_over(self, tolerance: int = 25) -> bool:
        """The real mouse is not where Sergio left it: the user moved it."""
        if self.last is None:
            return False
        x, y = self.position()
        return abs(x - self.last[0]) > tolerance or abs(y - self.last[1]) > tolerance


def default_hands() -> WindowsHands | None:
    return WindowsHands() if sys.platform == "win32" else None


__all__ = [
    "FAST",
    "HZ",
    "WindowsHands",
    "default_hands",
    "fast_seconds",
    "human_path",
    "move_seconds",
    "typing_delays",
]

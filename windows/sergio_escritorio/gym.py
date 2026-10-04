"""Mental gym pop-up: every 28 minutes, one exercise you cannot skip.

A full-screen, always-on-top card (all monitors are covered) with no close
button: Esc and Alt+F4 do nothing, and if another window steals the focus it
comes back on top. It ends by itself when the exercise is done or its time
is up, shows your score, and Sergio tells you how you did. The ten
exercises take turns (``brain.py`` holds their logic).

If you are away from the computer (no mouse or keyboard for a few minutes)
or it is locked, the exercise waits until you are back.
"""

from __future__ import annotations

import json
import logging
import math
import random
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QLineEdit, QWidget

from sergio_escritorio import brain

log = logging.getLogger(__name__)

INTERVAL_MINUTES = 28.0
AWAY_SECONDS = 180.0  # no input for this long: you are not at the computer
INTRO_SECONDS = 5.0
RESULT_SECONDS = 6.0
BG = QColor(0, 0, 0, 215)
CARD = QColor(28, 28, 30)
CARD_LINE = QColor(255, 255, 255, 28)
TEXT = QColor(245, 245, 247)
MUTED = QColor(142, 142, 147)
ACCENT = QColor(10, 132, 255)
GOOD = QColor(48, 209, 88)
BAD = QColor(255, 69, 58)
FONTS = ["Segoe UI Variable Display", "SF Pro Display", "Segoe UI"]


def font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(FONTS)
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


# -- stats and schedule (no Qt) ----------------------------------------------------------
@dataclass
class GymStats:
    """What is remembered between pop-ups (which one is next, levels, scores)."""

    path: Path | None = None
    next_index: int = 0
    nback_level: int = 2
    list_length: int = 5
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "GymStats":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                path,
                int(data.get("next_index", 0)),
                int(data.get("nback_level", 2)),
                int(data.get("list_length", 5)),
                list(data.get("history", []))[-300:],
            )
        except (OSError, ValueError, TypeError):
            return cls(path)

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.write_text(
                json.dumps(
                    {
                        "next_index": self.next_index,
                        "nback_level": self.nback_level,
                        "list_length": self.list_length,
                        "history": self.history[-300:],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def take_next(self) -> brain.Exercise:
        exercise, self.next_index = brain.next_exercise(self.next_index)
        self.save()
        return exercise

    def record(self, session: brain.Session) -> None:
        self.history.append(
            {
                "kind": session.exercise.kind,
                "time": time.time(),
                "correct": session.correct,
                "total": session.total,
                "accuracy": round(session.accuracy, 3),
                "level": session.level,
            }
        )
        self.save()

    def best(self, kind: str) -> float:
        return max(
            (h["accuracy"] for h in self.history if h.get("kind") == kind), default=0.0
        )

    def today(self) -> int:
        start = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        return sum(1 for h in self.history if h.get("time", 0) >= start)


class GymSchedule:
    """Every *interval* minutes of use, it is time for an exercise."""

    def __init__(
        self,
        interval_minutes: float = INTERVAL_MINUTES,
        *,
        away: Callable[[], float] = lambda: 0.0,
        locked: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.interval = interval_minutes * 60
        self.away = away
        self.locked = locked
        self.clock = clock
        self.enabled = True
        self.running = False
        self.due = clock() + self.interval

    def postpone_from_now(self) -> None:
        self.due = self.clock() + self.interval

    def check(self) -> bool:
        """True when an exercise should start now."""
        if not self.enabled or self.running:
            return False
        if self.clock() < self.due:
            return False
        if self.away() > AWAY_SECONDS or self.locked():
            return False  # waits for you to come back
        self.running = True
        return True

    def done(self) -> None:
        self.running = False
        self.postpone_from_now()

    def minutes_left(self) -> int:
        return max(0, math.ceil((self.due - self.clock()) / 60))


def idle_seconds() -> float:
    """Seconds since the last mouse or keyboard input (Windows)."""
    if sys.platform != "win32":
        return 0.0
    import ctypes

    class LastInput(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LastInput()
    info.cbSize = ctypes.sizeof(LastInput)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    ticks = ctypes.windll.kernel32.GetTickCount()
    return max(0.0, ((ticks - info.dwTime) & 0xFFFFFFFF) / 1000.0)


def screen_locked() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    desk = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not desk:
        return True  # the secure desktop (lock screen) is showing
    user32.CloseDesktop(desk)
    return False


def force_front(widget: QWidget) -> None:
    """Back on top and focused, even if another app grabbed the focus."""
    widget.raise_()
    widget.activateWindow()
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = int(widget.winId())
        front = user32.GetForegroundWindow()
        if front == hwnd:
            return
        theirs = user32.GetWindowThreadProcessId(front, None)
        mine = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(theirs, mine, True)
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)  # TOPMOST
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(theirs, mine, False)
    except Exception:  # noqa: BLE001 — best effort
        pass


# -- drawing helpers ------------------------------------------------------------------------
def draw_voxels(
    p: QPainter, cubes: list[tuple[int, int, int]], rect: QRectF, colour: QColor
) -> None:
    """A 3D figure of unit cubes (dimetric view, hidden faces removed)."""
    cubes = list(brain.normalise(cubes))
    solid = set(cubes)
    ax, az = (0.92, 0.30), (-0.62, 0.40)  # screen direction of +x and +z; +y is up

    def project(x: float, y: float, z: float) -> tuple[float, float]:
        return x * ax[0] + z * az[0], x * ax[1] + z * az[1] - y

    corners = [
        project(x + dx, y + dy, z + dz)
        for x, y, z in cubes
        for dx in (0, 1)
        for dy in (0, 1)
        for dz in (0, 1)
    ]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    unit = 0.86 * min(rect.width(), rect.height()) / span
    ox = rect.center().x() - unit * (min(xs) + max(xs)) / 2
    oy = rect.center().y() - unit * (min(ys) + max(ys)) / 2

    def screen(x: float, y: float, z: float) -> QPointF:
        sx, sy = project(x, y, z)
        return QPointF(ox + sx * unit, oy + sy * unit)

    faces = (
        ((0, 1, 0), [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)], 1.18),  # top
        ((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], 0.82),  # right
        ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], 0.62),  # front
    )
    p.setPen(QPen(QColor(20, 20, 24), max(1.0, unit * 0.04)))
    for x, y, z in sorted(cubes, key=lambda c: c[0] * 0.55 + c[1] * 0.6 + c[2] * 0.62):
        for normal, quad, light in faces:
            if (x + normal[0], y + normal[1], z + normal[2]) in solid:
                continue  # hidden behind its neighbour
            shade = QColor(
                min(255, int(colour.red() * light)),
                min(255, int(colour.green() * light)),
                min(255, int(colour.blue() * light)),
            )
            p.setBrush(shade)
            p.drawPolygon(QPolygonF([screen(x + a, y + b, z + c) for a, b, c in quad]))


def shape_path(kind: str, centre: QPointF, r: float, degrees: float) -> QPainterPath:
    path = QPainterPath()
    if kind == "circulo":
        path.addEllipse(centre, r, r)
        return path
    if kind == "cuadrado":
        pts = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        pts = [(x * 0.82, y * 0.82) for x, y in pts]
    elif kind == "triangulo":
        pts = [(math.cos(a), math.sin(a)) for a in (-math.pi / 2, math.pi / 6, 5 * math.pi / 6)]
    elif kind == "rombo":
        pts = [(0, -1), (0.62, 0), (0, 1), (-0.62, 0)]
    else:  # hexagono
        pts = [(math.cos(math.pi / 3 * i), math.sin(math.pi / 3 * i)) for i in range(6)]
    a = math.radians(degrees)
    poly = QPolygonF(
        [
            QPointF(
                centre.x() + r * (x * math.cos(a) - y * math.sin(a)),
                centre.y() + r * (x * math.sin(a) + y * math.cos(a)),
            )
            for x, y in pts
        ]
    )
    path.addPolygon(poly)
    path.closeSubpath()
    return path


SHADE_FILL = {"blanco": QColor(255, 255, 255), "gris": QColor(150, 150, 156), "negro": QColor(28, 28, 30)}


def draw_cell(p: QPainter, cell: brain.Cell, rect: QRectF) -> None:
    spots = {
        1: [(0.5, 0.5)],
        2: [(0.3, 0.5), (0.7, 0.5)],
        3: [(0.5, 0.28), (0.28, 0.7), (0.72, 0.7)],
        4: [(0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)],
    }[cell.count]
    r = rect.width() * (0.2 if cell.count == 1 else 0.14)
    p.setPen(QPen(QColor(28, 28, 30), 2.2))
    p.setBrush(SHADE_FILL[cell.shade])
    for fx, fy in spots:
        centre = QPointF(rect.left() + fx * rect.width(), rect.top() + fy * rect.height())
        p.drawPath(shape_path(cell.shape, centre, r, cell.degrees))


# -- the exercises ---------------------------------------------------------------------------
class Runner:
    """One exercise inside the pop-up (drawing, keys, answers, timing)."""

    uses_text = False
    keys_hint = ""

    def __init__(self, gym: "GymWindow") -> None:
        self.gym = gym
        self.rng = gym.rng
        self.session = gym.session
        self.index = 0
        self.flash: tuple[QColor, float] | None = None
        self.item_started = gym.clock()

    @property
    def per_item(self) -> float:
        ex = self.session.exercise
        return ex.seconds / ex.items

    def begin(self) -> None:
        self.next_item()

    def next_item(self) -> None:
        self.item_started = self.gym.clock()

    def done(self) -> bool:
        return self.index >= self.session.exercise.items

    def answer(self, ok: float) -> None:
        took = self.gym.clock() - self.item_started
        self.session.record(ok, took)
        self.flash = (GOOD if ok >= 1 else (ACCENT if ok > 0 else BAD), self.gym.clock())
        self.index += 1
        if not self.done():
            self.next_item()

    def tick(self, now: float) -> None:
        if not self.done() and now - self.item_started > self.per_item:
            self.answer(0.0)  # too slow: counts as a miss, next one

    def key(self, text: str) -> None:
        pass

    def click(self, pos: QPointF) -> None:
        pass

    def submit(self, text: str) -> None:
        pass

    def paint(self, p: QPainter, area: QRectF) -> None:
        pass

    def progress(self) -> str:
        return f"{min(self.index + 1, self.session.exercise.items)} / {self.session.exercise.items}"


class ChoiceRunner(Runner):
    """Shared buttons row for the multiple-choice exercises."""

    choices: list[tuple[str, str, QColor | None]] = []  # (key, label, colour)

    def button_rects(self, area: QRectF) -> list[QRectF]:
        n = len(self.choices)
        width = min(150.0, (area.width() - 12 * (n - 1)) / n)
        total = n * width + 12 * (n - 1)
        x = area.center().x() - total / 2
        return [QRectF(x + i * (width + 12), area.bottom() - 58, width, 50) for i in range(n)]

    def paint_buttons(self, p: QPainter, area: QRectF) -> None:
        p.setFont(font(12, QFont.Weight.DemiBold))
        for rect, (key, label, colour) in zip(self.button_rects(area), self.choices):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colour or QColor(58, 58, 60))
            p.drawRoundedRect(rect, 14, 14)
            p.setPen(QColor(255, 255, 255) if colour is None or colour.lightness() < 170 else QColor(20, 20, 22))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{key}  {label}" if label else key)

    def click(self, pos: QPointF) -> None:
        for rect, (key, _label, _c) in zip(self.button_rects(self.gym.content_rect()), self.choices):
            if rect.contains(pos):
                self.key(key)


class StroopRunner(ChoiceRunner):
    keys_hint = "Teclas 1 2 3 4 o clic"

    def __init__(self, gym: "GymWindow") -> None:
        super().__init__(gym)
        self.choices = [
            (str(i + 1), name.capitalize(), QColor(hexcode))
            for i, (name, hexcode) in enumerate(brain.STROOP_COLORS)
        ]
        self.item = brain.stroop(self.rng)

    def next_item(self) -> None:
        super().next_item()
        self.item = brain.stroop(self.rng)

    def key(self, text: str) -> None:
        if text in "1234" and text:
            name = brain.STROOP_COLORS[int(text) - 1][0]
            self.answer(1.0 if self.item.check(name) else 0.0)

    def paint(self, p: QPainter, area: QRectF) -> None:
        p.setFont(font(64, QFont.Weight.Black))
        p.setPen(QColor(self.item.ink_hex))
        p.drawText(area.adjusted(0, 0, 0, -80), Qt.AlignmentFlag.AlignCenter, self.item.word)
        self.paint_buttons(p, area)


class MathRunner(Runner):
    uses_text = True
    keys_hint = "Escribe el resultado y pulsa Enter"

    def next_item(self) -> None:
        super().next_item()
        self.item = brain.arithmetic(self.rng, level=self.index)

    def submit(self, text: str) -> None:
        if text.strip():
            self.answer(1.0 if self.item.check(text) else 0.0)

    def paint(self, p: QPainter, area: QRectF) -> None:
        p.setFont(font(54, QFont.Weight.Bold))
        p.setPen(TEXT)
        p.drawText(area.adjusted(0, 0, 0, -90), Qt.AlignmentFlag.AlignCenter, f"{self.item.text} = ?")


class SymmetryRunner(ChoiceRunner):
    keys_hint = "S = simétrico · A = asimétrico"

    def __init__(self, gym: "GymWindow") -> None:
        super().__init__(gym)
        self.choices = [("S", "Simétrico", None), ("A", "Asimétrico", None)]

    def next_item(self) -> None:
        super().next_item()
        self.item = brain.symmetry(self.rng)

    def key(self, text: str) -> None:
        if text.lower() in ("s", "a"):
            self.answer(1.0 if self.item.check(text.lower()) else 0.0)

    def paint(self, p: QPainter, area: QRectF) -> None:
        grid = self.item.grid
        n = len(grid)
        side = min(area.width(), area.height() - 90) * 0.8
        cell = side / n
        left = area.center().x() - side / 2
        top = area.top() + (area.height() - 90 - side) / 2
        for r, row in enumerate(grid):
            for c, filled in enumerate(row):
                rect = QRectF(left + c * cell + 2, top + r * cell + 2, cell - 4, cell - 4)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ACCENT if filled else QColor(44, 44, 46))
                p.drawRoundedRect(rect, 6, 6)
        self.paint_buttons(p, area)


class NBackRunner(Runner):
    keys_hint = "A = misma posición · L = misma letra (que hace N pasos)"
    STEP = 2.5
    SHOW = 1.6

    def __init__(self, gym: "GymWindow") -> None:
        super().__init__(gym)
        self.game = brain.NBack(self.rng, gym.stats.nback_level if gym.stats else 2)
        self.trial: brain.NBackTrial | None = None
        self.trial_at = 0.0
        self.pressed = {"a": False, "l": False}
        self.end_at = 0.0

    def begin(self) -> None:
        self.end_at = self.gym.clock() + self.session.exercise.seconds
        self._new_trial(self.gym.clock())

    def _new_trial(self, now: float) -> None:
        self.trial = self.game.next()
        self.trial_at = now
        self.pressed = {"a": False, "l": False}
        if self.gym.letter_voice is not None:
            self.gym.letter_voice(self.trial.letter)

    def _close_trial(self) -> None:
        if self.trial is None:
            return
        pos_ok, letter_ok = self.game.answer(self.pressed["a"], self.pressed["l"])
        self.session.record((pos_ok + letter_ok) / 2)
        self.flash = (GOOD if pos_ok and letter_ok else BAD, self.gym.clock())

    def tick(self, now: float) -> None:
        if self.done():
            return
        if now - self.trial_at >= self.STEP:
            self._close_trial()
            if now < self.end_at:
                self._new_trial(now)
            else:
                self.trial = None

    def done(self) -> bool:
        return self.trial is None and self.end_at > 0 and self.gym.clock() >= self.end_at

    def key(self, text: str) -> None:
        if text.lower() in self.pressed:
            self.pressed[text.lower()] = True

    def progress(self) -> str:
        return f"N = {self.game.level}"

    def paint(self, p: QPainter, area: QRectF) -> None:
        side = min(area.width(), area.height()) * 0.62
        cell = side / 3
        left = area.center().x() - side / 2
        top = area.top() + (area.height() - side) / 2 - 20
        lit = (
            self.trial is not None and self.gym.clock() - self.trial_at < self.SHOW
        )
        for i in range(9):
            r, c = divmod(i, 3)
            rect = QRectF(left + c * cell + 4, top + r * cell + 4, cell - 8, cell - 8)
            on = lit and self.trial is not None and self.trial.position == i
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ACCENT if on else QColor(44, 44, 46))
            p.drawRoundedRect(rect, 14, 14)
            if on:
                p.setPen(QColor(255, 255, 255))
                p.setFont(font(34, QFont.Weight.Bold))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.trial.letter)
        p.setFont(font(12, QFont.Weight.DemiBold))
        for key, label, x in (("a", "A  Posición", -110), ("l", "L  Letra", 110)):
            rect = QRectF(area.center().x() + x - 90, top + side + 14, 180, 40)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ACCENT if self.pressed.get(key) else QColor(58, 58, 60))
            p.drawRoundedRect(rect, 12, 12)
            p.setPen(QColor(255, 255, 255))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)


class RelationalRunner(ChoiceRunner):
    keys_hint = "V = verdadero · F = falso"

    def __init__(self, gym: "GymWindow") -> None:
        super().__init__(gym)
        self.choices = [("V", "Verdadero", None), ("F", "Falso", None)]

    def next_item(self) -> None:
        super().next_item()
        self.item = brain.relational(self.rng)

    def key(self, text: str) -> None:
        if text.lower() in ("v", "f"):
            self.answer(1.0 if self.item.check(text.lower()) else 0.0)

    def paint(self, p: QPainter, area: QRectF) -> None:
        p.setFont(font(17))
        p.setPen(TEXT)
        y = area.top() + 20
        for line in self.item.premises:
            p.drawText(QRectF(area.left() + 30, y, area.width() - 60, 34), Qt.AlignmentFlag.AlignLeft, line)
            y += 38
        p.setFont(font(21, QFont.Weight.Bold))
        p.setPen(ACCENT)
        p.drawText(QRectF(area.left() + 30, y + 16, area.width() - 60, 40), Qt.AlignmentFlag.AlignLeft, self.item.question)
        self.paint_buttons(p, area)


class RotationRunner(Runner):
    keys_hint = "Teclas 1 2 3 4 o clic en la pieza"

    def next_item(self) -> None:
        super().next_item()
        self.item = brain.rotation(self.rng)

    def option_rects(self, area: QRectF) -> list[QRectF]:
        top = area.top() + area.height() * 0.42
        width = (area.width() - 60) / 4
        return [QRectF(area.left() + 12 + i * (width + 12), top, width, area.height() * 0.55) for i in range(4)]

    def key(self, text: str) -> None:
        if text in ("1", "2", "3", "4"):
            self.answer(1.0 if self.item.check(text) else 0.0)

    def click(self, pos: QPointF) -> None:
        for i, rect in enumerate(self.option_rects(self.gym.content_rect())):
            if rect.contains(pos):
                self.key(str(i + 1))

    def paint(self, p: QPainter, area: QRectF) -> None:
        ref = QRectF(area.center().x() - 120, area.top(), 240, area.height() * 0.38)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(44, 44, 46))
        p.drawRoundedRect(ref, 16, 16)
        draw_voxels(p, self.item.reference, ref.adjusted(10, 10, -10, -10), QColor(255, 159, 10))
        for i, rect in enumerate(self.option_rects(area)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(44, 44, 46))
            p.drawRoundedRect(rect, 16, 16)
            draw_voxels(p, self.item.options[i], rect.adjusted(10, 10, -10, -34), QColor(100, 210, 255))
            p.setPen(TEXT)
            p.setFont(font(13, QFont.Weight.Bold))
            p.drawText(QRectF(rect.left(), rect.bottom() - 32, rect.width(), 26), Qt.AlignmentFlag.AlignCenter, str(i + 1))


class ListRunner(Runner):
    uses_text = True
    keys_hint = "Escribe la lista al revés y pulsa Enter"
    SHOW = 0.9
    GAP = 0.25

    def next_item(self) -> None:
        super().next_item()
        length = self.gym.stats.list_length if self.gym.stats else 5
        self.item = brain.reversed_list(self.rng, length)
        self.shown_until = self.item_started + len(self.item.items) * (self.SHOW + self.GAP)
        self.gym.set_text_enabled(False)

    def tick(self, now: float) -> None:
        if not self.done() and now >= self.shown_until:
            self.gym.set_text_enabled(True)
        super().tick(now)

    def submit(self, text: str) -> None:
        if self.gym.clock() < self.shown_until or not text.strip():
            return
        score = self.item.partial(text)
        stats = self.gym.stats
        if stats is not None:
            stats.list_length = max(4, min(9, stats.list_length + (1 if score == 1 else -1 if score < 0.5 else 0)))
            self.session.level = stats.list_length
        self.answer(score)

    def paint(self, p: QPainter, area: QRectF) -> None:
        now = self.gym.clock()
        if now < self.shown_until:
            step = int((now - self.item_started) / (self.SHOW + self.GAP))
            in_gap = (now - self.item_started) % (self.SHOW + self.GAP) > self.SHOW
            if not in_gap and step < len(self.item.items):
                p.setFont(font(72, QFont.Weight.Bold))
                p.setPen(TEXT)
                p.drawText(area.adjusted(0, 0, 0, -90), Qt.AlignmentFlag.AlignCenter, self.item.items[step].upper())
            p.setFont(font(12))
            p.setPen(MUTED)
            p.drawText(QRectF(area.left(), area.bottom() - 120, area.width(), 24), Qt.AlignmentFlag.AlignCenter,
                       f"Memoriza ({len(self.item.items)} elementos)")
        else:
            p.setFont(font(22, QFont.Weight.DemiBold))
            p.setPen(TEXT)
            p.drawText(area.adjusted(0, 0, 0, -120), Qt.AlignmentFlag.AlignCenter, "Ahora escríbela al revés")


class MatrixRunner(Runner):
    keys_hint = "Teclas 1 a 6 o clic en la pieza"

    def next_item(self) -> None:
        super().next_item()
        self.item = brain.matrix(self.rng)

    def layout(self, area: QRectF) -> tuple[list[QRectF], list[QRectF]]:
        side = min(area.height() * 0.62, area.width() * 0.5)
        cell = side / 3
        left = area.center().x() - side / 2
        grid = [QRectF(left + c * cell + 3, area.top() + r * cell + 3, cell - 6, cell - 6) for r in range(3) for c in range(3)]
        opt = min((area.width() - 70) / 6, area.height() - side - 30)
        x0 = area.center().x() - (6 * opt + 50) / 2
        y0 = area.top() + side + 18
        options = [QRectF(x0 + i * (opt + 10), y0, opt, opt) for i in range(6)]
        return grid, options

    def key(self, text: str) -> None:
        if text in "123456" and text:
            self.answer(1.0 if self.item.check(text) else 0.0)

    def click(self, pos: QPointF) -> None:
        for i, rect in enumerate(self.layout(self.gym.content_rect())[1]):
            if rect.contains(pos):
                self.key(str(i + 1))

    def paint(self, p: QPainter, area: QRectF) -> None:
        grid, options = self.layout(area)
        for i, rect in enumerate(grid):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(242, 242, 247))
            p.drawRoundedRect(rect, 10, 10)
            if i < 8:
                draw_cell(p, self.item.cells[i], rect)
            else:
                p.setPen(QColor(28, 28, 30))
                p.setFont(font(40, QFont.Weight.Bold))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "?")
        for i, rect in enumerate(options):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(242, 242, 247))
            p.drawRoundedRect(rect, 10, 10)
            draw_cell(p, self.item.options[i], rect)
            p.setPen(QColor(28, 28, 30))
            p.setFont(font(10, QFont.Weight.Bold))
            p.drawText(QRectF(rect.left() + 6, rect.top() + 4, 20, 18), Qt.AlignmentFlag.AlignLeft, str(i + 1))


class WordsRunner(Runner):
    uses_text = True
    keys_hint = "Escribe una palabra y pulsa Enter (3 por desafío)"

    def next_item(self) -> None:
        super().next_item()
        self.item = brain.word_challenge(self.rng)
        self.words: list[list[str]] = []  # [word, verdict]

    def submit(self, text: str) -> None:
        word = text.strip()
        if not word or any(brain.plain(w) == brain.plain(word) for w, _ in self.words):
            return
        entry = [word, self.item.judge(word)]
        if entry[1] == "desconocida" and self.gym.validate_word is not None:
            # Not in Sergio's lists: his AI decides, without freezing you.
            entry[1] = "pendiente"
            threading.Thread(
                target=self._validate, args=(entry, self.item.category), daemon=True
            ).start()
        self.words.append(entry)

    def _validate(self, entry: list[str], category: str) -> None:
        try:
            ok = bool(self.gym.validate_word(entry[0], category))
        except Exception:  # noqa: BLE001
            ok = False
        entry[1] = "ok" if ok else "regla"

    def tick(self, now: float) -> None:
        if self.done():
            return
        good = sum(1 for _, v in self.words if v == "ok")
        if good >= self.item.target:
            self.answer(1.0)
        elif now - self.item_started > self.per_item:
            self.answer(min(1.0, good / self.item.target))

    def paint(self, p: QPainter, area: QRectF) -> None:
        p.setFont(font(15))
        p.setPen(MUTED)
        p.drawText(QRectF(area.left(), area.top() + 10, area.width(), 26), Qt.AlignmentFlag.AlignCenter, "Escribe")
        p.setFont(font(26, QFont.Weight.Bold))
        p.setPen(TEXT)
        p.drawText(QRectF(area.left(), area.top() + 40, area.width(), 44), Qt.AlignmentFlag.AlignCenter,
                   self.item.category.upper())
        p.setFont(font(19, QFont.Weight.DemiBold))
        p.setPen(ACCENT)
        p.drawText(QRectF(area.left(), area.top() + 92, area.width(), 34), Qt.AlignmentFlag.AlignCenter,
                   f"que {self.item.rule}")
        x = area.left() + 30
        y = area.top() + 150
        p.setFont(font(12, QFont.Weight.DemiBold))
        colours = {"ok": GOOD, "pendiente": QColor(99, 99, 102)}
        for word, verdict in self.words:
            width = p.fontMetrics().horizontalAdvance(word) + 28
            if x + width > area.right() - 30:
                x, y = area.left() + 30, y + 40
            rect = QRectF(x, y, width, 32)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colours.get(verdict, BAD))
            p.drawRoundedRect(rect, 16, 16)
            p.setPen(QColor(255, 255, 255))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, word)
            x += width + 8


class CoordinationRunner(Runner):
    keys_hint = "D F (izquierda) · J K (derecha) · dos a la vez = juntas"
    LIGHT = 0.55
    GAP = 0.18
    CHORD_WINDOW = 0.3

    def next_item(self) -> None:
        super().next_item()
        length = 4 + self.index
        self.item = brain.coordination(self.rng, length, chords=max(0, self.index - 2))
        self.show_until = self.item_started + 0.6 + len(self.item.steps) * (self.LIGHT + self.GAP)
        self.pressed: list[tuple[str, ...]] = []
        self.lit_keys: dict[str, float] = {}

    def key(self, text: str) -> None:
        k = text.lower()
        now = self.gym.clock()
        if k not in brain.PADS or now < self.show_until or self.done():
            return
        self.lit_keys[k] = now
        # Two keys within a moment are one chord.
        if self.pressed and len(self.pressed[-1]) == 1 and now - self._last_key_at < self.CHORD_WINDOW:
            expected = self.item.steps[len(self.pressed) - 1]
            if len(expected) == 2 and k != self.pressed[-1][0]:
                self.pressed[-1] = tuple(sorted(self.pressed[-1] + (k,)))
                self._last_key_at = now
                self._check()
                return
        self.pressed.append((k,))
        self._last_key_at = now
        self._check()

    _last_key_at = 0.0

    def _check(self) -> None:
        n = len(self.pressed)
        expected = [tuple(sorted(s)) for s in self.item.steps]
        got = [tuple(sorted(s)) for s in self.pressed]
        # a single key while a chord is expected may still become the chord
        if got[n - 1] != expected[n - 1] and not (
            len(expected[n - 1]) == 2 and len(got[n - 1]) == 1 and got[n - 1][0] in expected[n - 1]
        ):
            self.answer(self.item.partial(self.pressed))
            return
        if n == len(expected) and got == expected:
            self.answer(1.0)

    def paint(self, p: QPainter, area: QRectF) -> None:
        now = self.gym.clock()
        lit: set[str] = set()
        if now < self.show_until:
            t = now - self.item_started - 0.6
            if t >= 0:
                step = int(t / (self.LIGHT + self.GAP))
                if step < len(self.item.steps) and t % (self.LIGHT + self.GAP) < self.LIGHT:
                    lit = set(self.item.steps[step])
        else:
            lit = {k for k, at in self.lit_keys.items() if now - at < 0.2}
        width = min(130.0, area.width() / 5)
        gap = 20.0
        total = 4 * width + 3 * gap + 40
        x = area.center().x() - total / 2
        y = area.center().y() - width / 2 - 30
        colours = (QColor(255, 159, 10), QColor(255, 214, 10), QColor(48, 209, 88), QColor(100, 210, 255))
        for i, key in enumerate(brain.PADS):
            rect = QRectF(x + i * (width + gap) + (40 if i >= 2 else 0), y, width, width)
            p.setPen(Qt.PenStyle.NoPen)
            colour = colours[i] if key in lit else QColor(44, 44, 46)
            p.setBrush(colour)
            p.drawRoundedRect(rect, 20, 20)
            p.setPen(QColor(20, 20, 22) if key in lit else TEXT)
            p.setFont(font(26, QFont.Weight.Bold))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, key.upper())
        p.setFont(font(13))
        p.setPen(MUTED)
        status = (
            "Mira la secuencia…"
            if now < self.show_until
            else f"Tu turno: {len(self.pressed)} de {len(self.item.steps)}"
        )
        p.drawText(QRectF(area.left(), y + width + 24, area.width(), 26), Qt.AlignmentFlag.AlignCenter, status)


RUNNERS: dict[str, type[Runner]] = {
    "stroop": StroopRunner,
    "calculo": MathRunner,
    "simetria": SymmetryRunner,
    "nback": NBackRunner,
    "relacional": RelationalRunner,
    "rotacion": RotationRunner,
    "listas": ListRunner,
    "matrices": MatrixRunner,
    "palabras": WordsRunner,
    "coordinacion": CoordinationRunner,
}


class GymWindow(QWidget):
    """The pop-up itself. ``finished`` carries the scored Session."""

    finished = Signal(object)

    def __init__(
        self,
        exercise: brain.Exercise,
        *,
        stats: GymStats | None = None,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        speak: Callable[[str], None] | None = None,
        validate_word: Callable[[str, str], bool] | None = None,
        letter_voice: Callable[[str], None] | None = None,
        unskippable: bool = True,
    ) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        if unskippable:
            flags |= Qt.WindowType.Tool
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.exercise = exercise
        self.stats = stats
        self.rng = rng or random.Random()
        self.clock = clock
        self.speak = speak
        self.validate_word = validate_word
        self.letter_voice = letter_voice
        self.unskippable = unskippable
        self.session = brain.Session(exercise)
        self.phase = "intro"
        self.started_at = clock()
        self.play_started = 0.0
        self.result_at = 0.0
        self._closing = False
        self.runner: Runner = RUNNERS[exercise.kind](self)
        self.entry = QLineEdit(self)
        self.entry.setStyleSheet(
            "QLineEdit { background: #2c2c2e; color: #f5f5f7; border: 1px solid #3a3a3c;"
            " border-radius: 22px; padding: 8px 18px; font-size: 22px; }"
            "QLineEdit:focus { border: 1px solid #0a84ff; }"
        )
        self.entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry.returnPressed.connect(self._submit)
        self.entry.hide()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._guard = QTimer(self)
        self._guard.timeout.connect(lambda: force_front(self))

    # -- geometry -----------------------------------------------------------------------
    def cover_screens(self) -> None:
        area = QRect()
        for screen in QGuiApplication.screens():
            area = area.united(screen.geometry())
        if area.isEmpty():
            area = QRect(0, 0, 1280, 800)
        self.setGeometry(area)

    def card_rect(self) -> QRectF:
        primary = QGuiApplication.primaryScreen()
        geo = primary.geometry() if primary is not None else self.geometry()
        centre = QPointF(geo.center() - self.geometry().topLeft())
        width = min(820.0, geo.width() - 80.0)
        height = min(640.0, geo.height() - 80.0)
        return QRectF(centre.x() - width / 2, centre.y() - height / 2, width, height)

    def content_rect(self) -> QRectF:
        card = self.card_rect()
        return card.adjusted(36, 120, -36, -60)

    # -- life cycle -------------------------------------------------------------------------
    def start(self) -> None:
        self.cover_screens()
        self.show()
        force_front(self)
        self._timer.start(33)
        if self.unskippable:
            self._guard.start(400)
        if self.speak is not None:
            self.speak(f"Hora del gimnasio mental: {self.exercise.title}.")

    def set_text_enabled(self, on: bool) -> None:
        if not self.runner.uses_text:
            return
        if on and self.entry.isHidden():
            self.entry.show()
            self.entry.setFocus()
        elif not on and not self.entry.isHidden():
            self.entry.hide()
            self.entry.clear()

    def _begin_play(self) -> None:
        self.phase = "play"
        self.play_started = self.clock()
        self.runner.begin()
        if self.runner.uses_text:
            card = self.card_rect()
            self.entry.setGeometry(
                int(card.center().x() - 180), int(card.bottom() - 132), 360, 52
            )
            if not isinstance(self.runner, ListRunner):
                self.set_text_enabled(True)
        self.setFocus()

    def _finish(self) -> None:
        self.phase = "result"
        self.result_at = self.clock()
        self.entry.hide()
        if isinstance(self.runner, NBackRunner):
            self.session.level = self.runner.game.level
            if self.stats is not None:
                self.stats.nback_level = self.runner.game.level
        if self.stats is not None:
            self.stats.record(self.session)
        if self.speak is not None:
            self.speak(self.session.verdict())

    def _tick(self) -> None:
        now = self.clock()
        if self.phase == "intro" and now - self.started_at >= INTRO_SECONDS:
            self._begin_play()
        elif self.phase == "play":
            self.runner.tick(now)
            if self.runner.done() or now - self.play_started >= self.exercise.seconds:
                self._finish()
        elif self.phase == "result" and now - self.result_at >= RESULT_SECONDS:
            self._close()
        self.update()

    def _close(self) -> None:
        self._closing = True
        self._timer.stop()
        self._guard.stop()
        self.hide()
        self.finished.emit(self.session)
        self.close()

    # -- input ---------------------------------------------------------------------------------
    def _submit(self) -> None:
        if self.phase == "play":
            text = self.entry.text()
            self.entry.clear()
            self.runner.submit(text)

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            return  # cannot be skipped
        if self.phase == "play" and event.text():
            self.runner.key(event.text())

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if self.phase == "play":
            self.runner.click(event.position())

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        if self._closing or not self.unskippable:
            event.accept()
        else:
            event.ignore()  # Alt+F4 and friends: not until it is done

    # -- drawing ----------------------------------------------------------------------------------
    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), BG)
        card = self.card_rect()
        p.setPen(QPen(CARD_LINE, 1))
        p.setBrush(CARD)
        p.drawRoundedRect(card, 30, 30)
        now = self.clock()
        # header
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.setPen(MUTED)
        p.drawText(QRectF(card.left() + 36, card.top() + 26, 400, 20), Qt.AlignmentFlag.AlignLeft, "GIMNASIO MENTAL")
        room = card.width() - 72 - (230 if self.phase == "play" else 0)
        size = 22.0
        while size > 15:
            p.setFont(font(size, QFont.Weight.Bold))
            if p.fontMetrics().horizontalAdvance(self.exercise.title) <= room:
                break
            size -= 1
        p.setPen(TEXT)
        p.drawText(QRectF(card.left() + 36, card.top() + 48, room, 36), Qt.AlignmentFlag.AlignLeft, self.exercise.title)
        if self.phase == "intro":
            self._paint_intro(p, card, now)
        elif self.phase == "play":
            self._paint_play(p, card, now)
        else:
            self._paint_result(p, card)
        p.end()

    def _paint_intro(self, p: QPainter, card: QRectF, now: float) -> None:
        area = card.adjusted(36, 110, -36, -40)
        p.setFont(font(17))
        p.setPen(TEXT)
        p.drawText(area.adjusted(0, 0, 0, -160), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.exercise.how)
        left = max(0, math.ceil(INTRO_SECONDS - (now - self.started_at)))
        p.setFont(font(64, QFont.Weight.Black))
        p.setPen(ACCENT)
        p.drawText(QRectF(area.left(), area.bottom() - 150, area.width(), 90), Qt.AlignmentFlag.AlignCenter, str(left or "¡Ya!"))
        ex = self.exercise
        minutes = f"{ex.seconds / 60:g}".replace(".", ",")
        detail = (
            f"{ex.items} ejercicios en {minutes} minutos"
            if ex.kind != "nback"
            else "1 bloque continuo de 2 minutos"
        )
        p.setFont(font(12))
        p.setPen(MUTED)
        p.drawText(QRectF(area.left(), area.bottom() - 50, area.width(), 24), Qt.AlignmentFlag.AlignCenter, detail)

    def _paint_play(self, p: QPainter, card: QRectF, now: float) -> None:
        left = max(0.0, self.exercise.seconds - (now - self.play_started))
        # time bar
        bar = QRectF(card.left() + 36, card.top() + 94, card.width() - 72, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(58, 58, 60))
        p.drawRoundedRect(bar, 3, 3)
        frac = left / self.exercise.seconds
        p.setBrush(ACCENT if frac > 0.2 else BAD)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * frac, bar.height()), 3, 3)
        p.setFont(font(12, QFont.Weight.DemiBold))
        p.setPen(MUTED)
        p.drawText(QRectF(card.right() - 236, card.top() + 54, 200, 24), Qt.AlignmentFlag.AlignRight,
                   f"{self.runner.progress()}   ·   {int(left // 60)}:{int(left % 60):02d}")
        area = self.content_rect()
        self.runner.paint(p, area)
        if self.runner.flash is not None:
            colour, at = self.runner.flash
            fade = 1 - (now - at) / 0.35
            if fade > 0:
                edge = QColor(colour)
                edge.setAlphaF(fade)
                p.setPen(QPen(edge, 4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(card.adjusted(2, 2, -2, -2), 29, 29)
        p.setFont(font(11))
        p.setPen(MUTED)
        p.drawText(QRectF(card.left(), card.bottom() - 40, card.width(), 22), Qt.AlignmentFlag.AlignCenter, self.runner.keys_hint)

    def _paint_result(self, p: QPainter, card: QRectF) -> None:
        area = card.adjusted(36, 110, -36, -40)
        acc = self.session.accuracy
        # ring
        centre = QPointF(area.center().x(), area.top() + 120)
        p.setPen(QPen(QColor(58, 58, 60), 14))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(centre, 84, 84)
        p.setPen(QPen(GOOD if acc >= 0.7 else (ACCENT if acc >= 0.5 else BAD), 14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(centre.x() - 84, centre.y() - 84, 168, 168), 90 * 16, int(-360 * 16 * acc))
        p.setPen(TEXT)
        p.setFont(font(34, QFont.Weight.Bold))
        p.drawText(QRectF(centre.x() - 84, centre.y() - 84, 168, 168), Qt.AlignmentFlag.AlignCenter, f"{round(acc * 100)}%")
        p.setFont(font(22, QFont.Weight.Bold))
        p.drawText(QRectF(area.left(), area.top() + 230, area.width(), 36), Qt.AlignmentFlag.AlignCenter, self.session.verdict())
        p.setFont(font(15))
        p.setPen(MUTED)
        p.drawText(QRectF(area.left(), area.top() + 272, area.width(), 28), Qt.AlignmentFlag.AlignCenter, self.session.summary())
        if self.stats is not None:
            best = self.stats.best(self.exercise.kind)
            today = self.stats.today()
            times = "entrenamiento" if today == 1 else "entrenamientos"
            p.drawText(QRectF(area.left(), area.top() + 304, area.width(), 28), Qt.AlignmentFlag.AlignCenter,
                       f"Tu mejor marca: {round(best * 100)}% · hoy llevas {today} {times}")
        if isinstance(self.runner, WordsRunner):
            examples = ", ".join(self.runner.item.examples)
            p.drawText(QRectF(area.left(), area.top() + 336, area.width(), 28), Qt.AlignmentFlag.AlignCenter,
                       f"Ejemplos válidos: {examples}")


def word_validator(ask: Callable[[str], str]) -> Callable[[str, str], bool]:
    """Ask Sergio's AI when a word is not in the lists ("¿es «X» un animal?").

    Called from a worker thread by the exercise, never from the window.
    """
    cache: dict[tuple[str, str], bool] = {}

    def validate(word: str, category: str) -> bool:
        key = (brain.plain(word), category)
        if key not in cache:
            reply = ask(
                f"Responde solo «sí» o «no»: ¿«{word}» pertenece a la categoría "
                f"«{category}» (en español)?"
            )
            cache[key] = brain.plain(reply).startswith("si")
        return cache[key]

    return validate


__all__ = [
    "GymSchedule",
    "GymStats",
    "GymWindow",
    "RUNNERS",
    "draw_voxels",
    "force_front",
    "idle_seconds",
    "screen_locked",
    "word_validator",
]

"""Gemini on the screen: a soft light along the edges while he watches.

When the screen is shared in a call, Sergio is not sent pictures now and
then: he sees it live. This glow says so, like a presence in the screen —
a thin breathing light around the monitor he is looking at, brighter while
he talks. It never takes a click (input passes through) and respects
reduced motion.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

DEPTH = 26.0  # how far the light reaches into the screen (px)
COLOURS = ("#9fd3ff", "#c7b8ff", "#ffd1e8", "#bff2e4")  # cool, quiet hues


def intensity(t: float, level: float, speaking: bool) -> float:
    """0..1: a slow breath while watching, lifted by his voice."""
    breath = 0.55 + 0.15 * math.sin(t * 1.6)
    voice = min(1.0, level * 1.6) if speaking else 0.0
    return max(0.0, min(1.0, breath + 0.45 * voice))


class ScreenGlow(QWidget):
    def __init__(self, reduce_motion: bool = False) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.reduce_motion = reduce_motion
        self.level = 0.0
        self.speaking = False
        self._on = 0.0  # fades in and out
        self._want = False
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # -- API --------------------------------------------------------------------
    def set_on(self, on: bool, box: tuple[int, int, int, int] | None = None) -> None:
        self._want = bool(on)
        if on:
            if box is None:
                screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
                g = screen.geometry()
                box = (g.x(), g.y(), g.width(), g.height())
            self.setGeometry(*box)
            self.show()
        if not self._timer.isActive():
            self._timer.start(33)

    def set_level(self, level: float, speaking: bool | None = None) -> None:
        self.level = max(0.0, min(1.0, level))
        if speaking is not None:
            self.speaking = speaking

    # -- animation --------------------------------------------------------------
    def _tick(self) -> None:
        target = 1.0 if self._want else 0.0
        self._on += (target - self._on) * (1.0 if self.reduce_motion else 0.12)
        if not self._want and self._on < 0.02:
            self._on = 0.0
            self._timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = 0.0 if self.reduce_motion else time.monotonic() - self._t0
        k = intensity(t, self.level, self.speaking) * self._on
        w, h = float(self.width()), float(self.height())
        shift = (t * 0.08) % 1.0
        sides = (
            (QRectF(0, 0, w, DEPTH), (0, 0, 0, DEPTH)),
            (QRectF(0, h - DEPTH, w, DEPTH), (0, h, 0, h - DEPTH)),
            (QRectF(0, 0, DEPTH, h), (0, 0, DEPTH, 0)),
            (QRectF(w - DEPTH, 0, DEPTH, h), (w, 0, w - DEPTH, 0)),
        )
        for i, (rect, (x1, y1, x2, y2)) in enumerate(sides):
            colour = QColor(COLOURS[(i + int(shift * 4)) % len(COLOURS)])
            grad = QLinearGradient(x1, y1, x2, y2)
            edge = QColor(colour)
            edge.setAlphaF(0.55 * k)
            clear = QColor(colour)
            clear.setAlphaF(0.0)
            grad.setColorAt(0.0, edge)
            grad.setColorAt(1.0, clear)
            p.fillRect(rect, grad)
        # a crisp hairline at the very edge
        line = QColor("#ffffff")
        line.setAlphaF(0.35 * k)
        p.setPen(QPen(line, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(0.75, 0.75, w - 1.5, h - 1.5))
        p.end()


__all__ = ["ScreenGlow", "intensity"]

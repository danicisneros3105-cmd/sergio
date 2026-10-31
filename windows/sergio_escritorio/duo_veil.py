"""The iPhone Duo fold for real windows (owner, 29 Oct 2026: «recuerda que es
con la animación blur de abrir y cerrar del iPhone Duo»).

When Sergio puts two programs side by side, the screen does what the web's
split screen does: everything goes out of focus for a moment, the two windows
glide to their halves with a soft spring, and the picture comes back into
focus. Native windows cannot be blurred, so a frozen, blurred picture of the
screen covers them while they move, then fades and sharpens away. The veil
never takes a click or the focus.
"""

from __future__ import annotations

import math
from typing import Any, Callable

FRAMES = 14  # the glide, about a quarter of a second
FRAME_S = 0.018
VEIL_IN = 0.12  # seconds to go out of focus
VEIL_OUT = 0.42  # seconds to come back into focus
BLUR_DOWN = 18  # the screen shrunk this many times and grown back = blur

Rect = tuple[int, int, int, int]


def ease(t: float) -> float:
    """The Duo's spring: quick out, a 2 % overshoot, settled at 1."""
    t = min(1.0, max(0.0, t))
    return 1 - math.exp(-6.5 * t) * math.cos(4.2 * t) * (1 - t)


def glide(start: Rect, end: Rect, frames: int = FRAMES) -> list[Rect]:
    """Every step of a window going from *start* to *end* (x, y, w, h)."""
    out = []
    for i in range(1, frames + 1):
        k = ease(i / frames)
        out.append(tuple(round(a + (b - a) * k) for a, b in zip(start, end)))  # type: ignore[misc]
    out[-1] = tuple(end)  # type: ignore[assignment]
    return out


def make_veil() -> Any:
    """The blurred cover (Qt); call ``fold(seconds)`` from the UI thread."""
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
    from PySide6.QtGui import QGuiApplication, QPainter
    from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

    class DuoVeil(QWidget):
        def __init__(self) -> None:
            super().__init__(
                None,
                Qt.FramelessWindowHint
                | Qt.WindowStaysOnTopHint
                | Qt.Tool
                | Qt.WindowTransparentForInput
                | Qt.WindowDoesNotAcceptFocus,
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self._picture = None
            self._fx = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self._fx)
            self._fade = QPropertyAnimation(self._fx, b"opacity", self)
            self._fade.finished.connect(self._done)

        def fold(self, hold: float = 0.3) -> None:
            screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
            if screen is None:
                return
            geo = screen.geometry()
            shot = screen.grabWindow(0)
            small = shot.scaled(max(1, geo.width() // BLUR_DOWN), max(1, geo.height() // BLUR_DOWN),
                                Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # fmt: skip
            self._picture = small.scaled(geo.width(), geo.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self.setGeometry(QRect(geo))
            self._fx.setOpacity(0.0)
            self.show()
            self.raise_()
            # out of focus, hold while the windows glide, back into focus
            self._fade.stop()
            self._fade.setDuration(int((VEIL_IN + hold + VEIL_OUT) * 1000))
            self._fade.setKeyValueAt(0.0, 0.0)
            self._fade.setKeyValueAt(VEIL_IN / (VEIL_IN + hold + VEIL_OUT), 1.0)
            self._fade.setKeyValueAt((VEIL_IN + hold) / (VEIL_IN + hold + VEIL_OUT), 1.0)
            self._fade.setKeyValueAt(1.0, 0.0)
            self._fade.setEasingCurve(QEasingCurve.InOutSine)
            self._fade.start()

        def _done(self) -> None:
            self.hide()
            self._picture = None

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 — Qt
            if self._picture is None:
                return
            p = QPainter(self)
            p.drawPixmap(0, 0, self._picture)
            p.end()

    return DuoVeil()


def run_glide(
    moves: list[tuple[int, Rect, Rect]],
    place: Callable[[int, Rect], None],
    sleep: Callable[[float], None],
    frames: int = FRAMES,
) -> None:
    """Move every window one step at a time, all together."""
    paths = [(hwnd, glide(a, b, frames)) for hwnd, a, b in moves]
    for i in range(frames):
        for hwnd, path in paths:
            place(hwnd, path[i])
        sleep(FRAME_S)


__all__ = ["FRAMES", "ease", "glide", "make_veil", "run_glide"]

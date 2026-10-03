"""The cursor companion: a small orb that lives next to the mouse pointer.

No window, no taskbar entry, never steals focus and lets every click pass
through. It shows what Sergio is doing (listening, thinking, speaking, using
the screen) and a short caption bubble with what was heard or answered.
Drawn with Qt so edges are antialiased and translucent on any wallpaper.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from sergio_escritorio.character import STATE_COLORS, draw_character

# One accent (system blue) plus semantic state colours, as in the web UI.
STATE_LABELS = {
    "listening": "Te escucho",
    "thinking": "Pensando",
    "speaking": "Sergio",
    "acting": "Usando tu pantalla",
    "paused": "Control pausado",
}

OFFSET = QPointF(18, 20)  # orb sits below-right of the pointer tip
CANVAS_W, CANVAS_H = 380, 132
ORB = 9.0  # character radius
BUBBLE_MAX_W = 300.0
FONT_FAMILIES = ["Segoe UI Variable Text", "SF Pro Text", "Geist", "Segoe UI"]
POINT_PAD = 34.0  # where the pointed spot sits inside the canvas
POINT_SECONDS = 7.0


def to_logical(x: float, y: float) -> QPointF:
    """Physical screen pixels (Windows accessibility, mss) -> Qt coordinates.

    Qt keeps each screen's origin in native pixels and scales the size, so a
    point is mapped relative to the origin of the screen that contains it.
    """
    for screen in QGuiApplication.screens():
        geo = screen.geometry()
        dpr = screen.devicePixelRatio() or 1.0
        if (
            geo.x() <= x < geo.x() + geo.width() * dpr
            and geo.y() <= y < geo.y() + geo.height() * dpr
        ):
            return QPointF(geo.x() + (x - geo.x()) / dpr, geo.y() + (y - geo.y()) / dpr)
    return QPointF(x, y)


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


class Companion(QWidget):
    def __init__(self, *, follow: bool = True, captions: bool = True) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(CANVAS_W, CANVAS_H)
        self.state = "idle"
        self.caption = ""
        self._caption_until = 0.0
        self._t0 = time.monotonic()
        self._pos = QPointF(QCursor.pos())
        self._flip = False
        self.follow = follow
        self.captions = captions  # off when the notch shows the text
        self._target: QPointF | None = None  # Clicky-style pointing
        self._target_until = 0.0
        self._target_label = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # -- API (call from the Qt thread; use signals from other threads) -------
    def set_state(self, state: str) -> None:
        self.state = state if state in STATE_COLORS else "idle"
        self.update()

    def say(self, text: str, seconds: float = 0.0) -> None:
        """Show a caption; it fades after *seconds* (default: by length)."""
        self.caption = " ".join(text.split())
        if not seconds:
            seconds = min(14.0, 3.0 + len(self.caption) / 18)
        self._caption_until = time.monotonic() + seconds
        self.update()

    def point_at(
        self, x: float, y: float, label: str = "", physical: bool = True
    ) -> None:
        """Fly to a spot on screen and highlight it for a few seconds."""
        self._target = to_logical(x, y) if physical else QPointF(x, y)
        self._target_until = time.monotonic() + POINT_SECONDS
        self._target_label = label
        self.update()

    @property
    def pointing(self) -> bool:
        return self._target is not None

    # -- motion -------------------------------------------------------------
    def _tick(self) -> None:
        if self._target is not None and time.monotonic() > self._target_until:
            self._target = None
        if self._target is not None:
            self._flip = False
            anchor = self._target - QPointF(POINT_PAD, POINT_PAD)
            self._pos += (anchor - self._pos) * 0.14  # a visible glide over
            self.move(self._pos.toPoint())
        elif self.follow:
            cursor = QPointF(QCursor.pos())
            screen = QGuiApplication.screenAt(cursor.toPoint())
            if screen is not None:
                bounds = screen.availableGeometry()
                self._flip = cursor.x() + CANVAS_W > bounds.right()
                drop = cursor.y() + CANVAS_H > bounds.bottom()
            else:
                drop = False
            anchor = QPointF(
                cursor.x() - (CANVAS_W - OFFSET.x() - 2 * ORB)
                if self._flip
                else cursor.x() + OFFSET.x() - 2 * ORB,
                cursor.y() - CANVAS_H + 2 * ORB - OFFSET.y()
                if drop
                else cursor.y() + OFFSET.y() - 2 * ORB,
            )
            # Critically damped follow: smooth, never overshoots.
            self._pos += (anchor - self._pos) * 0.32
            self.move(self._pos.toPoint())
        if self.caption and time.monotonic() > self._caption_until:
            self.caption = ""
        self.update()

    # -- drawing ------------------------------------------------------------
    def orb_centre(self) -> QPointF:
        if self._target is not None:
            return QPointF(POINT_PAD + 22, POINT_PAD + 20)
        x = CANVAS_W - 2 * ORB if self._flip else 2 * ORB
        return QPointF(x, 2 * ORB)

    def paintEvent(self, _event: object) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = time.monotonic() - self._t0
        if self._target is not None:
            self.draw_spot(painter, t)
        self.draw_orb(painter, t)
        if self._target is not None:
            self.draw_bubble(painter, self._target_label or "Aquí", self.caption)
            painter.end()
            return
        label = STATE_LABELS.get(self.state, "")
        if self.captions and (self.caption or (label and self.state != "speaking")):
            self.draw_bubble(painter, label, self.caption)
        painter.end()

    def draw_orb(self, p: QPainter, t: float) -> None:
        draw_character(p, self.orb_centre(), ORB, self.state, t, QPointF(-0.6, -0.8))

    def draw_spot(self, p: QPainter, t: float) -> None:
        """A soft pulsing ring on the spot Sergio is pointing at."""
        spot = QPointF(POINT_PAD, POINT_PAD)
        accent = STATE_COLORS.get("idle", QColor(10, 132, 255))
        for i in range(2):
            phase = (t * 1.2 + i * 0.5) % 1.0
            ring = QColor(accent)
            ring.setAlphaF(0.55 * (1 - phase))
            p.setPen(QPen(ring, 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(spot, 8 + 18 * phase, 8 + 18 * phase)
        p.setPen(QPen(QColor(255, 255, 255, 230), 2))
        p.setBrush(accent)
        p.drawEllipse(spot, 5.5, 5.5)

    def draw_bubble(self, p: QPainter, label: str, text: str) -> None:
        title_font = _font(8.5, QFont.Weight.DemiBold)
        body_font = _font(10.0)
        body_metrics = QFontMetricsF(body_font)
        pad_x, pad_y = 12.0, 9.0
        lines = (
            self._wrap(text, body_metrics, BUBBLE_MAX_W - 2 * pad_x)[:3] if text else []
        )
        title_h = 15.0 if label else 0.0
        body_w = max(
            (body_metrics.horizontalAdvance(line) for line in lines), default=0.0
        )
        title_w = QFontMetricsF(title_font).horizontalAdvance(label) if label else 0.0
        width = min(BUBBLE_MAX_W, max(body_w, title_w) + 2 * pad_x)
        height = title_h + len(lines) * body_metrics.lineSpacing() + 2 * pad_y
        if not lines:
            height -= 3
        centre = self.orb_centre()
        gap = 2 * ORB + 4
        x = centre.x() - gap - width if self._flip else centre.x() + gap
        rect = QRectF(x, centre.y() - 12, width, height)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(rect.translated(0, 2), 12, 12)
        p.setBrush(QColor(28, 28, 30, 232))  # dark glass, legible on any wallpaper
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawRoundedRect(rect, 12, 12)

        y = rect.top() + pad_y
        if label:
            p.setFont(title_font)
            p.setPen(STATE_COLORS[self.state].lighter(135))
            p.drawText(QPointF(rect.left() + pad_x, y + 11), label)
            y += title_h
        p.setFont(body_font)
        p.setPen(QColor(242, 242, 244))
        for line in lines:
            y += body_metrics.ascent()
            p.drawText(QPointF(rect.left() + pad_x, y), line)
            y += body_metrics.descent() + body_metrics.leading()

    @staticmethod
    def _wrap(text: str, metrics: QFontMetricsF, width: float) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if metrics.horizontalAdvance(trial) <= width:
                current = trial
                continue
            if current:
                lines.append(current)
            current = word
        if current:
            lines.append(current)
        if len(lines) > 3:
            lines = lines[:3]
            lines[2] = metrics.elidedText(
                lines[2] + " …", Qt.TextElideMode.ElideRight, width
            )
        return lines


__all__ = ["Companion", "STATE_COLORS"]

"""The cursor companion: a small orb that lives next to the mouse pointer.

No window, no taskbar entry, never steals focus and lets every click pass
through. It shows what Sergio is doing (listening, thinking, speaking, using
the screen) and a short caption bubble with what was heard or answered.
Drawn with Qt so edges are antialiased and translucent on any wallpaper.
"""

from __future__ import annotations

import math
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
TOP_PAD = 18.0  # room above the orb for hops and sleepy z's
SLEEP_AFTER = 90.0  # seconds without mouse movement before he naps
HAPPY_FOR = 3.0  # seconds of smile after answering
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
        # Life: mood, motion, voice level.
        self.level = 0.0
        self.mood = ""
        self._last_cursor = QPointF(QCursor.pos())
        self._last_move = time.monotonic()
        self._vel = QPointF(0, 0)
        self._bounce_at = -10.0
        self._happy_until = 0.0
        self._sleeping = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # -- API (call from the Qt thread; use signals from other threads) -------
    def set_state(self, state: str) -> None:
        state = state if state in STATE_COLORS else "idle"
        if self.state == "speaking" and state == "idle":
            self._happy_until = time.monotonic() + HAPPY_FOR  # answered: smile
        if state != "idle":
            self._wake()
            self._timer.setInterval(33)
        self.state = state
        self.update()

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, level))

    def bounce(self) -> None:
        """A little hop (you clicked, or he woke up)."""
        self._bounce_at = time.monotonic()

    def _wake(self) -> None:
        self._last_move = time.monotonic()
        if self._sleeping:
            self._sleeping = False
            self.bounce()

    def life(self, now: float) -> tuple[str, float, float]:
        """(mood, squash, hop in px) from what happened recently."""
        if self.state == "idle" and now - self._last_move > SLEEP_AFTER:
            self._sleeping = True
        if self._sleeping:
            mood = "sleep"
        elif self._target is not None:
            mood = "curious"
        elif now < self._happy_until:
            mood = "happy"
        else:
            mood = ""
        speed = (self._vel.x() ** 2 + self._vel.y() ** 2) ** 0.5
        squash = 1.0 + min(0.16, speed * 0.006)  # stretches when moving fast
        hop = 0.0
        phase = now - self._bounce_at
        if 0 <= phase < 0.6:
            wave = math.sin(phase * math.pi / 0.3) * math.exp(-phase * 5)
            squash *= 1.0 - 0.22 * wave
            hop = max(0.0, math.sin(phase * math.pi / 0.6)) * ORB * 0.9
        return mood, squash, hop

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

    def press(self) -> None:
        """The click itself: a quick squash and a ripple on the spot."""
        self._pressed = time.monotonic()
        self.update()

    @property
    def pointing(self) -> bool:
        return self._target is not None

    # -- motion -------------------------------------------------------------
    def _tick(self) -> None:
        now = time.monotonic()
        cursor_now = QPointF(QCursor.pos())
        moved = cursor_now - self._last_cursor
        self._last_cursor = cursor_now
        self._vel = self._vel * 0.7 + moved * 0.3
        if abs(moved.x()) + abs(moved.y()) > 2:
            self._wake()
        if self._target is not None and now > self._target_until:
            self._target = None
        if self._target is not None:
            self._flip = False
            anchor = self._target - QPointF(POINT_PAD, POINT_PAD)
            self._pos += (anchor - self._pos) * 0.14  # a visible glide over
            self._move_to(self._pos)
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
                cursor.y() - CANVAS_H + 2 * ORB + TOP_PAD - OFFSET.y()
                if drop
                else cursor.y() + OFFSET.y() - 2 * ORB - TOP_PAD,
            )
            # Critically damped follow: smooth, never overshoots.
            self._pos += (anchor - self._pos) * 0.32
            self._move_to(self._pos)
        if self.caption and time.monotonic() > self._caption_until:
            self.caption = ""
        self.update()
        # 60 Hz only while something moves; a still cursor and a quiet orb
        # need 10 (a top-level window moved and redrawn 60 times a second
        # costs the whole desktop, even on a fast laptop).
        # Listening or speaking with a still cursor only needs the orb to
        # breathe: 30 Hz (it was 60 all the time, and the conversation is
        # always on, owner 26 Oct 2026: «se laguea demasiado»).
        busy = (
            abs(moved.x()) + abs(moved.y()) > 0.5
            or self._target is not None
            or now - self._bounce_at < 1.0
            or now - self._last_move < 0.6
        )
        alive = self.state != "idle" or now < self._happy_until
        interval = 16 if busy else 33 if alive else 100
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)

    def _move_to(self, pos: QPointF) -> None:
        # Only when the window really lands on another pixel: moving a
        # top-level window costs the whole desktop a recomposition.
        point = pos.toPoint()
        if point != self.pos():
            self.move(point)

    # -- drawing ------------------------------------------------------------
    def orb_centre(self) -> QPointF:
        if self._target is not None:
            return QPointF(POINT_PAD + 22, POINT_PAD + 20)
        x = CANVAS_W - 2 * ORB if self._flip else 2 * ORB
        return QPointF(x, 2 * ORB + TOP_PAD)

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
        mood, squash, hop = self.life(time.monotonic())
        self.mood = mood
        centre = self.orb_centre() - QPointF(0, hop)
        speed = (self._vel.x() ** 2 + self._vel.y() ** 2) ** 0.5
        if speed > 1.5:  # look where we are going
            look = QPointF(self._vel.x() / speed, self._vel.y() / speed)
        else:
            look = QPointF(-0.6, -0.8)  # at the pointer tip
        level = self.level if self.state == "listening" else 0.0
        draw_character(
            p, centre, ORB, self.state, t, look, level, mood=mood, squash=squash
        )
        if self.state == "listening":
            self._draw_wave(p, centre, t)
        elif self.state in ("thinking", "acting"):
            self._draw_dots(p, centre, t)

    def _draw_wave(self, p: QPainter, centre: QPointF, t: float) -> None:
        """Clicky-style live waveform beside him while he listens."""
        side = -1 if self._flip else 1
        x0 = centre.x() + side * (ORB * 1.9)
        colour = STATE_COLORS["listening"].lighter(130)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(colour)
        for i in range(5):
            shape = 0.45 + 0.55 * abs(math.sin(t * 9 + i * 1.3))
            h = max(3.0, ORB * 2.2 * min(1.0, 0.15 + self.level * 1.4) * shape)
            x = x0 + side * i * 4.5
            p.drawRoundedRect(QRectF(x - 1.25, centre.y() - h / 2, 2.5, h), 1.25, 1.25)

    def _draw_dots(self, p: QPainter, centre: QPointF, t: float) -> None:
        """Three dots orbiting him while he thinks."""
        colour = STATE_COLORS[self.state].lighter(140)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            a = t * 4.0 + i * 2.1
            dot = centre + QPointF(math.cos(a) * ORB * 1.7, math.sin(a) * ORB * 1.7)
            c = QColor(colour)
            c.setAlphaF(0.45 + 0.55 * (i + 1) / 3)
            p.setBrush(c)
            p.drawEllipse(dot, 1.8, 1.8)

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
        since = time.monotonic() - getattr(self, "_pressed", -10.0)
        if 0 <= since < 0.45:  # the press: a fast, bright ripple
            k = since / 0.45
            p.setPen(QPen(QColor(255, 255, 255, int(230 * (1 - k))), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(spot, 6 + 26 * k, 6 + 26 * k)

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
        gap = 2 * ORB + 4 + (26 if self.state == "listening" else 0)  # room for wave
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

"""The notch: a Dynamic-Island-style pill at the top centre of the screen.

Pure black, flush with the top edge, home of Sergio's orb. Compact when idle
(orb + a quiet waveform); while listening the waveform follows your real
voice; while thinking the label shimmers; answers type themselves in. Click
it to open the control center (panel.py). Only the pill takes clicks.
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRegion,
)
from PySide6.QtWidgets import QWidget

from sergio_escritorio.character import PALETTES, STATE_COLORS, draw_character

LABELS = {
    "idle": "Sergio",
    "listening": "Te escucho",
    "thinking": "Pensando",
    "speaking": "Sergio",
    "acting": "Usando tu pantalla",
    "paused": "Control pausado",
}
FONTS = ["Segoe UI Variable Display", "SF Pro Display", "Geist", "Segoe UI"]

CANVAS_W, CANVAS_H = 540, 160
COMPACT = (132.0, 36.0)
MEDIUM = (252.0, 48.0)
EXPANDED_W = 460.0
PAD = 16.0
RADIUS = 22.0
BARS = 22
TYPE_SPEED = 55.0  # characters per second for answers


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(FONTS)
    font.setPointSizeF(size)
    font.setWeight(weight)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 99)
    return font


class Notch(QWidget):
    def __init__(
        self,
        *,
        on_click: Callable[[], None] | None = None,
        fullscreen_app: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clic para abrir el centro de control de Sergio")
        self.resize(CANVAS_W, CANVAS_H)
        self.on_click = on_click
        # Hide while a video or game is fullscreen (unless Sergio is active).
        self.fullscreen_app = fullscreen_app or (lambda: False)
        self._mask_rect = None
        self._hidden_for_fullscreen = False
        self._last_fs_check = 0.0
        self.state = "idle"
        self.caption = ""
        self._caption_until = 0.0
        self._caption_at = 0.0
        self.level = 0.0
        self._levels: deque[float] = deque([0.0] * BARS, maxlen=BARS)
        self._t0 = time.monotonic()
        self._w, self._h = COMPACT
        self._title = _font(9.0, QFont.Weight.DemiBold)
        self._body = _font(10.5)
        self._place()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # -- API ------------------------------------------------------------------
    def set_state(self, state: str) -> None:
        self.state = state if state in STATE_COLORS else "idle"

    def set_level(self, level: float) -> None:
        """Live microphone volume 0..1 (called ~30 times a second)."""
        self.level = max(0.0, min(1.0, level))

    def say(self, text: str, seconds: float = 0.0) -> None:
        self.caption = " ".join(text.split())
        self._caption_at = time.monotonic()
        self._caption_until = self._caption_at + (
            seconds or min(18.0, 4.0 + len(self.caption) / 15)
        )

    # -- layout -----------------------------------------------------------------
    def _place(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.geometry()
        self.move(geo.x() + (geo.width() - CANVAS_W) // 2, geo.y())

    def expanded(self) -> bool:
        return bool(self.caption) or self.state not in ("idle",)

    def lines(self) -> list[str]:
        if not self.caption:
            return []
        metrics = QFontMetricsF(self._body)
        width = EXPANDED_W - 2 * PAD - 58
        out: list[str] = []
        current = ""
        for word in self.caption.split():
            trial = f"{current} {word}".strip()
            if metrics.horizontalAdvance(trial) <= width:
                current = trial
            else:
                if current:
                    out.append(current)
                current = word
        if current:
            out.append(current)
        if len(out) > 3:
            out = out[:3]
            out[2] = metrics.elidedText(
                out[2] + " …", Qt.TextElideMode.ElideRight, width
            )
        return out

    def target_size(self) -> tuple[float, float]:
        if not self.expanded():
            return COMPACT
        lines = self.lines()
        if not lines:
            return MEDIUM  # just the state, e.g. "Te escucho" + live waveform
        metrics = QFontMetricsF(self._body)
        return EXPANDED_W, max(62.0, 34.0 + len(lines) * metrics.lineSpacing() + PAD)

    def pill(self) -> QRectF:
        return QRectF((CANVAS_W - self._w) / 2, 0, self._w, self._h)

    # -- animation --------------------------------------------------------------
    def _tick(self) -> None:
        if self.caption and time.monotonic() > self._caption_until:
            self.caption = ""
        # Waveform history: real voice while listening, gentle idle shimmer.
        t = time.monotonic() - self._t0
        if self.state == "listening":
            sample = self.level
        elif self.state == "speaking":
            sample = 0.25 + 0.5 * abs(math.sin(t * 7.3))
        else:
            # Idle: the small wave still follows the microphone, so you can see
            # at a glance that Sergio hears you.
            sample = max(0.06, self.level * 0.6)
        self._levels.append(self._levels[-1] * 0.35 + sample * 0.65)
        tw, th = self.target_size()
        # Spring-like ease toward the target size (no overshoot).
        self._w += (tw - self._w) * 0.2
        self._h += (th - self._h) * 0.2
        rect = self.pill().toAlignedRect().adjusted(-1, 0, 1, 1)
        if rect != self._mask_rect:
            self._mask_rect = rect
            self.setMask(QRegion(rect))  # clicks outside the pill go through
        self._respect_fullscreen()
        self.update()

    def _respect_fullscreen(self) -> None:
        now = time.monotonic()
        if now - self._last_fs_check < 1.0:
            return
        self._last_fs_check = now
        try:
            covered = self.fullscreen_app() and not self.expanded()
        except Exception:  # noqa: BLE001 — never let a check break the notch
            covered = False
        if covered and not self._hidden_for_fullscreen:
            self._hidden_for_fullscreen = True
            self.setWindowOpacity(0.0)
        elif not covered and self._hidden_for_fullscreen:
            self._hidden_for_fullscreen = False
            self.setWindowOpacity(1.0)

    def mousePressEvent(self, event: object) -> None:  # noqa: N802 (Qt API)
        if self.on_click is not None:
            self.on_click()

    # -- drawing ----------------------------------------------------------------
    def paintEvent(self, _event: object) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = time.monotonic() - self._t0
        rect = self.pill()

        # Flat top (flush with the screen edge), soft round bottom: a notch.
        path = QPainterPath()
        r = min(RADIUS, rect.height() / 2)
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.right(), rect.bottom() - r)
        path.cubicTo(
            rect.right(),
            rect.bottom() - r * 0.2,
            rect.right() - r * 0.2,
            rect.bottom(),
            rect.right() - r,
            rect.bottom(),
        )
        path.lineTo(rect.left() + r, rect.bottom())
        path.cubicTo(
            rect.left() + r * 0.2,
            rect.bottom(),
            rect.left(),
            rect.bottom() - r * 0.2,
            rect.left(),
            rect.bottom() - r,
        )
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawPath(path)

        compact = rect.height() < 42
        size = 10.5 if compact else 15.0
        centre = QPointF(
            rect.left() + PAD + size,
            rect.top()
            + (rect.height() / 2 if compact else min(31.0, rect.height() / 2)),
        )
        draw_character(
            p,
            centre,
            size,
            self.state,
            t,
            self._look(centre),
            level=self.level if self.state == "listening" else 0.0,
        )

        if compact:
            self._draw_wave(
                p,
                QRectF(rect.right() - PAD - 44, rect.top() + 9, 44, rect.height() - 18),
                9,
            )
            return

        text_x = centre.x() + size + 14
        label = LABELS.get(self.state, "Sergio")
        has_text = bool(self.lines())
        title_y = rect.top() + (24 if has_text else rect.height() / 2 + 4.5)
        p.setFont(self._title)
        if self.state == "thinking":
            self._shimmer(p, QPointF(text_x, title_y), label + "…", t)
        else:
            colour = QColor(PALETTES.get(self.state, PALETTES["idle"])[2])
            p.setPen(colour if self.state != "idle" else QColor(150, 150, 158))
            p.drawText(QPointF(text_x, title_y), label)
        if self.state in ("listening", "speaking") or not has_text:
            wave_w = 64.0
            self._draw_wave(
                p,
                QRectF(rect.right() - PAD - wave_w, rect.top() + 12, wave_w, 22),
                14,
            )
        if not has_text:
            return
        p.setFont(self._body)
        p.setPen(QColor(244, 244, 246))
        metrics = QFontMetricsF(self._body)
        shown = int((time.monotonic() - self._caption_at) * TYPE_SPEED)
        y = rect.top() + 30
        for line in self.lines():
            if shown <= 0:
                break
            visible = line[:shown]
            shown -= len(line) + 1
            y += metrics.ascent()
            if y > rect.bottom() - 6:
                break
            p.drawText(QPointF(text_x, y), visible)
            y += metrics.descent() + metrics.leading()

    def _draw_wave(self, p: QPainter, box: QRectF, bars: int) -> None:
        """Rounded bars from the recent levels, coloured like the orb."""
        _, mid, bright, _ = PALETTES.get(self.state, PALETTES["idle"])
        grad = QLinearGradient(box.topLeft(), box.topRight())
        grad.setColorAt(0.0, QColor(mid))
        grad.setColorAt(1.0, QColor(bright))
        values = list(self._levels)[-bars:]
        gap = box.width() / bars
        bar_w = max(2.0, gap * 0.55)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        t = time.monotonic() - self._t0
        for i, v in enumerate(values):
            # Each bar breathes on its own phase so it reads as a voice wave.
            shape = 0.55 + 0.45 * math.sin(t * 9.0 + i * 1.7) * math.cos(
                t * 3.1 + i * 0.6
            )
            h = max(bar_w, box.height() * min(1.0, 0.12 + v * 1.25 * shape))
            x = box.left() + i * gap + (gap - bar_w) / 2
            y = box.center().y() - h / 2
            p.drawRoundedRect(QRectF(x, y, bar_w, h), bar_w / 2, bar_w / 2)

    def _shimmer(self, p: QPainter, at: QPointF, text: str, t: float) -> None:
        """Label with a light sweep across it (thinking)."""
        width = QFontMetricsF(self._title).horizontalAdvance(text)
        sweep = (t * 0.9) % 1.6 - 0.3
        grad = QLinearGradient(at.x(), 0, at.x() + width, 0)
        base = QColor(150, 150, 165)
        grad.setColorAt(0.0, base)
        grad.setColorAt(max(0.0, min(1.0, sweep - 0.15)), base)
        grad.setColorAt(max(0.0, min(1.0, sweep)), QColor(255, 255, 255))
        grad.setColorAt(max(0.0, min(1.0, sweep + 0.15)), base)
        grad.setColorAt(1.0, base)
        p.setPen(QPen(grad, 1))
        p.drawText(at, text)

    def _look(self, centre: QPointF) -> QPointF:
        """Eyes follow the mouse pointer."""
        here = self.mapToGlobal(centre.toPoint())
        cursor = QCursor.pos()
        dx, dy = cursor.x() - here.x(), cursor.y() - here.y()
        dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
        return QPointF(dx / dist, max(-1.0, min(1.0, dy / dist)))


__all__ = ["Notch"]

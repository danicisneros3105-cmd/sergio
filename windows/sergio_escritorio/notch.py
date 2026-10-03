"""The notch: a Dynamic-Island-style pill at the top centre of the screen.

Black, flush with the top edge, home of Sergio's character. Small when idle;
grows smoothly to show what Sergio hears, thinks, says and does. Clicking it
talks to Sergio. Only the pill takes clicks; the rest of the screen is free.
"""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QRegion,
)
from PySide6.QtWidgets import QWidget

from sergio_escritorio.character import STATE_COLORS, draw_character

LABELS = {
    "idle": "Sergio",
    "listening": "Te escucho",
    "thinking": "Pensando",
    "speaking": "Sergio",
    "acting": "Usando tu pantalla",
    "paused": "Control pausado",
}
FONTS = ["Segoe UI Variable Text", "SF Pro Text", "Geist", "Segoe UI"]

CANVAS_W, CANVAS_H = 520, 150
COMPACT = (148.0, 34.0)
MEDIUM = (232.0, 46.0)
EXPANDED_W = 440.0
PAD = 14.0
RADIUS = 20.0


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(FONTS)
    font.setPointSizeF(size)
    font.setWeight(weight)
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
        self.setToolTip("Clic para hablar con Sergio")
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

    def say(self, text: str, seconds: float = 0.0) -> None:
        self.caption = " ".join(text.split())
        self._caption_until = time.monotonic() + (
            seconds or min(16.0, 3.5 + len(self.caption) / 16)
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
        width = EXPANDED_W - 2 * PAD - 52
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
            return MEDIUM  # just the state, e.g. "Te escucho"
        metrics = QFontMetricsF(self._body)
        return EXPANDED_W, max(58.0, 30.0 + len(lines) * metrics.lineSpacing() + PAD)

    def pill(self) -> QRectF:
        return QRectF((CANVAS_W - self._w) / 2, 0, self._w, self._h)

    # -- animation --------------------------------------------------------------
    def _tick(self) -> None:
        if self.caption and time.monotonic() > self._caption_until:
            self.caption = ""
        tw, th = self.target_size()
        # Spring-like ease toward the target size (no overshoot).
        self._w += (tw - self._w) * 0.22
        self._h += (th - self._h) * 0.22
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

        # Flat top (flush with the screen edge), round bottom: a real notch.
        path = QPainterPath()
        r = min(RADIUS, rect.height() / 2)
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.right(), rect.bottom() - r)
        path.quadTo(rect.right(), rect.bottom(), rect.right() - r, rect.bottom())
        path.lineTo(rect.left() + r, rect.bottom())
        path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - r)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawPath(path)

        compact = rect.height() < 40
        size = 11.0 if compact else 17.0
        centre = QPointF(
            rect.left() + PAD + size,
            rect.top()
            + (rect.height() / 2 if compact else min(29.0, rect.height() / 2)),
        )
        draw_character(p, centre, size, self.state, t, self._look(centre))

        text_x = centre.x() + size + 14
        colour = STATE_COLORS.get(self.state, STATE_COLORS["idle"])
        p.setFont(self._title)
        if compact:
            p.setPen(QColor(235, 235, 240))
            baseline = rect.top() + rect.height() / 2 + 4.5
            p.drawText(QPointF(text_x, baseline), LABELS.get(self.state, "Sergio"))
            return
        p.setPen(colour.lighter(140) if self.state != "idle" else QColor(160, 160, 170))
        has_text = bool(self.lines())
        title_y = rect.top() + (22 if has_text else rect.height() / 2 + 4.5)
        p.drawText(QPointF(text_x, title_y), LABELS.get(self.state, "Sergio"))
        p.setFont(self._body)
        p.setPen(QColor(244, 244, 246))
        metrics = QFontMetricsF(self._body)
        y = rect.top() + 26
        for line in self.lines():
            y += metrics.ascent()
            if y > rect.bottom() - 6:
                break
            p.drawText(QPointF(text_x, y), line)
            y += metrics.descent() + metrics.leading()

    def _look(self, centre: QPointF) -> QPointF:
        """Eyes follow the mouse pointer."""
        here = self.mapToGlobal(centre.toPoint())
        cursor = QCursor.pos()
        dx, dy = cursor.x() - here.x(), cursor.y() - here.y()
        dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
        return QPointF(dx / dist, max(-1.0, min(1.0, dy / dist)))


__all__ = ["Notch"]

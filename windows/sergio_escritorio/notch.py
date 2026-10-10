"""The notch: a Dynamic-Island-style pill at the top centre of the screen.

Pure black, flush with the top edge, home of Sergio's orb. Compact when idle
(orb + a quiet waveform); while listening the waveform follows your real
voice; while thinking the label shimmers; answers type themselves in. Click
it to open the control center (panel.py). Only the pill takes clicks.

Live Activities (activities.py): a running job rides in the pill with its
progress ring and name; when two run at once the island splits in two like
an iPhone's — the «dúo», a round bubble beside the pill with the second
one's ring (and «+N» for more). Sizes move on real springs (a soft
overshoot, like iOS), and a finished job shows a check before merging back.
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
    QPixmap,
    QRegion,
    QTransform,
)
from PySide6.QtWidgets import QWidget

from sergio_escritorio.activities import Activities, Activity, Fold, Spring
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

CANVAS_W, CANVAS_H = 620, 160
COMPACT = (132.0, 36.0)
LIVE = (236.0, 36.0)  # compact with a Live Activity in it
BUBBLE = 36.0  # the second island of the «dúo»
GAP = 9.0
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
        self.name = "Sergio"  # personalisation can rename him
        self.caption = ""
        self._caption_until = 0.0
        self._caption_at = 0.0
        self.level = 0.0
        self.call_since: float | None = None  # in a call with Sergio
        self._levels: deque[float] = deque([0.0] * BARS, maxlen=BARS)
        self._t0 = time.monotonic()
        self._w, self._h = COMPACT
        self._sw, self._sh = Spring(COMPACT[0]), Spring(COMPACT[1])
        self._duo = Fold()  # the iPhone Duo fold: 0° merged .. 180° split
        self._duo_item: Activity | None = None  # what the folding half shows
        self._duo_more = 0
        self._last_tick = time.monotonic()
        self.activities: Activities | None = None
        self._live: list[Activity] = []
        self._small = _font(8.2, QFont.Weight.DemiBold)
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

    def set_call(self, active: bool) -> None:
        """A green call timer, like the Dynamic Island during a phone call."""
        self.call_since = time.monotonic() if active else None

    def call_time(self) -> str:
        if self.call_since is None:
            return ""
        seconds = int(time.monotonic() - self.call_since)
        return f"{seconds // 60}:{seconds % 60:02d}"

    def say(self, text: str, seconds: float = 0.0) -> None:
        text = " ".join(text.split())
        # A live call sends the sentence as it grows: keep typing, no restart.
        growing = bool(self.caption) and text.startswith(self.caption)
        self.caption = text
        if not growing:
            self._caption_at = time.monotonic()
        self._caption_until = time.monotonic() + (
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
            return LIVE if self._live and self.call_since is None else COMPACT
        lines = self.lines()
        if not lines:
            return MEDIUM  # just the state, e.g. "Te escucho" + live waveform
        metrics = QFontMetricsF(self._body)
        return EXPANDED_W, max(62.0, 34.0 + len(lines) * metrics.lineSpacing() + PAD)

    def pill(self) -> QRectF:
        return QRectF((CANVAS_W - self._w) / 2, 0, self._w, self._h)

    def hinge(self) -> float:
        """The x of the fold's hinge, just right of the pill."""
        return self.pill().right() + GAP

    def bubble(self) -> QRectF | None:
        """The second island (dúo): where the folding half is right now."""
        if self._duo.angle <= 0.5:
            return None
        hinge, far = self.hinge(), self.hinge() + BUBBLE * self._duo.reach()
        left, right = min(hinge, far), max(hinge, far)
        return QRectF(left, 0, max(1.0, right - left), BUBBLE)

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
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        self._live = self.activities.snapshot() if self.activities is not None else []
        tw, th = self.target_size()
        # Real springs (a soft iOS overshoot) toward the target size.
        self._sw.target, self._sh.target = tw, th
        self._w, self._h = self._sw.step(dt), self._sh.step(dt)
        self._duo.open(len(self._live) >= 2)
        self._duo.step(dt)
        region = QRegion(self.pill().toAlignedRect().adjusted(-1, 0, 1, 1))
        bubble = self.bubble()
        if bubble is not None:
            region = region.united(
                QRegion(bubble.toAlignedRect().adjusted(-1, 0, 1, 1))
            )
        if region != self._mask_rect:
            self._mask_rect = region
            self.setMask(region)  # clicks outside the islands go through
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

        if self.bubble() is not None:
            # While it folds shut the second activity may already be gone:
            # the last one shown keeps folding away.
            if len(self._live) >= 2:
                self._duo_item, self._duo_more = self._live[1], len(self._live) - 2
            if self._duo_item is not None:
                self._draw_fold(p, self._duo_item, self._duo_more, t)
        if compact:
            if self.call_since is not None:
                self._draw_call(p, rect)
            elif self._live:
                self._draw_live(p, rect, self._live[0], t)
            else:
                self._draw_wave(
                    p,
                    QRectF(
                        rect.right() - PAD - 44, rect.top() + 9, 44, rect.height() - 18
                    ),
                    9,
                )
            return

        text_x = centre.x() + size + 14
        label = LABELS.get(self.state, self.name)
        if label == "Sergio":
            label = self.name
        if self.call_since is not None and self.state in ("idle", "listening"):
            label = f"En llamada · {self.call_time()}"
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

    # -- Live Activities ----------------------------------------------------------
    def _ring(
        self, p: QPainter, centre: QPointF, radius: float, item: Activity, t: float
    ) -> None:
        """Progress ring (spins when the progress is unknown); check or cross at the end."""
        colour = QColor(item.colour)
        track = QColor(colour)
        track.setAlpha(55)
        box = QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(track, 2.6))
        p.drawEllipse(box)
        pen = QPen(colour, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        if item.state == "running" and item.progress is None:
            start = int((-t * 360 * 0.9) % 360 * 16)
            p.drawArc(box, start, int(100 * 16))
        else:
            span = 1.0 if item.state != "running" else (item.progress or 0.0)
            p.drawArc(box, 90 * 16, int(-span * 360 * 16))
        if item.state == "done":
            k = min(
                1.0, (time.monotonic() - item.ended) / 0.35
            )  # the check draws itself
            a = QPointF(centre.x() - radius * 0.42, centre.y() + radius * 0.02)
            b = QPointF(centre.x() - radius * 0.1, centre.y() + radius * 0.34)
            c = QPointF(centre.x() + radius * 0.45, centre.y() - radius * 0.32)
            path = QPainterPath(a)
            if k < 0.4:
                path.lineTo(a + (b - a) * (k / 0.4))
            else:
                path.lineTo(b)
                path.lineTo(b + (c - b) * ((k - 0.4) / 0.6))
            p.drawPath(path)
        elif item.state == "failed":
            d = radius * 0.32
            p.drawLine(
                QPointF(centre.x() - d, centre.y() - d),
                QPointF(centre.x() + d, centre.y() + d),
            )
            p.drawLine(
                QPointF(centre.x() + d, centre.y() - d),
                QPointF(centre.x() - d, centre.y() + d),
            )

    def _draw_live(self, p: QPainter, rect: QRectF, item: Activity, t: float) -> None:
        """Compact island with one Live Activity: its name and its ring."""
        ring = QPointF(rect.right() - PAD - 9, rect.center().y())
        self._ring(p, ring, 9.0, item, t)
        left = rect.left() + PAD + 2 * 10.5 + 10
        width = ring.x() - 16 - left
        if width < 30:
            return
        p.setFont(self._small)
        p.setPen(QColor(item.colour))
        metrics = QFontMetricsF(self._small)
        text = metrics.elidedText(item.title, Qt.TextElideMode.ElideRight, width)
        p.drawText(QPointF(left, rect.center().y() + 4), text)

    def _draw_fold(self, p: QPainter, item: Activity, more: int, t: float) -> None:
        """The dúo folding open like the iPhone Duo's cover half.

        The open bubble is drawn flat, blurred and darkened by how closed
        it is, then mapped onto the half that swings around the hinge, with
        a little perspective (the far edge shrinks as it turns)."""
        fold = self._duo
        size = int(BUBBLE)
        face = QPixmap(size, size)
        face.fill(Qt.GlobalColor.transparent)
        q = QPainter(face)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(0, 0, BUBBLE, BUBBLE)
        if fold.facing():
            self._draw_bubble(q, box, item, more, t)
        else:  # its back, the plain black island
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(0, 0, 0))
            q.drawEllipse(box)
        effect, dark = fold.effect(), fold.darken()
        if dark > 0.0:
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(0, 0, 0, int(255 * dark)))
            q.drawEllipse(box)
        q.end()
        if effect > 0.02:
            # Blur by shrinking and enlarging smoothly: cheap, and soft enough.
            small = max(2, int(size * (1.0 - 0.85 * effect)))
            mode = Qt.TransformationMode.SmoothTransformation
            face = face.scaled(small, small, mode=mode).scaled(size, size, mode=mode)
        scale_x = fold.reach()  # -1 (lying over the pill) .. 1 (open)
        depth = 0.25 * math.sin(math.radians(fold.angle)) / BUBBLE
        # Local (x from the hinge, y from the middle) → screen, projective.
        warp = QTransform(scale_x, 0.0, depth, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        warp *= QTransform.fromTranslate(self.hinge(), BUBBLE / 2)
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setTransform(warp, combine=True)
        p.drawPixmap(QPointF(0, -BUBBLE / 2), face)
        p.restore()

    def _draw_bubble(
        self, p: QPainter, box: QRectF, item: Activity, more: int, t: float
    ) -> None:
        """The dúo: a second black island with the next activity's ring."""
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawEllipse(box)
        self._ring(p, box.center(), box.width() * 0.3, item, t)
        if more > 0:
            p.setFont(self._small)
            badge = QRectF(box.right() - 15, box.bottom() - 13, 17, 13)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(58, 58, 64))
            p.drawRoundedRect(badge, 6.5, 6.5)
            p.setPen(QColor(240, 240, 245))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"+{more}")

    def _draw_call(self, p: QPainter, rect: QRectF) -> None:
        """Compact notch during a call: green handset + elapsed time."""
        green = QColor(48, 209, 88)
        p.setFont(self._title)
        text = self.call_time()
        width = QFontMetricsF(self._title).horizontalAdvance(text)
        right = rect.right() - PAD
        p.setPen(green)
        p.drawText(QPointF(right - width, rect.center().y() + 4), text)
        x, y = right - width - 12, rect.center().y()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(green)
        p.drawEllipse(QPointF(x, y), 4.5, 4.5)

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


__all__ = ["BUBBLE", "LIVE", "Notch"]

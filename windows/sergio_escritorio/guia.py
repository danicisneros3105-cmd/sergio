"""Drawings on the real screen that show the way, then get out of the way.

The owner (28 Oct 2026): «para que no pierdas tiempo buscando con la mirada,
Sergio dibuja flechas, círculos o líneas en 2D y 3D directamente sobre tu
pantalla, justo encima del botón que buscas, y mueve un cursor animado para
que sigas el recorrido. En cuanto haces clic o entiendes la instrucción, los
dibujos desaparecen».

A guide is a short list of marks, in order:

* ``arrow``: a solid arrow that lands on the spot (``depth`` gives it a
  3D side and a shadow, and it bobs towards the target);
* ``circle``: a hand-drawn ring around the element, drawn as you watch;
* ``box``: the element framed, the rest of the screen dimmed a little;
* ``underline``: a stroke under a word or a field;
* ``line``: from this mark to the next one (where to drag, what goes with what).

A ghost cursor (not the real one: the user keeps the mouse) travels from mark
to mark with a small press on each. The overlay never takes a click or the
focus: the first click anywhere, Esc, «entendido» or the time limit fades it.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Iterable

SHAPES = ("arrow", "circle", "box", "underline", "line")
MAX_MARKS = 6
SHOW_SECONDS = 25.0  # nobody needs it longer; a click ends it sooner
CLICK_GRACE = 0.5  # the click that asked for the guide does not close it
FADE = 0.35
DRAW_IN = 0.55  # each stroke draws itself in this long
STEP = 0.9  # the ghost cursor's time from one mark to the next
UNDERSTOOD = (
    "entendido",
    "entiendo",
    "ya entendi",
    "ya vi",
    "ya lo vi",
    "lo veo",
    "listo",
    "vale",
    "ok",
    "okay",
    "gracias",
    "perfecto",
    "ya esta",
)


@dataclass
class Mark:
    """One drawing, in physical screen pixels (as Windows accessibility gives them)."""

    x: float
    y: float
    w: float = 0.0  # the element's size; 0 = only a spot is known
    h: float = 0.0
    shape: str = "arrow"
    text: str = ""
    depth: bool = True  # 3D arrows by default; flat if asked


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def marks_from(items: Iterable[Any]) -> list[Mark]:
    """Clean marks from what a model or a tool asked for (bad ones are dropped)."""
    out: list[Mark] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        x, y = _num(item.get("x")), _num(item.get("y"))
        if x is None or y is None:
            continue
        shape = str(item.get("shape") or "arrow").strip().lower()
        shape = {
            "flecha": "arrow",
            "circulo": "circle",
            "círculo": "circle",
            "recuadro": "box",
            "caja": "box",
            "subrayado": "underline",
            "linea": "line",
            "línea": "line",
        }.get(shape, shape)
        if shape not in SHAPES:
            shape = "arrow"
        w, h = _num(item.get("w")) or 0.0, _num(item.get("h")) or 0.0
        out.append(
            Mark(
                x,
                y,
                max(0.0, min(w, 4000.0)),
                max(0.0, min(h, 4000.0)),
                shape,
                " ".join(str(item.get("text") or "").split())[:48],
                item.get("depth") not in (False, "false", "2d", "flat"),
            )
        )
        if len(out) >= MAX_MARKS:
            break
    return out


def plain(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def understood(text: str) -> bool:
    """«Entendido», «ya lo vi», «ok gracias»: the guide can go."""
    said = f" {plain(text)} "
    return len(said) < 40 and any(f" {w} " in said for w in UNDERSTOOD)


def ease(t: float) -> float:
    """Ease in-out (cubic): starts and lands softly, like a hand."""
    t = max(0.0, min(1.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def cursor_at(points: list[tuple[float, float]], start: tuple[float, float], t: float) -> tuple[float, float, float]:
    """Where the ghost cursor is *t* seconds in, and how pressed it is (0–1).

    It glides along a slight curve to each mark, presses, and moves on; after
    the last one it stays there."""
    if not points:
        return start[0], start[1], 0.0
    route = [start, *points]
    leg = int(t // STEP)
    if leg >= len(points):
        last = points[-1]
        return last[0], last[1], 0.0
    k = (t - leg * STEP) / STEP
    (ax, ay), (bx, by) = route[leg], route[leg + 1]
    glide = ease(min(1.0, k / 0.75))
    # A gentle arc, not a ruler: the middle of the leg bows to one side.
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy) or 1.0
    bow = math.sin(glide * math.pi) * min(60.0, length * 0.12)
    x = ax + dx * glide - dy / length * bow
    y = ay + dy * glide + dx / length * bow
    press = max(0.0, 1.0 - abs(k - 0.85) / 0.1) if k > 0.75 else 0.0
    return x, y, press


def arrow_tail(mark: Mark, screen_w: float, screen_h: float) -> tuple[float, float]:
    """Where an arrow starts so it points at the mark from the roomier side
    (never from off-screen), about 110 px away."""
    tip_x, tip_y = mark.x, mark.y
    dx = -1.0 if tip_x > screen_w * 0.6 else 1.0
    dy = 1.0 if tip_y < screen_h * 0.35 else -1.0
    reach = 110.0
    gap = max(mark.w, mark.h) / 2 + 6 if mark.w and mark.h else 8.0
    norm = math.hypot(dx, dy)
    ux, uy = dx / norm, dy / norm
    return tip_x + ux * (gap + reach), tip_y + uy * (gap + reach)


class Clock:
    """What the guide is doing at a moment: drawn, fading, gone."""

    def __init__(self, now: float, seconds: float = SHOW_SECONDS, steps: int = 0) -> None:
        self.start = now
        self.seconds = seconds
        self.until = now + seconds
        self.ending: float | None = None
        # Step by step (owner, 29 Oct 2026: «mejora la guía en pantalla»):
        # one mark at a time; each click moves to the next, the last ends it.
        self.steps = steps if steps > 1 else 0
        self.current = 0
        self.step_at = now

    def dismiss(self, now: float) -> None:
        if self.ending is None:
            self.ending = now

    def click(self, now: float) -> bool:
        """A click: the next step, or the end; never the very click that
        brought it."""
        since = self.step_at if self.current else self.start
        if now - since < CLICK_GRACE:
            return False
        if self.steps and self.current < self.steps - 1:
            self.current += 1
            self.step_at = now
            self.until = now + self.seconds  # each step has its own time
            return True
        self.dismiss(now)
        return True

    def back(self, now: float) -> None:
        """The previous step (a key the owner presses)."""
        if self.steps and self.current > 0:
            self.current -= 1
            self.step_at = now
            self.until = now + self.seconds

    def alpha(self, now: float) -> float:
        if self.ending is None and now >= self.until:
            self.ending = self.until
        if self.ending is not None:
            return max(0.0, 1.0 - (now - self.ending) / FADE)
        return min(1.0, (now - self.start) / 0.18)

    def done(self, now: float) -> bool:
        return self.alpha(now) <= 0.0 and now > self.start


# -- drawing (Qt) ---------------------------------------------------------------------


def make_overlay() -> Any:
    """The overlay window (built lazily so the logic above has no Qt cost)."""
    from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
    from PySide6.QtGui import (
        QColor,
        QCursor,
        QFont,
        QFontMetricsF,
        QGuiApplication,
        QPainter,
        QPainterPath,
        QPen,
        QPolygonF,
    )
    from PySide6.QtWidgets import QWidget

    from sergio_escritorio.companion import to_logical

    accent = QColor(10, 132, 255)  # the system blue: one accent, as everywhere
    ink = QColor(255, 255, 255)

    class GuideOverlay(QWidget):
        def __init__(self) -> None:
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
            self.marks: list[Mark] = []
            self.points: list[QPointF] = []
            self.sizes: list[tuple[float, float]] = []
            self.clock: Clock | None = None
            self.caption = ""
            self._from = QPointF(0, 0)
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)

        # -- API (Qt thread) ----------------------------------------------------
        def show_marks(self, marks: list[Mark], caption: str = "", steps: bool = False) -> None:
            if not marks:
                return
            first = to_logical(marks[0].x, marks[0].y)
            screen = QGuiApplication.screenAt(first.toPoint()) or QGuiApplication.primaryScreen()
            geo = screen.geometry()
            dpr = screen.devicePixelRatio() or 1.0
            self.setGeometry(geo)
            self.marks = marks
            self.points = [to_logical(m.x, m.y) - QPointF(geo.topLeft()) for m in marks]
            self.sizes = [(m.w / dpr, m.h / dpr) for m in marks]
            self.caption = caption[:90]
            self._from = QPointF(QCursor.pos()) - QPointF(geo.topLeft())
            self.clock = Clock(time.monotonic(), steps=len(marks) if steps else 0)
            self.show()
            self.raise_()
            self._timer.start(16)

        def clicked(self) -> None:
            if self.clock is not None and self.clock.click(time.monotonic()):
                self._timer.start(16)

        def dismiss(self) -> None:
            if self.clock is not None:
                self.clock.dismiss(time.monotonic())

        @property
        def showing(self) -> bool:
            return self.isVisible() and self.clock is not None and self.clock.ending is None

        def _tick(self) -> None:
            now = time.monotonic()
            if self.clock is None or self.clock.done(now):
                self._timer.stop()
                self.clock = None
                self.hide()
                return
            # Everything is drawn after ~(marks × STEP + DRAW_IN): then a calm
            # 30 Hz is plenty for the breathing arrows.
            busy = now - self.clock.start < len(self.marks) * STEP + DRAW_IN + 0.3
            interval = 16 if busy or self.clock.ending is not None else 33
            if self._timer.interval() != interval:
                self._timer.setInterval(interval)
            self.update()

        # -- painting -----------------------------------------------------------
        def paintEvent(self, _event: object) -> None:  # noqa: N802 (Qt API)
            if self.clock is None:
                return
            now = time.monotonic()
            t = now - self.clock.start
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setOpacity(self.clock.alpha(now))
            boxes = [i for i, m in enumerate(self.marks) if m.shape == "box"]
            if boxes:
                self._dim(p, boxes, min(1.0, t / DRAW_IN))
            stepping = self.clock.steps > 0
            for i, mark in enumerate(self.marks):
                if stepping:
                    if i > self.clock.current:
                        continue  # the next steps wait for their click
                    p.setOpacity(self.clock.alpha(now) * (1.0 if i == self.clock.current else 0.3))
                    local = now - self.clock.step_at if i == self.clock.current else 9.0
                else:
                    local = t - i * STEP * 0.6  # each mark a little after the last
                if local <= 0:
                    continue
                grow = ease(min(1.0, local / DRAW_IN))
                spot, (w, h) = self.points[i], self.sizes[i]
                if mark.shape == "circle":
                    self._circle(p, spot, w, h, grow)
                elif mark.shape == "box":
                    self._box(p, spot, w, h, grow)
                elif mark.shape == "underline":
                    self._underline(p, spot, w, h, grow)
                elif mark.shape == "line" and i + 1 < len(self.points):
                    self._line(p, spot, self.points[i + 1], grow)
                else:
                    self._arrow(p, mark, spot, w, h, grow, t, mark.depth)
                if mark.text and grow > 0.6:
                    self._label(p, spot, w, h, f"{i + 1}  {mark.text}" if len(self.marks) > 1 else mark.text)
            p.setOpacity(self.clock.alpha(now))
            if stepping:  # the cursor flies from the last step to this one
                k = self.clock.current
                start = self.points[k - 1] if k else self._from
                x, y, press = cursor_at([(self.points[k].x(), self.points[k].y())], (start.x(), start.y()),
                                        now - self.clock.step_at)
            else:
                x, y, press = cursor_at([(q.x(), q.y()) for q in self.points], (self._from.x(), self._from.y()), t)
            self._ghost(p, QPointF(x, y), press)
            if stepping:
                n, k = self.clock.steps, self.clock.current
                head = f"Paso {k + 1} de {n}"
                tail = self.marks[k].text or self.caption
                self._caption(p, f"{head}  ·  {tail}" if tail else head)
            elif self.caption:
                self._caption(p)
            p.end()

        def _pen(self, width: float, colour: QColor = accent) -> QPen:
            pen = QPen(colour, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            return pen

        def _halo(self, p: QPainter, path: QPainterPath, width: float) -> None:
            """A dark under-stroke so the blue reads on white and on black."""
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(self._pen(width + 4, QColor(0, 0, 0, 90)))
            p.drawPath(path)

        def _circle(self, p: QPainter, c: QPointF, w: float, h: float, grow: float) -> None:
            rx = max(26.0, w / 2 + 12)
            ry = max(20.0, h / 2 + 10)
            path = QPainterPath()
            # Hand-drawn: the ring overshoots its start a little and wobbles.
            steps = 64
            span = 2 * math.pi * 1.08 * grow
            for k in range(steps + 1):
                a = -2.2 + span * k / steps
                wob = 1.0 + 0.035 * math.sin(a * 3.0)
                point = QPointF(c.x() + math.cos(a) * rx * wob, c.y() + math.sin(a) * ry * wob)
                if k == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            self._halo(p, path, 4)
            p.setPen(self._pen(4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        def _box(self, p: QPainter, c: QPointF, w: float, h: float, grow: float) -> None:
            w, h = max(w, 40.0) + 12, max(h, 26.0) + 10
            rect = QRectF(c.x() - w / 2, c.y() - h / 2, w, h)
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            length = path.length()
            pen = self._pen(3.5)
            pen.setDashPattern([length * grow / 3.5, 10_000])  # draws itself around
            self._halo(p, path, 3.5)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        def _dim(self, p: QPainter, boxes: list[int], k: float) -> None:
            """The rest of the screen a little darker, the boxed things lit."""
            outside = QPainterPath()
            outside.addRect(QRectF(self.rect()))
            for i in boxes:
                c, (w, h) = self.points[i], self.sizes[i]
                w, h = max(w, 40.0) + 12, max(h, 26.0) + 10
                hole = QPainterPath()
                hole.addRoundedRect(QRectF(c.x() - w / 2, c.y() - h / 2, w, h), 10, 10)
                outside = outside.subtracted(hole)
            p.fillPath(outside, QColor(0, 0, 0, int(70 * k)))

        def _underline(self, p: QPainter, c: QPointF, w: float, h: float, grow: float) -> None:
            w = max(w, 60.0)
            y = c.y() + max(h, 18.0) / 2 + 5
            path = QPainterPath(QPointF(c.x() - w / 2, y))
            for k in range(1, 25):
                x = c.x() - w / 2 + w * grow * k / 24
                path.lineTo(QPointF(x, y + math.sin(k * 0.9) * 1.6))
            self._halo(p, path, 4)
            p.setPen(self._pen(4))
            p.drawPath(path)

        def _line(self, p: QPainter, a: QPointF, b: QPointF, grow: float) -> None:
            end = a + (b - a) * grow
            mid = (a + end) / 2 + QPointF(0, -min(80.0, abs(end.x() - a.x()) * 0.2))
            path = QPainterPath(a)
            path.quadTo(mid, end)
            pen = self._pen(3.5)
            pen.setDashPattern([2.2, 2.0])
            self._halo(p, path, 3.5)
            p.setPen(pen)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            p.drawEllipse(a, 5, 5)

        def _arrow(
            self, p: QPainter, mark: Mark, tip: QPointF, w: float, h: float, grow: float, t: float, depth: bool
        ) -> None:
            tail_x, tail_y = arrow_tail(
                Mark(tip.x(), tip.y(), w, h), self.width(), self.height()
            )
            tail = QPointF(tail_x, tail_y)
            gap = (max(w, h) / 2 + 6) if w and h else 8.0
            direction = tip - tail
            length = math.hypot(direction.x(), direction.y()) or 1.0
            u = QPointF(direction.x() / length, direction.y() / length)
            bob = math.sin(t * 5.0) * 5.0 if grow >= 1.0 else 0.0  # it nods at the spot
            point = tip - u * (gap - bob)
            start = point - u * (length - gap) * grow
            n = QPointF(-u.y(), u.x())
            shaft, head, head_len = 7.0, 15.0, 24.0
            neck = point - u * head_len
            body = QPolygonF(
                [
                    start + n * shaft / 2,
                    neck + n * shaft / 2,
                    neck + n * head,
                    point,
                    neck - n * head,
                    neck - n * shaft / 2,
                    start - n * shaft / 2,
                ]
            )
            if depth:
                # 3D: a soft shadow on the screen, then the arrow's side face
                # (an extrusion towards the light's opposite corner).
                shadow = body.translated(7, 9)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 70))
                p.drawPolygon(shadow)
                side = accent.darker(170)
                p.setBrush(side)
                for k in range(7, 0, -1):
                    p.drawPolygon(body.translated(k * 0.9, k * 1.0))
            p.setPen(QPen(QColor(255, 255, 255, 235), 2.0))
            p.setBrush(accent)
            p.drawPolygon(body)
            if depth:
                # A highlight along the top edge: the light comes from above-left.
                p.setPen(self._pen(1.6, QColor(255, 255, 255, 120)))
                p.drawLine(start + n * (shaft / 2 - 1.2), neck + n * (shaft / 2 - 1.2))

        def _label(self, p: QPainter, c: QPointF, w: float, h: float, text: str) -> None:
            font = QFont()
            font.setFamilies(["Segoe UI Variable Text", "SF Pro Text", "Segoe UI"])
            font.setPointSizeF(10.5)
            font.setWeight(QFont.Weight.DemiBold)
            metrics = QFontMetricsF(font)
            tw = metrics.horizontalAdvance(text) + 22
            th = metrics.height() + 12
            below = c.y() + max(h, 20.0) / 2 + 16
            y = below if below + th < self.height() - 8 else c.y() - max(h, 20.0) / 2 - 16 - th
            x = min(max(8.0, c.x() - tw / 2), self.width() - tw - 8)
            rect = QRectF(x, y, tw, th)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 60))
            p.drawRoundedRect(rect.translated(0, 2), th / 2, th / 2)
            p.setBrush(QColor(28, 28, 30, 238))
            p.drawRoundedRect(rect, th / 2, th / 2)
            p.setFont(font)
            p.setPen(ink)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        def _ghost(self, p: QPainter, at: QPointF, press: float) -> None:
            """A cursor-shaped pointer in blue: clearly not the user's own."""
            scale = 1.0 - 0.18 * press
            shape = QPolygonF(
                [QPointF(0, 0), QPointF(0, 22), QPointF(6, 17), QPointF(10, 26), QPointF(14, 24), QPointF(10, 15), QPointF(17, 15)]
            )
            p.save()
            p.translate(at)
            p.scale(scale, scale)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 80))
            p.drawPolygon(shape.translated(2, 3))
            p.setPen(QPen(ink, 1.6))
            p.setBrush(accent)
            p.drawPolygon(shape)
            p.restore()
            if press > 0:
                p.setPen(self._pen(2.5, QColor(10, 132, 255, int(200 * press))))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(at, 10 + 14 * (1 - press), 10 + 14 * (1 - press))

        def _caption(self, p: QPainter, words: str = "") -> None:
            font = QFont()
            font.setFamilies(["Segoe UI Variable Text", "SF Pro Text", "Segoe UI"])
            font.setPointSizeF(12)
            metrics = QFontMetricsF(font)
            text = metrics.elidedText(words or self.caption, Qt.TextElideMode.ElideRight, self.width() * 0.6)
            tw, th = metrics.horizontalAdvance(text) + 32, metrics.height() + 18
            # At the bottom, unless a mark is there: then at the top.
            low = any(q.y() > self.height() * 0.7 for q in self.points)
            y = 72 if low else self.height() - th - 72
            rect = QRectF((self.width() - tw) / 2, y, tw, th)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(28, 28, 30, 235))
            p.drawRoundedRect(rect, th / 2, th / 2)
            p.setFont(font)
            p.setPen(ink)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    return GuideOverlay()


__all__ = [
    "Clock",
    "MAX_MARKS",
    "Mark",
    "SHAPES",
    "arrow_tail",
    "cursor_at",
    "make_overlay",
    "marks_from",
    "understood",
]

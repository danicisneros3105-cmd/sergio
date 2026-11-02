"""Face ID's animation, the Apple way, with a little of Sergio in it.

* scan     — a ring of dashes turns like a comet around the face glyph, and
             the glyph's eyes glance left and right as if looking for you;
* success  — the dashes run together into one circle, the face winks at
             you (Sergio's touch) and the circle becomes a check that draws
             itself with a soft spring overshoot;
* fail     — the glyph shakes side to side like the iPhone's (a damped
             shake), with a sceptical eyebrow before settling.

Timing is pure functions of the time since the phase began, so it is
tested without a screen; ``paint`` draws it with QPainter in any rect.
"""

from __future__ import annotations

import math
import time

DASHES = 24
SCAN_SPEED = 0.85  # turns per second
JOIN = 0.28  # seconds: the dashes run together into a circle
WINK = (0.30, 0.52)  # seconds: the wink (eye closed in between)
CHECK = (0.52, 0.86)  # seconds: the check draws itself
SHAKE = 0.62  # seconds of the failure shake


def ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def spring_scale(t: float, start: float, response: float = 0.32, damping: float = 0.55) -> float:
    """1 → a soft overshoot → 1 (the check's pop), after *start* seconds."""
    if t <= start:
        return 1.0
    x = t - start
    omega = 2 * math.pi / response
    return 1.0 + 0.12 * math.exp(-damping * omega * x) * math.sin(omega * x)


def shake_offset(t: float, amplitude: float = 1.0) -> float:
    """The iPhone's 'no': a damped side-to-side shake (in units of *amplitude*)."""
    if t <= 0 or t >= SHAKE:
        return 0.0
    return amplitude * math.exp(-t * 5.5) * math.sin(2 * math.pi * 6.0 * t)


def join_fraction(t: float) -> float:
    """0 = separate dashes … 1 = one closed circle."""
    return ease_out(t / JOIN)


def check_fraction(t: float) -> float:
    return ease_out((t - CHECK[0]) / (CHECK[1] - CHECK[0]))


def winking(t: float) -> bool:
    return WINK[0] <= t <= WINK[1]


def glance(t: float) -> float:
    """Where the eyes look while scanning: −1 left … 1 right, with pauses."""
    phase = (t * 0.6) % 1.0
    if phase < 0.35:
        return 0.0
    if phase < 0.55:
        return -ease_out((phase - 0.35) / 0.2)
    if phase < 0.75:
        return -1.0 + 2 * ease_out((phase - 0.55) / 0.2)
    return 1.0 - ease_out((phase - 0.75) / 0.25)


class FaceIDGlyph:
    """One Visage moment: ``start('scan')`` then ``start('success')``/'fail'."""

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self.phase = "idle"
        self.since = clock()

    def start(self, phase: str) -> None:
        if phase not in ("idle", "scan", "success", "fail"):
            phase = "idle"
        self.phase = phase
        self.since = self.clock()

    def age(self) -> float:
        return self.clock() - self.since

    def finished(self) -> bool:
        """Success/fail have played out (the caller may hide the glyph)."""
        if self.phase == "success":
            return self.age() > CHECK[1] + 0.45
        if self.phase == "fail":
            return self.age() > SHAKE + 0.5
        return False

    # -- drawing -------------------------------------------------------------------
    def paint(self, p, rect, colour=None, success_colour=None) -> None:  # noqa: ANN001 (Qt)
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QPainterPath, QPen

        ink = QColor(colour or "#f5f5f7")
        good = QColor(success_colour or "#34c759")
        t = self.age()
        size = min(rect.width(), rect.height())
        cx = rect.center().x() + (shake_offset(t, size * 0.09) if self.phase == "fail" else 0.0)
        cy = rect.center().y()
        r = size * 0.42
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        width = max(1.6, size * 0.035)

        # The ring: rotating comet of dashes, joining into a circle on success.
        if self.phase in ("scan", "success"):
            join = join_fraction(t) if self.phase == "success" else 0.0
            if self.phase == "success" and t >= JOIN:
                pen = QPen(good, width * 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawEllipse(QPointF(cx, cy), r, r)
            else:
                turn = (t * SCAN_SPEED * 360.0) if self.phase == "scan" else 0.0
                for i in range(DASHES):
                    angle = turn + i * 360.0 / DASHES
                    trail = (i / DASHES) if self.phase == "scan" else 1.0
                    c = QColor(good if self.phase == "success" else ink)
                    c.setAlpha(int(255 * (0.18 + 0.82 * trail)))
                    pen = QPen(c, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                    p.setPen(pen)
                    span = 360.0 / DASHES * (0.45 + 0.55 * join)
                    box = QRectF(cx - r, cy - r, 2 * r, 2 * r)
                    p.drawArc(box, int(-angle * 16), int(-span * 16))

        # The face (brackets for idle/fail, a simple friendly face always).
        scale = spring_scale(t, CHECK[0]) if self.phase == "success" else 1.0
        f = r * 0.62 * scale
        if self.phase == "success" and t >= CHECK[0]:
            k = check_fraction(t)
            a = QPointF(cx - f * 0.55, cy + f * 0.02)
            b = QPointF(cx - f * 0.12, cy + f * 0.45)
            c = QPointF(cx + f * 0.62, cy - f * 0.42)
            path = QPainterPath(a)
            if k < 0.4:
                path.lineTo(a + (b - a) * (k / 0.4))
            else:
                path.lineTo(b)
                path.lineTo(b + (c - b) * ((k - 0.4) / 0.6))
            p.setPen(QPen(good, width * 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
            p.restore()
            return

        pen = QPen(ink, width * 1.15, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        if self.phase in ("idle", "fail"):
            # The four corner brackets of the familiar glyph.
            g = f * 1.15
            arm = g * 0.42
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                corner = QPointF(cx + sx * g, cy + sy * g)
                p.drawLine(corner, QPointF(corner.x() - sx * arm, corner.y()))
                p.drawLine(corner, QPointF(corner.x(), corner.y() - sy * arm))
        look = glance(t) * f * 0.12 if self.phase == "scan" else 0.0
        eye_y = cy - f * 0.28
        left, right = QPointF(cx - f * 0.34 + look, eye_y), QPointF(cx + f * 0.34 + look, eye_y)
        p.setPen(QPen(ink, width * 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPoint(left)
        if self.phase == "success" and winking(t):
            p.setPen(QPen(ink, width * 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(right.x() - f * 0.1, eye_y), QPointF(right.x() + f * 0.1, eye_y))
        else:
            p.drawPoint(right)
        p.setPen(QPen(ink, width * 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if self.phase == "fail":
            # sceptical: one eyebrow up, a flat mouth
            p.drawLine(QPointF(right.x() - f * 0.13, eye_y - f * 0.26), QPointF(right.x() + f * 0.13, eye_y - f * 0.34))
            p.drawLine(QPointF(cx - f * 0.22, cy + f * 0.32), QPointF(cx + f * 0.22, cy + f * 0.32))
        else:
            # nose and smile (wider while winking)
            p.drawLine(QPointF(cx + look * 0.5, cy - f * 0.12), QPointF(cx + look * 0.5 - f * 0.06, cy + f * 0.12))
            grin = 1.25 if self.phase == "success" else 1.0
            smile = QRectF(cx - f * 0.3 * grin, cy + f * 0.05, f * 0.6 * grin, f * 0.42)
            p.drawArc(smile, 200 * 16, 140 * 16)
        p.restore()


__all__ = [
    "FaceIDGlyph",
    "check_fraction",
    "glance",
    "join_fraction",
    "shake_offset",
    "spring_scale",
    "winking",
]

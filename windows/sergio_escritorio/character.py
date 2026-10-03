"""Sergio's character: a round face that blinks, looks at you and reacts.

Pure drawing (QPainter), shared by the notch and the cursor companion so
Sergio looks the same everywhere. Geometric on purpose: a soft sphere, two
eyes and, when talking, a mouth.

States: idle (blue, blinks, follows the pointer), listening (red, eyes wide,
pulse), thinking (amber, eyes up, orbiting dot), speaking (green, mouth
moves), acting (blue, focused eyes), paused (grey, eyes closed).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient

STATE_COLORS = {
    "idle": QColor(10, 108, 255),
    "listening": QColor(255, 69, 58),
    "thinking": QColor(255, 159, 10),
    "speaking": QColor(48, 209, 88),
    "acting": QColor(10, 108, 255),
    "paused": QColor(142, 142, 147),
}

BLINK_EVERY = 4.2  # seconds
BLINK_TIME = 0.14


def _blink(t: float) -> float:
    """Eye openness 0..1 with a quick blink every few seconds."""
    phase = t % BLINK_EVERY
    if phase > BLINK_TIME:
        return 1.0
    return abs(math.cos(math.pi * phase / BLINK_TIME))


def draw_character(
    p: QPainter,
    centre: QPointF,
    radius: float,
    state: str,
    t: float,
    look: QPointF | None = None,
) -> None:
    """Draw Sergio at *centre*. *look* is a direction (-1..1) for the eyes."""
    colour = STATE_COLORS.get(state, STATE_COLORS["idle"])
    look = look or QPointF(0, 0)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Halo for states that need attention.
    if state in ("listening", "speaking", "acting"):
        phase = (t * (1.3 if state == "listening" else 0.9)) % 1.0
        ring = QColor(colour)
        ring.setAlphaF(0.5 * (1 - phase))
        p.setPen(QPen(ring, max(1.5, radius * 0.12)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        grow = radius * (0.25 + 0.7 * phase)
        p.drawEllipse(centre, radius + grow, radius + grow)

    # Body: a lit sphere (highlight top-left, deeper tone bottom-right).
    breathe = 1.0 + (0.035 * math.sin(t * 1.7) if state == "idle" else 0.0)
    r = radius * breathe
    body = QRadialGradient(centre + QPointF(-r * 0.35, -r * 0.45), r * 1.5)
    body.setColorAt(0.0, colour.lighter(150))
    body.setColorAt(0.55, colour)
    body.setColorAt(1.0, colour.darker(135))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(body)
    p.drawEllipse(centre, r, r)
    # Rim light, like glass.
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 60), max(1.0, r * 0.06)))
    p.drawEllipse(centre, r * 0.94, r * 0.94)

    # Eyes.
    gaze = QPointF(look.x() * r * 0.14, look.y() * r * 0.12)
    if state == "thinking":
        gaze = QPointF(r * 0.12 * math.cos(t * 2), -r * 0.14)
    eye_dx, eye_y = r * 0.34, -r * 0.1
    eye_w, eye_h = r * 0.2, r * 0.3
    if state == "listening":
        eye_w, eye_h = r * 0.23, r * 0.36
    elif state == "acting":
        eye_h = r * 0.18  # focused
    openness = 0.08 if state == "paused" else _blink(t)
    if state == "speaking":
        openness = max(openness, 0.85)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 245))
    for side in (-1, 1):
        eye_centre = centre + QPointF(side * eye_dx, eye_y) + gaze
        h = max(eye_h * openness, r * 0.045)
        p.drawRoundedRect(
            QRectF(eye_centre.x() - eye_w / 2, eye_centre.y() - h / 2, eye_w, h),
            eye_w / 2,
            min(eye_w, h) / 2,
        )

    # Mouth while speaking: a soft pill that opens and closes.
    if state == "speaking":
        talk = 0.35 + 0.65 * abs(math.sin(t * 9.0) * math.sin(t * 3.7 + 1.0))
        mw, mh = r * 0.42, max(r * 0.08, r * 0.26 * talk)
        mc = centre + QPointF(gaze.x() * 0.5, r * 0.36)
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawRoundedRect(
            QRectF(mc.x() - mw / 2, mc.y() - mh / 2, mw, mh), mh / 2, mh / 2
        )
    elif state == "idle":
        # A small, calm smile.
        smile = QPen(QColor(255, 255, 255, 200), max(1.2, r * 0.09))
        smile.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(smile)
        p.setBrush(Qt.BrushStyle.NoBrush)
        box = QRectF(centre.x() - r * 0.22, centre.y() + r * 0.1, r * 0.44, r * 0.3)
        p.drawArc(box, -20 * 16, -140 * 16)

    # Thinking: a dot orbiting the head.
    if state == "thinking":
        angle = t * 3.2
        dot = centre + QPointF(math.cos(angle) * r * 1.35, math.sin(angle) * r * 1.35)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(colour.lighter(130))
        p.drawEllipse(dot, max(1.6, r * 0.13), max(1.6, r * 0.13))
    p.restore()


__all__ = ["STATE_COLORS", "draw_character"]

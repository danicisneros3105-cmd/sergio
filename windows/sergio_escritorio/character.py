"""Sergio's character: a living glass orb of flowing colour, with soft eyes.

Inspired by the voice orbs of current assistants (ChatGPT's fluid sphere,
Meta AI's iridescent ring): colour blobs drift inside a glass ball, the ball
breathes, swells with your voice while listening, swirls while thinking and
pulses while speaking. Two soft eyes blink so it still feels like someone.

Pure QPainter drawing, shared by the notch and the cursor companion.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

# Each state: three blob colours (deep, mid, bright) + a glow colour.
PALETTES = {
    "idle": ("#1b4dff", "#7b5cff", "#3fd6ff", "#4c7dff"),
    "listening": ("#ff3b6b", "#ff8a3d", "#ffd166", "#ff5a7a"),
    "thinking": ("#7b5cff", "#c86bff", "#4fc3ff", "#9b7bff"),
    "speaking": ("#0fbf8f", "#3fd6ff", "#b6ff7a", "#2fd6a0"),
    "acting": ("#1b4dff", "#00c2ff", "#7cf3ff", "#2f8bff"),
    "paused": ("#5b5b66", "#8a8a96", "#c4c4cc", "#7a7a86"),
}
# Kept for code that only needs one representative colour per state.
STATE_COLORS = {k: QColor(v[3]) for k, v in PALETTES.items()}

BLINK_EVERY = 4.6
BLINK_TIME = 0.16


def _blink(t: float) -> float:
    phase = t % BLINK_EVERY
    if phase > BLINK_TIME:
        return 1.0
    return abs(math.cos(math.pi * phase / BLINK_TIME))


def _alpha(colour: str, a: float) -> QColor:
    c = QColor(colour)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def draw_character(
    p: QPainter,
    centre: QPointF,
    radius: float,
    state: str,
    t: float,
    look: QPointF | None = None,
    level: float = 0.0,
    eyes: bool = True,
) -> None:
    """Draw Sergio at *centre*. *level* (0..1) is the live voice volume."""
    deep, mid, bright, glow = PALETTES.get(state, PALETTES["idle"])
    look = look or QPointF(0, 0)
    speed = {"thinking": 2.4, "listening": 1.6, "speaking": 1.4}.get(state, 0.6)
    if state == "speaking":
        level = max(level, 0.35 + 0.35 * abs(math.sin(t * 7.0) * math.sin(t * 2.3 + 1)))
    swell = 1.0 + 0.04 * math.sin(t * 1.6) + 0.16 * level
    r = radius * swell

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Outer glow (stronger with voice).
    halo = QRadialGradient(centre, r * 1.9)
    halo.setColorAt(0.45, _alpha(glow, 0.32 + 0.4 * level))
    halo.setColorAt(1.0, _alpha(glow, 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawEllipse(centre, r * 1.9, r * 1.9)

    # Glass ball: clip the flowing colour to a circle.
    ball = QPainterPath()
    ball.addEllipse(centre, r, r)
    p.setClipPath(ball)
    p.fillPath(ball, QColor(deep).darker(160))

    # Three soft blobs drifting on slow orbits (the "fluid").
    for i, colour in enumerate((deep, mid, bright)):
        angle = t * speed * (0.6 + 0.25 * i) + i * 2.1
        wobble = 0.35 + 0.12 * math.sin(t * (0.9 + i * 0.3) + i)
        pos = centre + QPointF(
            math.cos(angle) * r * wobble, math.sin(angle * 1.3) * r * wobble
        )
        size = r * (1.05 - 0.18 * i + 0.25 * level)
        blob = QRadialGradient(pos, size)
        blob.setColorAt(0.0, _alpha(colour, 0.95))
        blob.setColorAt(0.6, _alpha(colour, 0.45))
        blob.setColorAt(1.0, _alpha(colour, 0.0))
        p.setBrush(blob)
        p.drawEllipse(pos, size, size)

    # Thinking: an iridescent swirl sweeping around (Meta-style ring light).
    if state == "thinking":
        swirl = QConicalGradient(centre, -t * 140)
        swirl.setColorAt(0.0, _alpha(bright, 0.55))
        swirl.setColorAt(0.25, _alpha(mid, 0.0))
        swirl.setColorAt(0.5, _alpha(deep, 0.35))
        swirl.setColorAt(0.75, _alpha(bright, 0.0))
        swirl.setColorAt(1.0, _alpha(bright, 0.55))
        p.setBrush(swirl)
        p.drawEllipse(centre, r, r)

    # Glass: soft top highlight and a darker bottom edge for volume.
    shine = QRadialGradient(centre + QPointF(-r * 0.3, -r * 0.55), r * 0.9)
    shine.setColorAt(0.0, QColor(255, 255, 255, 120))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(shine)
    p.drawEllipse(centre, r, r)
    shade = QRadialGradient(centre + QPointF(0, r * 0.9), r * 1.1)
    shade.setColorAt(0.0, QColor(0, 0, 0, 70))
    shade.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setBrush(shade)
    p.drawEllipse(centre, r, r)
    p.setClipping(False)

    # Rim light.
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 70), max(0.8, r * 0.05)))
    p.drawEllipse(centre, r * 0.97, r * 0.97)

    # Soft eyes (hidden when tiny): blink, follow the pointer, close in pause.
    if eyes and radius >= 7:
        openness = 0.12 if state == "paused" else _blink(t)
        gaze = QPointF(look.x() * r * 0.12, look.y() * r * 0.1)
        if state == "thinking":
            gaze = QPointF(r * 0.1 * math.cos(t * 1.7), -r * 0.12)
        eye_w = r * 0.16
        eye_h = max(r * 0.05, r * (0.3 if state == "listening" else 0.26) * openness)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 235))
        for side in (-1, 1):
            c = centre + QPointF(side * r * 0.27, -r * 0.06) + gaze
            p.drawRoundedRect(
                QRectF(c.x() - eye_w / 2, c.y() - eye_h / 2, eye_w, eye_h),
                eye_w / 2,
                min(eye_w, eye_h) / 2,
            )
    p.restore()


__all__ = ["PALETTES", "STATE_COLORS", "draw_character"]

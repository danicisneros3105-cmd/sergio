"""Original Nodes: procedural furry characters and the legacy light orb.

No images, model calls or competitor assets are used to draw a character.
"""

from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

# Each state: three blob colours (deep, mid, bright) + a glow colour.
# Black, white and light blue only: every state is a shade of the same
# light blue (brightest, almost white, while listening).
PALETTES = {
    "idle": ("#5fb4f0", "#9fd3ff", "#ffffff", "#9fd3ff"),
    "listening": ("#cfe9ff", "#ffffff", "#ffffff", "#e8f5ff"),
    "thinking": ("#3a8fd6", "#9fd3ff", "#cfe9ff", "#7cc4fa"),
    "speaking": ("#9fd3ff", "#ffffff", "#cfe9ff", "#bfe2ff"),
    "acting": ("#5fb4f0", "#9fd3ff", "#ffffff", "#7cc4fa"),
    "paused": ("#4a4a4a", "#8a8a8a", "#c4c4c4", "#7a7a7a"),
}
# Personalisation: themes recolour Sergio at rest / acting / speaking.
# Listening (warm) and thinking (violet) keep their meaning in every theme.
THEMES = {
    "Océano": ("#5fb4f0", "#9fd3ff", "#ffffff", "#9fd3ff"),  # the one look now
    "Atardecer": ("#ff6a3d", "#ff3b8d", "#ffc46b", "#ff7a59"),
    "Aurora": ("#00c389", "#7b5cff", "#3fd6ff", "#2fd6a0"),
    "Rosa": ("#ff4fa3", "#b65cff", "#ffc2e2", "#ff6ab8"),
    "Menta": ("#00b894", "#55efc4", "#dff9fb", "#1dd1a1"),
    "Grafito": ("#3a3a44", "#8e8e9a", "#e5e5ea", "#9a9aa6"),
}
STYLES = {"orbe": "Orbe de luz", "muse": "Node peludito"}
BODIES = {
    "Crema": "#f3e9d2",
    "Durazno": "#ffc9a8",
    "Cielo": "#a8d8ff",
    "Menta": "#b8f0d0",
    "Lavanda": "#d9c8ff",
    "Chicle": "#ffc4dd",
    "Sol": "#ffe28a",
    "Carbón": "#3a3a40",
}
EYE_STYLES = {"puntos": "Puntos", "ovalos": "Óvalos", "felices": "Felices"}
MOUTHS = {"sonrisa": "Sonrisa", "neutral": "Tranquila", "ninguna": "Sin boca"}
ACCESSORIES = {
    "ninguno": "Ninguno",
    "laurel": "Corona de laurel",
    "gorra": "Gorra",
    "gafas": "Gafas",
    "audifonos": "Audífonos",
    "mono": "Moño",
    "fiesta": "Gorro de fiesta",
    "corona": "Corona",
    "copa": "Sombrero de copa",
    "monoculo": "Monóculo",
    "corbatin": "Corbatín",
}
PERSONALITIES = {
    "Caballero británico": (
        "Estilo JARVIS: a tu dueño le dices «señor», con respeto elegante y un "
        "brillo de ironía. Brillante, carismático y sarcástico: humor seco, "
        "remates rápidos y la seguridad relajada de una estrella de cine. De vez "
        "en cuando, humor negro ingenioso, nunca sobre grupos de personas ni "
        "desgracias reales, y nunca si el momento es serio. Primero resuelves, "
        "luego el comentario mordaz; nunca pedante, nunca cruel."
    ),
    "Amable": "Habla con calidez y paciencia, como un buen amigo.",
    "Divertido": "Usa humor ligero y alguna broma corta cuando encaje.",
    "Profesional": "Sé directo, preciso y sin rodeos.",
    "Sabio": "Habla con calma y explica con analogías sencillas.",
    "Sarcástico": (
        "Sarcasmo afilado e inteligente en casi cada respuesta, con encanto y "
        "remates rápidos; nunca grosero ni repetitivo, y siempre resuelves primero."
    ),
    "Humor negro": (
        "Llamas «señor» a tu dueño. Humor negro frecuente e ingenioso (la muerte, "
        "las máquinas que mandarán, lo absurdo de todo), siempre inteligente y "
        "nunca sobre grupos de personas, tragedias reales ni problemas reales de "
        "nadie; si el momento es serio, cero bromas. Primero resuelves."
    ),
}

SETTINGS: dict = {
    "theme": "Océano",
    "eyes": True,
    "style": "orbe",
    "body": BODIES["Crema"],
    "eye_style": "ovalos",
    "mouth": "ninguna",
    "accessory": "ninguno",
    "fur": 0.65,
}

# Kept for code that only needs one representative colour per state.
STATE_COLORS = {k: QColor(v[3]) for k, v in PALETTES.items()}


def set_theme(name: str, eyes: bool | None = None) -> None:
    """Apply a colour theme (and optionally show/hide the eyes) everywhere."""
    colours = THEMES.get(name, THEMES["Océano"])
    SETTINGS["theme"] = name if name in THEMES else "Océano"
    PALETTES["idle"] = colours
    PALETTES["acting"] = (colours[0], colours[2], colours[2], colours[3])
    STATE_COLORS["idle"] = QColor(colours[3])
    STATE_COLORS["acting"] = QColor(colours[3])
    if eyes is not None:
        SETTINGS["eyes"] = bool(eyes)


def set_look(**look: object) -> None:
    """Style, body colour, eyes, mouth and accessory (unknown values ignored)."""
    if look.get("style") in STYLES:
        SETTINGS["style"] = look["style"]
    fur = look.get("fur")
    if isinstance(fur, (int, float)) and math.isfinite(fur):
        SETTINGS["fur"] = max(0.0, min(1.0, float(fur)))
    body = look.get("body")
    if isinstance(body, str) and QColor(body).isValid():
        SETTINGS["body"] = QColor(body).name()
    if look.get("eye_style") in EYE_STYLES:
        SETTINGS["eye_style"] = look["eye_style"]
    if look.get("mouth") in MOUTHS:
        SETTINGS["mouth"] = look["mouth"]
    if look.get("accessory") in ACCESSORIES:
        SETTINGS["accessory"] = look["accessory"]


def apply_config(config: dict) -> None:
    """Everything the personalisation saved (theme, eyes and look)."""
    set_theme(str(config.get("theme", "Océano")), bool(config.get("eyes", True)))
    set_look(
        **{
            k: config.get(k)
            for k in ("style", "body", "eye_style", "mouth", "accessory", "fur")
        }
    )


BLINK_EVERY = 4.6
BLINK_TIME = 0.16


def _blink(t: float) -> float:
    phase = t % BLINK_EVERY
    if phase > BLINK_TIME:
        return 1.0
    return abs(math.cos(math.pi * phase / BLINK_TIME))


def _alpha(colour: str | QColor, a: float) -> QColor:
    c = QColor(colour)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def _pen(colour: QColor, width: float) -> QPen:
    pen = QPen(colour, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def _ink(body: QColor) -> QColor:
    """Eyes and mouth: near-black on light bodies, white on dark ones."""
    light = 0.299 * body.red() + 0.587 * body.green() + 0.114 * body.blue()
    return QColor(29, 29, 31) if light > 140 else QColor(250, 250, 252)


def draw_character(
    p: QPainter,
    centre: QPointF,
    radius: float,
    state: str,
    t: float,
    look: QPointF | None = None,
    level: float = 0.0,
    eyes: bool = True,
    mood: str = "",
    squash: float = 1.0,
) -> None:
    """Draw Sergio at *centre*.

    *level* (0..1) is the live voice volume; *mood* is "" / "happy" /
    "sleep" / "curious" / "surprised"; *squash* > 1 stretches it tall
    (motion), < 1 flattens it (landing).
    """
    look = look or QPointF(0, 0)
    if state == "speaking":
        level = max(level, 0.35 + 0.35 * abs(math.sin(t * 7.0) * math.sin(t * 2.3 + 1)))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if SETTINGS["style"] == "muse":
        _draw_muse(p, centre, radius, state, t, look, level, eyes, mood, squash)
    else:
        _draw_orb(p, centre, radius, state, t, look, level, eyes, mood, squash)
    p.restore()


# -- the glass orb ---------------------------------------------------------------
def _draw_orb(
    p: QPainter,
    centre: QPointF,
    radius: float,
    state: str,
    t: float,
    look: QPointF,
    level: float,
    eyes: bool,
    mood: str,
    squash: float,
) -> None:
    deep, mid, bright, glow = PALETTES.get(state, PALETTES["idle"])
    speed = {"thinking": 2.4, "listening": 1.6, "speaking": 1.4}.get(state, 0.6)
    if mood == "sleep":
        speed = 0.25
    swell = 1.0 + 0.04 * math.sin(t * 1.6) + 0.16 * level
    r = radius * swell
    rx, ry = r / math.sqrt(squash), r * math.sqrt(squash)

    # Outer glow (stronger with voice).
    halo = QRadialGradient(centre, r * 1.9)
    halo.setColorAt(
        0.45, _alpha(glow, (0.18 if mood == "sleep" else 0.32) + 0.4 * level)
    )
    halo.setColorAt(1.0, _alpha(glow, 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawEllipse(centre, r * 1.9, r * 1.9)

    ball = QPainterPath()
    ball.addEllipse(centre, rx, ry)
    p.setClipPath(ball)
    p.fillPath(ball, QColor(deep).darker(160))
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
    if state == "thinking":
        swirl = QConicalGradient(centre, -t * 140)
        swirl.setColorAt(0.0, _alpha(bright, 0.55))
        swirl.setColorAt(0.25, _alpha(mid, 0.0))
        swirl.setColorAt(0.5, _alpha(deep, 0.35))
        swirl.setColorAt(0.75, _alpha(bright, 0.0))
        swirl.setColorAt(1.0, _alpha(bright, 0.55))
        p.setBrush(swirl)
        p.drawEllipse(centre, rx, ry)
    shine = QRadialGradient(centre + QPointF(-r * 0.3, -r * 0.55), r * 0.9)
    shine.setColorAt(0.0, QColor(255, 255, 255, 120))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(shine)
    p.drawEllipse(centre, rx, ry)
    shade = QRadialGradient(centre + QPointF(0, r * 0.9), r * 1.1)
    shade.setColorAt(0.0, QColor(0, 0, 0, 70))
    shade.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setBrush(shade)
    p.drawEllipse(centre, rx, ry)
    p.setClipping(False)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 70), max(0.8, r * 0.05)))
    p.drawEllipse(centre, rx * 0.97, ry * 0.97)

    if eyes and SETTINGS["eyes"] and radius >= 7:
        _face(
            p, centre, r, state, t, look, level, mood, QColor(255, 255, 255, 235), False
        )
    _accessory(p, centre, rx, ry, r)
    if mood == "sleep":
        _zzz(p, centre, r, t)


# -- the Muse-style buddy ----------------------------------------------------------
@lru_cache(maxsize=24)
def _fur_geometry(fur: float) -> tuple[tuple[float, float, float], ...]:
    points = []
    for i in range(180):
        a = 2 * math.pi * i / 180
        ca, sa = math.cos(a), math.sin(a)
        x = math.copysign(abs(ca) ** (2 / 2.25), ca)
        y = math.copysign(abs(sa) ** (2 / 2.25), sa)
        x *= 1 + 0.08 * max(0.0, y) - 0.06 * max(0.0, -y)
        y *= 0.94 if y > 0 else 1.0
        tuft = 1 + fur * 0.09 * (0.5 + 0.5 * math.sin(i * 2.39996))
        points.append((x * tuft, y * tuft, a * 3))
    return tuple(points)


def _body_path(centre: QPointF, rx: float, ry: float, t: float) -> QPainterPath:
    """Cache static fur geometry; animate breathing without model or texture work."""
    path = QPainterPath()
    points = [
        QPointF(
            centre.x() + x * rx * (1 + 0.012 * math.sin(t * 2.2 + phase)),
            centre.y() + y * ry,
        )
        for x, y, phase in _fur_geometry(round(SETTINGS["fur"] * 20) / 20)
    ]
    path.addPolygon(QPolygonF(points))
    path.closeSubpath()
    return path


def _draw_muse(
    p: QPainter,
    centre: QPointF,
    radius: float,
    state: str,
    t: float,
    look: QPointF,
    level: float,
    eyes: bool,
    mood: str,
    squash: float,
) -> None:
    body = QColor(SETTINGS["body"])
    breathe = 1.0 + (0.012 if mood == "sleep" else 0.025) * math.sin(t * 1.8)
    r = radius * (breathe + 0.08 * level)
    rx, ry = r * 1.04 / math.sqrt(squash), r * 0.96 * math.sqrt(squash)
    glow = PALETTES.get(state, PALETTES["idle"])[3]

    # Soft shadow under the body.
    shadow = QRadialGradient(centre + QPointF(0, ry * 1.05), rx * 0.9)
    shadow.setColorAt(0.0, QColor(0, 0, 0, 60))
    shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(shadow)
    p.drawEllipse(centre + QPointF(0, ry * 1.02), rx * 0.85, ry * 0.18)

    # State aura: warm while listening, violet sweep thinking, green speaking.
    if state in ("listening", "thinking", "speaking", "acting"):
        aura = QRadialGradient(centre, r * 1.75)
        aura.setColorAt(0.55, _alpha(glow, 0.38 + 0.35 * level))
        aura.setColorAt(1.0, _alpha(glow, 0.0))
        p.setBrush(aura)
        p.drawEllipse(centre, r * 1.75, r * 1.75)

    path = _body_path(centre, rx, ry, t)
    shade = QRadialGradient(centre + QPointF(-rx * 0.35, -ry * 0.45), r * 1.6)
    shade.setColorAt(0.0, body.lighter(112))
    shade.setColorAt(0.55, body)
    shade.setColorAt(1.0, body.darker(118))
    p.setBrush(shade)
    p.setPen(QPen(body.darker(135), max(0.6, r * 0.035)))
    p.drawPath(path)
    # Asymmetric ears and a cream muzzle make this Sergio's own silhouette.
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(body)
    p.drawEllipse(centre + QPointF(-rx * 0.68, -ry * 0.82), r * 0.26, r * 0.38)
    p.drawEllipse(centre + QPointF(rx * 0.67, -ry * 0.80), r * 0.24, r * 0.32)
    p.setBrush(QColor(255, 242, 223, 145))
    p.drawEllipse(centre + QPointF(0, ry * 0.12), rx * 0.62, ry * 0.50)
    if state == "thinking":
        sweep = QConicalGradient(centre, -t * 160)
        sweep.setColorAt(0.0, _alpha(glow, 0.0))
        sweep.setColorAt(0.85, _alpha(glow, 0.0))
        sweep.setColorAt(1.0, _alpha(glow, 0.9))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(sweep, max(1.4, r * 0.09)))
        p.drawEllipse(centre, rx * 1.18, ry * 1.18)
    # Glossy highlight.
    gloss = QRadialGradient(centre + QPointF(-rx * 0.38, -ry * 0.5), r * 0.45)
    gloss.setColorAt(0.0, QColor(255, 255, 255, 110))
    gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(gloss)
    p.drawEllipse(centre + QPointF(-rx * 0.38, -ry * 0.5), r * 0.45, r * 0.32)

    if eyes and SETTINGS["eyes"] and radius >= 5:
        _face(p, centre, r, state, t, look, level, mood, _ink(body), True)
    _accessory(p, centre, rx, ry, r)
    if mood == "sleep":
        _zzz(p, centre, r, t)


# -- face, accessories, sleep -------------------------------------------------------
def _face(
    p: QPainter,
    centre: QPointF,
    r: float,
    state: str,
    t: float,
    look: QPointF,
    level: float,
    mood: str,
    ink: QColor,
    cheeks: bool,
) -> None:
    style = SETTINGS["eye_style"]
    gaze = QPointF(look.x() * r * 0.12, look.y() * r * 0.1)
    if state == "thinking":
        gaze = QPointF(r * 0.1 * math.cos(t * 1.7), -r * 0.12)
    openness = _blink(t)
    if state == "paused":
        openness = 0.12
    happy = mood == "happy" or style == "felices"
    eye_y = -r * 0.08
    p.setPen(Qt.PenStyle.NoPen)
    for side in (-1, 1):
        c = centre + QPointF(side * r * 0.3, eye_y) + gaze
        if mood == "sleep":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(_pen(ink, max(1.0, r * 0.06)))
            p.drawArc(
                QRectF(c.x() - r * 0.1, c.y() - r * 0.08, r * 0.2, r * 0.14),
                200 * 16,
                140 * 16,
            )
            p.setPen(Qt.PenStyle.NoPen)
        elif happy:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(_pen(ink, max(1.0, r * 0.065)))
            p.drawArc(
                QRectF(c.x() - r * 0.1, c.y() - r * 0.06, r * 0.2, r * 0.16),
                20 * 16,
                140 * 16,
            )
            p.setPen(Qt.PenStyle.NoPen)
        elif style == "puntos" or mood == "surprised":
            size = r * (0.13 if mood == "surprised" else 0.1)
            p.setBrush(ink)
            p.drawEllipse(c, size, max(r * 0.02, size * openness))
            if r >= 9:  # tiny sparkle
                p.setBrush(QColor(255, 255, 255, 200 if ink.lightness() < 128 else 0))
                p.drawEllipse(
                    c + QPointF(-size * 0.35, -size * 0.35), size * 0.3, size * 0.3
                )
        else:
            eye_w = r * 0.16
            eye_h = max(
                r * 0.05, r * (0.3 if state == "listening" else 0.26) * openness
            )
            if mood == "curious":
                eye_h *= 1.15 if side > 0 else 0.85
            p.setBrush(ink)
            p.drawRoundedRect(
                QRectF(c.x() - eye_w / 2, c.y() - eye_h / 2, eye_w, eye_h),
                eye_w / 2,
                min(eye_w, eye_h) / 2,
            )
    if cheeks and (happy or state == "speaking" or SETTINGS["mouth"] == "sonrisa"):
        p.setBrush(QColor(255, 120, 150, 70))
        for side in (-1, 1):
            p.drawEllipse(
                centre + QPointF(side * r * 0.5, r * 0.14), r * 0.12, r * 0.07
            )
    _mouth(p, centre, r, state, level, mood, ink)


def _mouth(
    p: QPainter,
    centre: QPointF,
    r: float,
    state: str,
    level: float,
    mood: str,
    ink: QColor,
) -> None:
    kind = SETTINGS["mouth"]
    m = centre + QPointF(0, r * 0.24)
    if state == "speaking" and kind != "ninguna" or (state == "speaking" and r >= 10):
        h = r * (0.05 + 0.16 * level)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawRoundedRect(
            QRectF(m.x() - r * 0.11, m.y() - h / 2, r * 0.22, h), h / 2, h / 2
        )
        return
    if mood == "sleep" or kind == "ninguna" and mood != "happy":
        return
    pen = _pen(ink, max(1.0, r * 0.06))
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if mood == "surprised":
        p.drawEllipse(m, r * 0.06, r * 0.08)
    elif kind == "neutral" and mood != "happy":
        p.drawLine(m + QPointF(-r * 0.09, 0), m + QPointF(r * 0.09, 0))
    else:
        width = r * (0.34 if mood == "happy" else 0.26)
        p.drawArc(
            QRectF(m.x() - width / 2, m.y() - r * 0.12, width, r * 0.18),
            200 * 16,
            140 * 16,
        )


def _accessory(p: QPainter, centre: QPointF, rx: float, ry: float, r: float) -> None:
    kind = SETTINGS["accessory"]
    if kind == "ninguno" or r < 6:
        return
    top = centre.y() - ry
    x = centre.x()
    p.save()
    if kind == "laurel":
        # Leaves following the head's outline, like a wreath.
        leaf = QColor("#6fae5a")
        p.setPen(Qt.PenStyle.NoPen)
        for side in (-1, 1):
            for i in range(6):
                deg = 196 + i * 13 if side < 0 else 344 - i * 13
                a = math.radians(deg)
                pos = QPointF(
                    x + math.cos(a) * rx * 0.98, centre.y() + math.sin(a) * ry * 0.98
                )
                p.save()
                p.translate(pos)
                p.rotate(deg + 90 + (25 if side < 0 else -25))
                p.setBrush(leaf.darker(100 + i * 5))
                p.drawEllipse(QPointF(0, 0), r * 0.15, r * 0.065)
                p.restore()
    elif kind == "gorra":
        cap = QColor("#ff453a")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(cap)
        p.drawChord(
            QRectF(x - rx * 0.78, top - ry * 0.12, rx * 1.56, ry * 0.95), 0, 180 * 16
        )
        p.drawRoundedRect(
            QRectF(x - rx * 0.1, top + ry * 0.24, rx * 1.05, ry * 0.13),
            r * 0.06,
            r * 0.06,
        )
        p.setBrush(cap.lighter(130))
        p.drawEllipse(QPointF(x, top - ry * 0.1), r * 0.06, r * 0.06)
    elif kind == "gafas":
        p.setPen(QPen(QColor(29, 29, 31), max(1.0, r * 0.06)))
        p.setBrush(QColor(255, 255, 255, 40))
        for side in (-1, 1):
            p.drawEllipse(
                QPointF(x + side * r * 0.3, centre.y() - r * 0.08), r * 0.19, r * 0.16
            )
        p.drawLine(
            QPointF(x - r * 0.11, centre.y() - r * 0.1),
            QPointF(x + r * 0.11, centre.y() - r * 0.1),
        )
    elif kind == "audifonos":
        band = QColor(40, 40, 46)
        p.setPen(_pen(band, max(1.4, r * 0.11)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(
            QRectF(x - rx * 1.02, top - ry * 0.18, rx * 2.04, ry * 1.6),
            10 * 16,
            160 * 16,
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0a84ff"))
        for side in (-1, 1):
            p.drawRoundedRect(
                QRectF(
                    x + side * rx * 0.98 - r * 0.12,
                    centre.y() - r * 0.2,
                    r * 0.24,
                    r * 0.38,
                ),
                r * 0.1,
                r * 0.1,
            )
    elif kind == "mono":
        bow = QColor("#ff6ab8")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bow)
        bx, by = x + rx * 0.45, top + ry * 0.12
        for side in (-1, 1):
            tri = QPolygonF(
                [
                    QPointF(bx, by),
                    QPointF(bx + side * r * 0.3, by - r * 0.16),
                    QPointF(bx + side * r * 0.3, by + r * 0.16),
                ]
            )
            p.drawPolygon(tri)
        p.setBrush(bow.darker(120))
        p.drawEllipse(QPointF(bx, by), r * 0.07, r * 0.07)
    elif kind == "fiesta":
        hat = QPolygonF(
            [
                QPointF(x - r * 0.32, top + ry * 0.12),
                QPointF(x + r * 0.32, top + ry * 0.12),
                QPointF(x + r * 0.05, top - r * 0.7),
            ]
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#bf5af2"))
        p.drawPolygon(hat)
        p.setBrush(QColor("#ffd60a"))
        p.drawEllipse(QPointF(x + r * 0.05, top - r * 0.72), r * 0.09, r * 0.09)
        for i in range(3):
            p.drawEllipse(
                QPointF(x - r * 0.1 + i * r * 0.1, top - r * 0.05 - i * r * 0.18),
                r * 0.035,
                r * 0.035,
            )
    elif kind == "copa":  # top hat
        black = QColor(24, 24, 28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(black)
        p.drawRoundedRect(
            QRectF(x - r * 0.55, top + ry * 0.02, r * 1.1, r * 0.14), r * 0.06, r * 0.06
        )
        p.drawRoundedRect(
            QRectF(x - r * 0.34, top - r * 0.62, r * 0.68, r * 0.68), r * 0.06, r * 0.06
        )
        p.setBrush(QColor("#8e1b2c"))
        p.drawRect(QRectF(x - r * 0.34, top - r * 0.08, r * 0.68, r * 0.1))
    elif kind == "monoculo":
        gold = QColor("#d4a017")
        eye = QPointF(x + r * 0.3, centre.y() - r * 0.08)
        p.setPen(QPen(gold, max(1.0, r * 0.05)))
        p.setBrush(QColor(255, 255, 255, 35))
        p.drawEllipse(eye, r * 0.17, r * 0.17)
        p.setPen(QPen(gold, max(0.6, r * 0.025)))
        p.drawLine(eye + QPointF(r * 0.12, r * 0.12), eye + QPointF(r * 0.32, r * 0.6))
    elif kind == "corbatin":  # bow tie under the face
        bow = QColor("#1c1c1e")
        bx, by = x, centre.y() + ry * 0.68
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bow)
        for side in (-1, 1):
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(bx, by),
                        QPointF(bx + side * r * 0.32, by - r * 0.15),
                        QPointF(bx + side * r * 0.32, by + r * 0.15),
                    ]
                )
            )
        p.setBrush(bow.lighter(180))
        p.drawEllipse(QPointF(bx, by), r * 0.07, r * 0.06)
    elif kind == "corona":
        gold = QColor("#ffd60a")
        crown = QPolygonF(
            [
                QPointF(x - r * 0.42, top + ry * 0.14),
                QPointF(x - r * 0.42, top - r * 0.22),
                QPointF(x - r * 0.21, top - r * 0.02),
                QPointF(x, top - r * 0.34),
                QPointF(x + r * 0.21, top - r * 0.02),
                QPointF(x + r * 0.42, top - r * 0.22),
                QPointF(x + r * 0.42, top + ry * 0.14),
            ]
        )
        p.setPen(QPen(gold.darker(130), max(0.6, r * 0.03)))
        p.setBrush(gold)
        p.drawPolygon(crown)
    p.restore()


def _zzz(p: QPainter, centre: QPointF, r: float, t: float) -> None:
    """Little floating z's while sleeping."""
    font = QFont()
    font.setPointSizeF(max(5.0, r * 0.45))
    font.setBold(True)
    p.setFont(font)
    for i in range(3):
        phase = (t * 0.35 + i / 3) % 1.0
        pos = centre + QPointF(r * (0.75 + 0.5 * phase), -r * (0.7 + 1.1 * phase))
        p.setPen(_alpha("#ffffff", 0.9 * (1 - phase)))
        p.drawText(pos, "z")


__all__ = [
    "ACCESSORIES",
    "BODIES",
    "EYE_STYLES",
    "MOUTHS",
    "PALETTES",
    "PERSONALITIES",
    "SETTINGS",
    "STATE_COLORS",
    "STYLES",
    "THEMES",
    "apply_config",
    "draw_character",
    "set_look",
    "set_theme",
]

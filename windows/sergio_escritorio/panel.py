"""Sergio's control center: what drops out of the notch when you click it.

Six sections and nothing more, in the user's language (idioma.py):

* Chat: talk or type to Sergio, the brain, the microphone, the last answer.
* Cowork: describe an outcome; Sergio plans and works, and asks here before
  anything delicate (approve or deny each waiting step).
* Agent Swarm: send a task to the background swarm, see what is running,
  open the agents.
* Health: health, sleep (Night Shift), the mental gym and its results, the
  counselling chair.
* Profile: who you are to Sergio (profile, goals, your face) and how Sergio
  looks and sounds.
* Configuration: the switches (wake word, screen control, camera…),
  multitasking, hiding the notch, language and country.

The look is Bang & Olufsen on graphite: black anodised glass, aluminium
hairlines and a light aluminium primary button, a serif for the titles.
Everything is native Qt; data comes from the local Sergio server.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sergio_escritorio.character import (
    ACCESSORIES,
    BODIES,
    EYE_STYLES,
    MOUTHS,
    PALETTES,
    PERSONALITIES,
    SETTINGS,
    STYLES,
    THEMES,
    apply_config,
    draw_character,
)
from sergio_escritorio import idioma
from sergio_escritorio.neural_voice import VOICES

WIDTH, HEIGHT = 468, 600
RADIUS = 30.0
FONTS = ["Segoe UI Variable Text", "SF Pro Text", "Segoe UI"]
SERIF = "'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, serif"
TEXT = "#efece6"  # warm paper white
SECONDARY = "#8f8b84"
CARD = "#111111"
LINE = "#2a2926"  # aluminium hairline
ALUMINIUM = "#cfcac0"
ACCENT = ALUMINIUM
SIZES = {"S": 7.0, "M": 9.0, "L": 12.0}
BRAINS = {
    "auto": "Auto",
    "rapido": "Rápido",
    "equilibrado": "Normal",
    "profundo": "Profundo",
}
RATES = {"-10%": "Lenta", "+0%": "Normal", "+15%": "Rápida"}

STYLE = f"""
QWidget {{ color: {TEXT}; font-family: 'Segoe UI Variable Text', 'Segoe UI';
           font-size: 13px; }}
QLabel#title {{ font-family: {SERIF}; font-size: 21px; font-weight: 400;
                letter-spacing: 0.3px; }}
QLabel#subtitle, QLabel#hint {{ color: {SECONDARY}; font-size: 12px; }}
QLabel#section {{ color: {SECONDARY}; font-size: 10px; font-weight: 600;
                  letter-spacing: 1.8px; }}
QLabel#heading {{ font-family: {SERIF}; font-size: 17px; }}
QLabel#answer {{ font-size: 13px; line-height: 140%; }}
QLabel#row {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px;
             padding: 9px 12px; }}
QLineEdit {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px;
             padding: 9px 14px; font-size: 13px;
             selection-background-color: #3a3833; }}
QLineEdit:focus {{ border: 1px solid {ALUMINIUM}; }}
QPushButton {{ background: transparent; border: 1px solid {LINE}; border-radius: 10px;
               padding: 8px 14px; font-weight: 500; letter-spacing: 0.3px; }}
QPushButton:hover {{ border: 1px solid #4a4843; background: #161616; }}
QPushButton#primary {{ background: {ALUMINIUM}; color: #0b0b0b; border: none; }}
QPushButton#primary:hover {{ background: #e2ddd3; }}
QPushButton#seg {{ background: transparent; color: {SECONDARY}; border: none;
                   border-radius: 0; padding: 7px 0 6px 0; font-weight: 500;
                   font-size: 11px; letter-spacing: 0.6px;
                   border-bottom: 1px solid transparent; }}
QPushButton#seg:checked {{ color: {TEXT}; border-bottom: 1px solid {ALUMINIUM}; }}
QWidget#segbar {{ background: {CARD}; border-radius: 14px; }}
QWidget#segbar QPushButton#seg {{ padding: 5px 10px; border-radius: 11px; }}
QComboBox {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px;
             padding: 6px 12px; }}
QComboBox QAbstractItemView {{ background: {CARD}; color: {TEXT};
             selection-background-color: #2a2926; border: 1px solid {LINE}; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px;
                     margin: 0 0 6px 0; padding: 9px 11px; }}
QListWidget::item:selected {{ border: 1px solid {ALUMINIUM}; color: {TEXT}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 3px; }}
QScrollBar:horizontal {{ height: 0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(FONTS)
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


@dataclass
class Toggle:
    label: str
    icon: str  # "wave" | "hand" | "camera" | "pointer" | "phone" | "brain"
    get: Callable[[], bool]
    set: Callable[[bool], None]


@dataclass
class PanelActions:
    """What the panel can do; the app fills these in."""

    talk: Callable[[], None] = lambda: None
    send: Callable[[str], None] = lambda _text: None
    toggles: list[Toggle] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    save_config: Callable[[dict], None] = lambda _cfg: None
    open_url: Callable[[str], None] = lambda _url: None
    server_url: str = "http://localhost:8000"
    http: httpx.Client | None = None
    status: Callable[[], str] = lambda: ""
    # Opens a part of Sergio (health, the gym, the agents…): (key, argument).
    open_section: Callable[[str, str], None] = lambda _key, _arg="": None
    # Agent Swarm: one line per task running now.
    swarm: Callable[[], list[str]] = lambda: []
    # The notch itself: multitasking on/off and hiding it.
    multitasking: Callable[[], bool] = lambda: False
    set_multitasking: Callable[[bool], None] = lambda _on: None
    hide_notch: Callable[[], None] = lambda: None


# -- small Apple-style controls ------------------------------------------------
class Switch(QAbstractButton):
    """iOS switch: green when on, a white knob that slides."""

    def __init__(self, checked: bool = False) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 28)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(46, 28)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QColor(ALUMINIUM) if self.isChecked() else QColor("#2f2e2b")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 46, 28), 14, 14)
        x = 20 if self.isChecked() else 2
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QRectF(x, 3, 24, 24))
        p.setBrush(QColor("#0b0b0b") if self.isChecked() else QColor(TEXT))
        p.drawEllipse(QRectF(x, 2, 24, 24))
        p.end()


def draw_icon(p: QPainter, kind: str, centre: QPointF, colour: QColor) -> None:
    """Minimal line icons in the spirit of SF Symbols."""
    pen = QPen(colour, 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    x, y = centre.x(), centre.y()
    if kind == "mic":
        p.drawRoundedRect(QRectF(x - 4, y - 9, 8, 13), 4, 4)
        p.drawArc(QRectF(x - 7.5, y - 6, 15, 14), 200 * 16, 140 * 16)
        p.drawLine(QPointF(x, y + 8), QPointF(x, y + 11))
    elif kind == "wave":
        for i, h in enumerate((5, 11, 16, 11, 5)):
            px = x - 10 + i * 5
            p.drawLine(QPointF(px, y - h / 2), QPointF(px, y + h / 2))
    elif kind == "camera":
        p.drawRoundedRect(QRectF(x - 10, y - 6, 14, 12), 3, 3)
        path = QPainterPath()
        path.moveTo(x + 5, y - 2)
        path.lineTo(x + 10, y - 5)
        path.lineTo(x + 10, y + 5)
        path.lineTo(x + 5, y + 2)
        p.drawPath(path)
    elif kind == "pointer":
        path = QPainterPath()
        path.moveTo(x - 6, y - 9)
        path.lineTo(x + 7, y + 2)
        path.lineTo(x + 1, y + 3)
        path.lineTo(x + 4, y + 9)
        path.lineTo(x + 1, y + 10)
        path.lineTo(x - 2, y + 4)
        path.lineTo(x - 6, y + 7)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "hand":  # screen control
        p.drawRoundedRect(QRectF(x - 11, y - 8, 22, 14), 3, 3)
        p.drawLine(QPointF(x - 5, y + 10), QPointF(x + 5, y + 10))
        p.drawLine(QPointF(x, y + 6), QPointF(x, y + 10))
    elif kind == "phone":  # a handset: talk like a call
        path = QPainterPath()
        path.moveTo(x - 8, y - 9)
        path.cubicTo(x - 11, y - 3, x - 6, y + 6, x + 3, y + 9)
        path.lineTo(x + 7, y + 6)
        path.lineTo(x + 3, y + 1)
        path.lineTo(x, y + 3)
        path.cubicTo(x - 3, y + 1, x - 5, y - 2, x - 5, y - 4)
        path.lineTo(x - 3, y - 7)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "brain":  # mental gym
        p.drawEllipse(QRectF(x - 10, y - 8, 11, 15))
        p.drawEllipse(QRectF(x - 1, y - 8, 11, 15))
        p.drawLine(QPointF(x - 5, y - 2), QPointF(x - 2, y + 1))
        p.drawLine(QPointF(x + 5, y - 2), QPointF(x + 2, y + 1))
    elif kind == "note":  # organizer: a sticky note
        p.drawRoundedRect(QRectF(x - 9, y - 9, 18, 18), 3, 3)
        p.drawLine(QPointF(x - 5, y - 3), QPointF(x + 5, y - 3))
        p.drawLine(QPointF(x - 5, y + 2), QPointF(x + 2, y + 2))
    elif kind == "target":  # goals
        p.drawEllipse(QPointF(x, y), 10, 10)
        p.drawEllipse(QPointF(x, y), 5.5, 5.5)
        p.drawEllipse(QPointF(x, y), 1.4, 1.4)
    elif kind == "heart":  # health
        path = QPainterPath()
        path.moveTo(x, y + 9)
        path.cubicTo(x - 14, y - 1, x - 7, y - 13, x, y - 5)
        path.cubicTo(x + 7, y - 13, x + 14, y - 1, x, y + 9)
        p.drawPath(path)
    elif kind == "chair":  # counselling: the lounge chair
        path = QPainterPath()
        path.moveTo(x - 9, y - 8)
        path.quadTo(x - 10, y + 3, x - 2, y + 3)
        path.lineTo(x + 9, y + 3)
        p.drawPath(path)
        p.drawLine(QPointF(x - 3, y + 3), QPointF(x - 5, y + 9))
        p.drawLine(QPointF(x + 6, y + 3), QPointF(x + 8, y + 9))
    elif kind == "chart":  # results
        for i, h in enumerate((6, 11, 16)):
            p.drawRoundedRect(QRectF(x - 9 + i * 7, y + 8 - h, 4.5, h), 1.5, 1.5)
    elif kind == "eye":  # Sergio sees
        path = QPainterPath()
        path.moveTo(x - 11, y)
        path.quadTo(x, y - 11, x + 11, y)
        path.quadTo(x, y + 11, x - 11, y)
        p.drawPath(path)
        p.drawEllipse(QPointF(x, y), 3.6, 3.6)
    elif kind == "cube":  # holograms / Blender
        p.drawPolygon([QPointF(x, y - 10), QPointF(x + 9, y - 5), QPointF(x, y), QPointF(x - 9, y - 5)])
        p.drawLine(QPointF(x - 9, y - 5), QPointF(x - 9, y + 5))
        p.drawLine(QPointF(x + 9, y - 5), QPointF(x + 9, y + 5))
        p.drawLine(QPointF(x, y), QPointF(x, y + 10))
        p.drawLine(QPointF(x - 9, y + 5), QPointF(x, y + 10))
        p.drawLine(QPointF(x + 9, y + 5), QPointF(x, y + 10))
    elif kind == "globe":
        p.drawEllipse(QPointF(x, y), 10, 10)
        p.drawEllipse(QRectF(x - 4.5, y - 10, 9, 20))
        p.drawLine(QPointF(x - 10, y), QPointF(x + 10, y))
    elif kind == "cctv":  # live cameras
        p.drawRoundedRect(QRectF(x - 10, y - 7, 15, 8), 2, 2)
        p.drawLine(QPointF(x + 5, y - 3), QPointF(x + 9, y - 1))
        p.drawLine(QPointF(x - 4, y + 1), QPointF(x - 4, y + 8))
        p.drawLine(QPointF(x - 8, y + 8), QPointF(x, y + 8))
    elif kind == "plane":
        path = QPainterPath()
        path.moveTo(x, y - 11)
        path.lineTo(x + 1.6, y - 3)
        path.lineTo(x + 10, y + 2)
        path.lineTo(x + 1.6, y + 1)
        path.lineTo(x + 1, y + 7)
        path.lineTo(x + 4, y + 10)
        path.lineTo(x - 4, y + 10)
        path.lineTo(x - 1, y + 7)
        path.lineTo(x - 1.6, y + 1)
        path.lineTo(x - 10, y + 2)
        path.lineTo(x - 1.6, y - 3)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "film":
        p.drawRoundedRect(QRectF(x - 10, y - 7, 20, 14), 2.5, 2.5)
        path = QPainterPath()
        path.moveTo(x - 2.5, y - 4)
        path.lineTo(x + 4, y)
        path.lineTo(x - 2.5, y + 4)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "doc":  # meeting notes
        p.drawRoundedRect(QRectF(x - 7, y - 10, 14, 20), 2.5, 2.5)
        for dy in (-4, 0, 4):
            p.drawLine(QPointF(x - 3.5, y + dy), QPointF(x + 3.5, y + dy))
    elif kind == "person":  # profile
        p.drawEllipse(QPointF(x, y - 4.5), 4.5, 4.5)
        p.drawArc(QRectF(x - 9, y + 2, 18, 14), 0, 180 * 16)
    elif kind == "face":
        p.drawRoundedRect(QRectF(x - 9, y - 10, 18, 20), 9, 9)
        p.drawPoint(QPointF(x - 3.5, y - 2))
        p.drawPoint(QPointF(x + 3.5, y - 2))
        p.drawArc(QRectF(x - 4, y + 1, 8, 5), 200 * 16, 140 * 16)
    elif kind == "shield":  # blocking
        path = QPainterPath()
        path.moveTo(x, y - 10)
        path.lineTo(x + 8, y - 6)
        path.quadTo(x + 8, y + 6, x, y + 10)
        path.quadTo(x - 8, y + 6, x - 8, y - 6)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(x - 3.5, y), QPointF(x + 3.5, y))
    elif kind == "moon":  # Night Shift: a crescent
        path = QPainterPath()
        path.addEllipse(QPointF(x, y), 9, 9)
        bite = QPainterPath()
        bite.addEllipse(QPointF(x + 5, y - 4), 8, 8)
        p.drawPath(path.subtracted(bite))
    elif kind == "lock":
        p.drawRoundedRect(QRectF(x - 7, y - 1, 14, 10), 2.5, 2.5)
        p.drawArc(QRectF(x - 4.5, y - 9, 9, 13), 0, 180 * 16)
    elif kind == "gear":
        p.drawEllipse(QPointF(x, y), 3.5, 3.5)
        p.drawEllipse(QPointF(x, y), 8, 8)
    elif kind == "send":
        p.drawLine(QPointF(x, y + 7), QPointF(x, y - 7))
        p.drawLine(QPointF(x - 6, y - 1), QPointF(x, y - 7))
        p.drawLine(QPointF(x + 6, y - 1), QPointF(x, y - 7))


class Tile(QAbstractButton):
    """Control Center tile: dark when off, bright when on."""

    def __init__(self, toggle: Toggle) -> None:
        super().__init__()
        self.toggle = toggle
        self.setCheckable(True)
        self.setChecked(bool(toggle.get()))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)
        self.toggled.connect(lambda on: self.toggle.set(on))

    def sync(self) -> None:
        self.blockSignals(True)
        self.setChecked(bool(self.toggle.get()))
        self.blockSignals(False)
        self.update()

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # On: an aluminium hairline and a lit ring; off: just graphite.
        p.setPen(QPen(QColor(ALUMINIUM if on else LINE), 1.0))
        p.setBrush(QColor("#151515" if on else CARD))
        p.drawRoundedRect(rect, 12, 12)
        bubble = QPointF(30, rect.center().y())
        p.setPen(QPen(QColor(ALUMINIUM if on else "#4a4843"), 1.0))
        p.setBrush(QColor(ALUMINIUM) if on else Qt.BrushStyle.NoBrush)
        p.drawEllipse(bubble, 16, 16)
        draw_icon(p, self.toggle.icon, bubble, QColor("#0b0b0b" if on else SECONDARY))
        p.setPen(QColor(TEXT))
        p.setFont(_font(9.5, QFont.Weight.DemiBold))
        p.drawText(QPointF(56, rect.center().y() - 2), self.toggle.label)
        p.setPen(QColor(SECONDARY))
        p.setFont(_font(8.5))
        p.drawText(QPointF(56, rect.center().y() + 14), "Activado" if on else "Apagado")
        p.end()


SECTION_ICONS = {  # the «Todo» tab, in order: (icon, bubble colour)
    "agents": ("person", "#0a84ff"),
    "organizer": ("note", "#ff9f0a"),
    "goals": ("target", "#30d158"),
    "health": ("heart", "#ff375f"),
    "consult": ("chair", "#c9a27e"),
    "gym": ("brain", "#bf5af2"),
    "results": ("chart", "#5e5ce6"),
    "camera": ("eye", "#64d2ff"),
    "holo": ("cube", "#5ac8fa"),
    "blender": ("cube", "#ff9500"),
    "video": ("film", "#ff2d55"),
    "meeting": ("doc", "#8e8e93"),
    "profile": ("person", "#32ade6"),
    "faces": ("face", "#34c759"),
    "blocking": ("shield", "#ff6961"),
    "night": ("moon", "#5e5ce6"),
    "lock": ("lock", "#636366"),
}


def all_territories() -> list[tuple[str, str]]:
    """Every country and territory Qt knows (ISO code, name), by name."""
    from PySide6.QtCore import QLocale

    found: dict[str, str] = {}
    kinds = QLocale.Country
    for attr in dir(kinds):
        value = getattr(kinds, attr)
        if not isinstance(value, kinds):
            continue
        code = QLocale.territoryToCode(value)
        if len(code) == 2 and code.isalpha() and code not in ("ZZ",):
            found[code] = QLocale.territoryToString(value)
    return sorted(found.items(), key=lambda kv: kv[1])


class SectionTile(QAbstractButton):
    """One part of Sergio in the «Todo» grid: a coloured icon and its name."""

    def __init__(self, key: str, label: str) -> None:
        super().__init__()
        self.key, self.label = key, label
        self.icon_kind, self.colour = SECTION_ICONS.get(key, ("gear", ACCENT))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(78)
        self.setToolTip(label)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        hot = self.isDown() or self.underMouse()
        p.setPen(QPen(QColor(ALUMINIUM if hot else LINE), 1.0))
        p.setBrush(QColor("#161616" if hot else CARD))
        p.drawRoundedRect(rect, 12, 12)
        bubble = QPointF(rect.center().x(), rect.top() + 28)
        p.setPen(QPen(QColor(ALUMINIUM), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(bubble, 16, 16)
        draw_icon(p, self.icon_kind, bubble, QColor(TEXT))
        p.setPen(QColor(TEXT))
        p.setFont(_font(8.6, QFont.Weight.DemiBold))
        p.drawText(
            QRectF(rect.left() + 4, rect.top() + 50, rect.width() - 8, 22),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            self.label,
        )
        p.end()

    def enterEvent(self, _event: Any) -> None:  # noqa: N802
        self.update()

    def leaveEvent(self, _event: Any) -> None:  # noqa: N802
        self.update()


class Orb(QWidget):
    """A live Sergio for the header and the personalisation tab."""

    def __init__(self, radius: float, state: Callable[[], str] = lambda: "idle"):
        super().__init__()
        self.radius = radius
        self.state = state
        side = int(radius * 4.2)  # room for the glow
        self.setFixedSize(side, side)
        self._t0 = time.monotonic()
        timer = QTimer(self)
        timer.timeout.connect(self.update)
        timer.start(16)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        centre = QPointF(self.width() / 2, self.height() / 2)
        draw_character(
            p, centre, self.radius, self.state(), time.monotonic() - self._t0
        )
        p.end()


class Swatch(QAbstractButton):
    """A round colour choice (one per theme), ringed when selected."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.setCheckable(True)
        self.setToolTip(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(38, 38)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        deep, mid, bright, _glow = THEMES[self.name]
        centre = QPointF(19, 19)
        grad = QRadialGradient(QPointF(14, 13), 20)
        grad.setColorAt(0.0, QColor(bright))
        grad.setColorAt(0.55, QColor(mid))
        grad.setColorAt(1.0, QColor(deep))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(centre, 13, 13)
        if self.isChecked():
            p.setPen(QPen(QColor(TEXT), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(centre, 17, 17)
        p.end()


class ColorDot(QAbstractButton):
    """A flat round colour (body colours), ringed when selected; "+" = custom."""

    def __init__(self, colour: str, tip: str, plus: bool = False) -> None:
        super().__init__()
        self.colour = colour
        self.plus = plus
        self.setCheckable(not plus)
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(34, 34)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        centre = QPointF(17, 17)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        if self.plus:
            p.setBrush(QColor("#2c2c2e"))
            p.drawEllipse(centre, 12, 12)
            p.setPen(QPen(QColor(TEXT), 1.8))
            p.drawLine(QPointF(17, 11), QPointF(17, 23))
            p.drawLine(QPointF(11, 17), QPointF(23, 17))
        else:
            p.setBrush(QColor(self.colour))
            p.drawEllipse(centre, 12, 12)
        if self.isChecked():
            p.setPen(QPen(QColor(TEXT), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(centre, 15.5, 15.5)
        p.end()


class LookChip(QAbstractButton):
    """A mini Sergio wearing one accessory (Muse-style picker)."""

    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key
        self.setCheckable(True)
        self.setToolTip(ACCESSORIES[key])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 44)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, 42, 42)
        p.setPen(QPen(QColor(TEXT), 2) if self.isChecked() else Qt.PenStyle.NoPen)
        p.setBrush(QColor(CARD))
        p.drawRoundedRect(rect, 14, 14)
        saved = SETTINGS["accessory"]
        SETTINGS["accessory"] = self.key
        draw_character(p, QPointF(22, 25), 10, "idle", 1.0)
        SETTINGS["accessory"] = saved
        p.end()


class Segmented(QWidget):
    """Apple segmented control for a few named options."""

    def __init__(
        self, options: dict[str, str], current: str, on_change: Callable[[str], None]
    ) -> None:
        super().__init__()
        self.setObjectName("segbar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for key, label in options.items():
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(key == current)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: on_change(k))
            self.group.addButton(b)
            self.buttons[key] = b
            row.addWidget(b)

    def select(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)


class LevelBar(QWidget):
    """Live microphone level, so you can see that Sergio hears you."""

    def __init__(self) -> None:
        super().__init__()
        self.level = 0.0
        self.setFixedHeight(6)

    def set_level(self, level: float) -> None:
        self.level = self.level * 0.6 + max(0.0, min(1.0, level)) * 0.4
        self.update()

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2c2c2e"))
        p.drawRoundedRect(rect, 3, 3)
        p.setBrush(QColor("#30d158") if self.level > 0.25 else QColor("#8e8e93"))
        p.drawRoundedRect(QRectF(0, 0, rect.width() * self.level, rect.height()), 3, 3)
        p.end()


def _row(label: str, widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(_label(label), 1)
    row.addWidget(widget)
    return row


def _label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    # Section names in small capitals, letter-spaced (Qt has no text-transform).
    label = QLabel(text.upper() if name == "section" else text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


# -- the panel -----------------------------------------------------------------
class ControlCenter(QWidget):
    cowork_ready = Signal(dict)

    TABS = ("tab_chat", "tab_cowork", "tab_swarm", "tab_health", "tab_profile", "tab_settings")
    CHAT, COWORK, SWARM, HEALTH, PROFILE, SETTINGS_TAB = range(6)
    HEALTH_SECTIONS = ("health", "night", "gym", "results", "consult")
    PROFILE_SECTIONS = ("profile", "goals", "faces")

    def __init__(self, actions: PanelActions) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.setFixedSize(WIDTH, HEIGHT)
        self.actions = actions
        self.lang = str(actions.config.get("language") or idioma.system_language())
        self.state = "idle"
        self._opened_at = 0.0
        self._runs: dict[str, dict] = {}
        self.cowork_ready.connect(self._show_cowork)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 20)
        root.setSpacing(14)
        root.addLayout(self._header())
        root.addWidget(self._segmented())
        self.pages = QStackedWidget()
        apply_config(self.actions.config)
        self.pages.addWidget(self._chat())
        self.pages.addWidget(self._cowork())
        self.pages.addWidget(self._swarm())
        self.pages.addWidget(self._sections_page(self.HEALTH_SECTIONS, "health_hint"))
        self.pages.addWidget(self._profile())
        self.pages.addWidget(self._settings())
        root.addWidget(self.pages, 1)
        self._swarm_timer = QTimer(self)
        self._swarm_timer.timeout.connect(self._refresh_swarm)
        self._swarm_timer.start(1000)

    # -- building blocks -------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(Orb(10, lambda: self.state))
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.title = _label("Sergio", "title")
        texts.addWidget(self.title)
        self.subtitle = _label("", "subtitle")
        texts.addWidget(self.subtitle)
        row.addLayout(texts, 1)
        close = QPushButton("×")
        close.setFixedSize(30, 30)
        close.setStyleSheet("border-radius: 15px; padding: 0; font-size: 13px;")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        row.addWidget(close)
        return row

    def _segmented(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"border-bottom: 1px solid {LINE};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.tab_group = QButtonGroup(self)
        for i, key in enumerate(self.TABS):
            button = QPushButton(idioma.t(key, self.lang))
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tab_group.addButton(button, i)
            row.addWidget(button)
        self.tab_group.button(0).setChecked(True)
        self.tab_group.idClicked.connect(self.show_tab)
        return bar

    def _chat(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        ask = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText(idioma.t("type_here", self.lang))
        self.entry.returnPressed.connect(self._send)
        ask.addWidget(self.entry, 1)
        talk = QPushButton(idioma.t("talk", self.lang))
        talk.setObjectName("primary")
        talk.setCursor(Qt.CursorShape.PointingHandCursor)
        talk.clicked.connect(self._talk)
        ask.addWidget(talk)
        col.addLayout(ask)
        self.brain = Segmented(
            BRAINS,
            str(self.actions.config.get("effort", "auto")),
            lambda k: self._save(effort=k),
        )
        col.addLayout(_row(idioma.t("brain", self.lang), self.brain))
        mic = QHBoxLayout()
        mic.addWidget(_label(idioma.t("mic", self.lang), "hint"))
        self.mic = LevelBar()
        mic.addWidget(self.mic, 1)
        col.addLayout(mic)
        col.addWidget(_label(idioma.t("last_answer", self.lang), "section"))
        self.answer = _label(idioma.t("ask_me", self.lang), "answer", True)
        self.answer.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.answer)
        col.addWidget(scroll, 1)
        return page

    def _cowork(self) -> QWidget:
        """Describe the outcome; approve or deny what Sergio asks about."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        col.addWidget(_label(idioma.t("cowork_hint", self.lang), "hint", True))
        row = QHBoxLayout()
        self.goal = QLineEdit()
        self.goal.setPlaceholderText(idioma.t("cowork_goal", self.lang))
        self.goal.returnPressed.connect(self._start_cowork)
        row.addWidget(self.goal, 1)
        start = QPushButton(idioma.t("start", self.lang))
        start.setObjectName("primary")
        start.setCursor(Qt.CursorShape.PointingHandCursor)
        start.clicked.connect(self._start_cowork)
        row.addWidget(start)
        col.addLayout(row)
        self.cowork_note = _label("", "hint", True)
        col.addWidget(self.cowork_note)
        self.run_list = QListWidget()
        self.run_list.currentItemChanged.connect(lambda _now, _before: self._pick_run())
        col.addWidget(self.run_list, 1)
        self.waiting = _label("", "answer", True)
        col.addWidget(self.waiting)
        decide = QHBoxLayout()
        self.approve = QPushButton(idioma.t("approve", self.lang))
        self.approve.setObjectName("primary")
        self.approve.clicked.connect(lambda: self._decide(True))
        self.deny = QPushButton(idioma.t("deny", self.lang))
        self.deny.clicked.connect(lambda: self._decide(False))
        for button in (self.approve, self.deny):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setVisible(False)
            decide.addWidget(button)
        col.addLayout(decide)
        return page

    def _swarm(self) -> QWidget:
        """Background tasks and the agent swarm."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        col.addWidget(_label(idioma.t("swarm_hint", self.lang), "hint", True))
        row = QHBoxLayout()
        self.swarm_entry = QLineEdit()
        self.swarm_entry.setPlaceholderText(idioma.t("swarm_task", self.lang))
        self.swarm_entry.returnPressed.connect(self._launch_swarm)
        row.addWidget(self.swarm_entry, 1)
        launch = QPushButton(idioma.t("launch", self.lang))
        launch.setObjectName("primary")
        launch.setCursor(Qt.CursorShape.PointingHandCursor)
        launch.clicked.connect(self._launch_swarm)
        row.addWidget(launch)
        col.addLayout(row)
        col.addWidget(_label(idioma.t("running_now", self.lang), "section"))
        self.swarm_list = QListWidget()
        col.addWidget(self.swarm_list, 1)
        buttons = QHBoxLayout()
        agents = QPushButton(idioma.t("agents", self.lang))
        agents.clicked.connect(lambda: self._open_section("agents"))
        cancel = QPushButton(idioma.t("cancel_last", self.lang))
        cancel.clicked.connect(lambda: self.actions.send("cancela la tarea"))
        for button in (agents, cancel):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        col.addLayout(buttons)
        return page

    def _sections_page(self, keys: tuple[str, ...], hint: str) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        col.addWidget(_label(idioma.t(hint, self.lang), "hint", True))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, key in enumerate(keys):
            tile = SectionTile(key, idioma.t(key, self.lang))
            tile.clicked.connect(lambda _c=False, k=key: self._open_section(k))
            grid.addWidget(tile, i // 3, i % 3)
        col.addLayout(grid)
        col.addStretch(1)
        return page

    def _profile(self) -> QWidget:
        """Who you are to Sergio, and how Sergio looks and sounds."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, key in enumerate(self.PROFILE_SECTIONS):
            tile = SectionTile(key, idioma.t(key, self.lang))
            tile.clicked.connect(lambda _c=False, k=key: self._open_section(k))
            grid.addWidget(tile, 0, i)
        col.addLayout(grid)
        col.addWidget(_label(idioma.t("tab_sergio", self.lang), "heading"))
        col.addWidget(self._personalise(), 1)
        return page

    def _open_section(self, key: str, arg: str = "") -> None:
        self.hide()
        self.actions.open_section(key, arg)

    # -- cowork ----------------------------------------------------------------
    def _start_cowork(self) -> None:
        goal = self.goal.text().strip()
        if not goal:
            return
        self.goal.clear()
        self.cowork_note.setText(idioma.t("planning", self.lang))
        base = self.actions.server_url

        def job() -> dict:
            resp = self._http().post(f"{base}/v1/cowork", json={"goal": goal})
            resp.raise_for_status()
            return {"runs": self._http().get(f"{base}/v1/cowork").json().get("runs", [])}

        self._background(job, self.cowork_ready)

    def _load_cowork(self) -> None:
        base = self.actions.server_url

        def job() -> dict:
            return self._http().get(f"{base}/v1/cowork").json()

        self._background(job, self.cowork_ready)

    def _show_cowork(self, data: dict) -> None:
        if data.get("error"):
            self.cowork_note.setText(idioma.t("no_server", self.lang))
            return
        runs = data.get("runs", [])
        self.cowork_note.setText("" if runs else idioma.t("no_runs", self.lang))
        chosen = self.run_list.currentItem()
        keep = chosen.data(Qt.ItemDataRole.UserRole) if chosen else None
        self.run_list.clear()
        self._runs = {r["id"]: r for r in runs}
        for run in runs:
            done = int(round(float(run.get("progress", 0)) * 100))
            mark = " · " + idioma.t("needs_you", self.lang) if run.get("waiting") else ""
            item = QListWidgetItem(
                f"{run.get('title') or run.get('goal', '')}\n{run.get('status', '')} · {done}%{mark}"
            )
            item.setData(Qt.ItemDataRole.UserRole, run["id"])
            self.run_list.addItem(item)
            if run["id"] == keep or (keep is None and run.get("waiting")):
                self.run_list.setCurrentItem(item)
        self._pick_run()

    def _current_run(self) -> dict | None:
        item = self.run_list.currentItem()
        return self._runs.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _pick_run(self) -> None:
        run = self._current_run()
        waiting = (run or {}).get("waiting") or []
        if waiting:
            step = run["steps"][waiting[0]]
            self.waiting.setText(
                f"{idioma.t('step', self.lang)} {waiting[0] + 1}: {step.get('text', '')}"
            )
        else:
            self.waiting.setText("")
        for button in (self.approve, self.deny):
            button.setVisible(bool(waiting))

    def _decide(self, approve: bool) -> None:
        run = self._current_run()
        if not run or not run.get("waiting"):
            return
        base, step = self.actions.server_url, run["waiting"][0] + 1

        def job() -> dict:
            self._http().post(
                f"{base}/v1/cowork/{run['id']}/decision",
                json={"step": step, "approve": approve},
            ).raise_for_status()
            return self._http().get(f"{base}/v1/cowork").json()

        self._background(job, self.cowork_ready)

    # -- agent swarm -----------------------------------------------------------
    def _launch_swarm(self) -> None:
        text = self.swarm_entry.text().strip()
        if not text:
            return
        self.swarm_entry.clear()
        self.actions.send(f"en segundo plano, {text}")

    def _refresh_swarm(self) -> None:
        if not self.isVisible() or self.pages.currentIndex() != self.SWARM:
            return
        lines = self.actions.swarm() or [idioma.t("nothing_running", self.lang)]
        if [self.swarm_list.item(i).text() for i in range(self.swarm_list.count())] != lines:
            self.swarm_list.clear()
            self.swarm_list.addItems(lines)

    def _settings(self) -> QWidget:
        """The switches, the notch, language and country."""
        cfg = self.actions.config
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 14, 0)
        col.setSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.tiles = [Tile(t) for t in self.actions.toggles]
        for i, tile in enumerate(self.tiles):
            grid.addWidget(tile, i // 2, i % 2)
        col.addLayout(grid)
        col.addWidget(_label("NOTCH", "section"))
        self.multi_switch = Switch(self.actions.multitasking())
        self.multi_switch.toggled.connect(self.actions.set_multitasking)
        col.addLayout(_row(idioma.t("multitasking", self.lang), self.multi_switch))
        hide = QPushButton(idioma.t("hide_notch", self.lang))
        hide.setCursor(Qt.CursorShape.PointingHandCursor)
        hide.clicked.connect(lambda: (self.hide(), self.actions.hide_notch()))
        col.addWidget(hide)
        col.addWidget(_label(idioma.t("settings_hint", self.lang), "hint", True))
        self.language_box = QComboBox()
        for code, name in idioma.LANGUAGES.items():
            self.language_box.addItem(name, code)
        self.language_box.setCurrentIndex(max(0, self.language_box.findData(self.lang)))
        self.language_box.currentIndexChanged.connect(
            lambda _i: self._save(language=self.language_box.currentData())
        )
        col.addLayout(_row(idioma.t("language", self.lang), self.language_box))
        self.country_box = QComboBox()
        self.country_box.setMaxVisibleItems(16)
        for code, c in sorted(idioma.COUNTRIES.items(), key=lambda kv: kv[1].name):
            self.country_box.addItem(c.name, code)  # crisis lines checked one by one
        self.country_box.insertSeparator(self.country_box.count())
        for code, name in all_territories():  # every other country and territory
            if code not in idioma.COUNTRIES:
                self.country_box.addItem(name, code)
        here = str(cfg.get("country") or idioma.system_country() or "EC")
        self.country_box.setCurrentIndex(max(0, self.country_box.findData(here)))
        self.country_box.currentIndexChanged.connect(self._pick_country)
        col.addLayout(_row(idioma.t("country", self.lang), self.country_box))
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _pick_country(self, _index: int) -> None:
        self._save(country=self.country_box.currentData() or "")

    def _personalise(self) -> QWidget:
        """Muse-style: name, look, face, accessory, personality and voice."""
        cfg = self.actions.config
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 14, 0)
        col.setSpacing(10)
        top = QHBoxLayout()
        top.addStretch(1)
        self.preview = Orb(30, lambda: self.state)
        top.addWidget(self.preview)
        top.addStretch(1)
        col.addLayout(top)
        self.style_seg = Segmented(STYLES, SETTINGS["style"], self._pick_style)
        col.addLayout(_row("Estilo", self.style_seg))

        col.addWidget(_label("COLOR", "section"))
        self.colour_stack = QStackedWidget()
        # Orb: colour themes. Character: body colours (+ your own).
        orb_row = QWidget()
        swatches = QHBoxLayout(orb_row)
        swatches.setContentsMargins(0, 0, 0, 0)
        self.swatch_group = QButtonGroup(self)
        for name in THEMES:
            sw = Swatch(name)
            sw.setChecked(name == cfg.get("theme", SETTINGS["theme"]))
            self.swatch_group.addButton(sw)
            swatches.addWidget(sw)
        swatches.addStretch(1)
        self.swatch_group.buttonClicked.connect(lambda b: self._save(theme=b.name))
        body_row = QWidget()
        bodies = QHBoxLayout(body_row)
        bodies.setContentsMargins(0, 0, 0, 0)
        bodies.setSpacing(4)
        self.body_group = QButtonGroup(self)
        for name, colour in BODIES.items():
            dot = ColorDot(colour, name)
            dot.setChecked(colour == SETTINGS["body"])
            self.body_group.addButton(dot)
            bodies.addWidget(dot)
        custom = ColorDot("", "Elegir otro color", plus=True)
        custom.clicked.connect(self._custom_colour)
        bodies.addWidget(custom)
        bodies.addStretch(1)
        self.body_group.buttonClicked.connect(lambda b: self._save(body=b.colour))
        self.colour_stack.addWidget(orb_row)
        self.colour_stack.addWidget(body_row)
        self.colour_stack.setCurrentIndex(1 if SETTINGS["style"] == "muse" else 0)
        self.colour_stack.setFixedHeight(40)
        col.addWidget(self.colour_stack)

        col.addWidget(_label("CARA", "section"))
        self.eye_seg = Segmented(
            EYE_STYLES, SETTINGS["eye_style"], lambda k: self._save(eye_style=k)
        )
        col.addLayout(_row("Ojos", self.eye_seg))
        self.mouth_seg = Segmented(
            MOUTHS, SETTINGS["mouth"], lambda k: self._save(mouth=k)
        )
        col.addLayout(_row("Boca", self.mouth_seg))
        self.eyes = Switch(bool(cfg.get("eyes", SETTINGS["eyes"])))
        self.eyes.toggled.connect(lambda on: self._save(eyes=on))
        col.addLayout(_row("Mostrar su cara", self.eyes))

        col.addWidget(_label("ACCESORIO", "section"))
        chips = QGridLayout()
        chips.setSpacing(4)
        self.chip_group = QButtonGroup(self)
        for i, key in enumerate(ACCESSORIES):
            chip = LookChip(key)
            chip.setChecked(key == SETTINGS["accessory"])
            self.chip_group.addButton(chip)
            chips.addWidget(chip, i // 6, i % 6)
        self.chip_group.buttonClicked.connect(lambda b: self._save(accessory=b.key))
        col.addLayout(chips)

        col.addWidget(_label("PERSONALIDAD", "section"))
        self.persona = QComboBox()
        self.persona.addItems(list(PERSONALITIES))
        self.persona.setCurrentText(str(cfg.get("personality", "Caballero británico")))
        self.persona.currentTextChanged.connect(lambda t: self._save(personality=t))
        col.addLayout(_row("Forma de ser", self.persona))

        col.addWidget(_label("VOZ Y TAMAÑO", "section"))
        self.voice = QComboBox()
        # Long voice names must not push the section wider than the panel.
        self.voice.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.voice.setMinimumContentsLength(16)
        for voice_id, label in VOICES:
            self.voice.addItem(label, voice_id)
        self.voice.addItem("Voz local (sin internet)", "")
        self.voice.setCurrentIndex(max(0, self.voice.findData(cfg.get("voice", ""))))
        self.voice.currentIndexChanged.connect(
            lambda _i: self._save(voice=self.voice.currentData() or "")
        )
        col.addLayout(_row("Voz", self.voice))
        self.rate_seg = Segmented(
            RATES, str(cfg.get("voice_rate", "+0%")), lambda k: self._save(voice_rate=k)
        )
        col.addLayout(_row("Velocidad", self.rate_seg))
        sizes = {key: key for key in SIZES}
        current = next(
            (k for k, v in SIZES.items() if v == cfg.get("cursor_size", 9.0)), "M"
        )
        self.size_seg = Segmented(
            sizes, current, lambda k: self._save(cursor_size=SIZES[k])
        )
        col.addLayout(_row("Tamaño junto al cursor", self.size_seg))
        col.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _pick_style(self, style: str) -> None:
        self.colour_stack.setCurrentIndex(1 if style == "muse" else 0)
        if style == "muse" and SETTINGS["mouth"] == "ninguna":
            self.mouth_seg.select("sonrisa")  # a character looks best smiling
            self._save(style=style, mouth="sonrisa")
        else:
            self._save(style=style)

    def _custom_colour(self) -> None:
        from PySide6.QtWidgets import QColorDialog

        chosen = QColorDialog.getColor(QColor(SETTINGS["body"]), self, "Su color")
        if chosen.isValid():
            for button in self.body_group.buttons():
                button.setChecked(False)
            self._save(body=chosen.name())

    def show_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.tab_group.button(index).setChecked(True)
        if index == self.COWORK:
            self._load_cowork()
        elif index == self.SWARM:
            self._refresh_swarm()

    def open(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            self.move(geo.x() + (geo.width() - WIDTH) // 2, geo.y())
        for tile in self.tiles:
            tile.sync()
        self.multi_switch.setChecked(self.actions.multitasking())
        self.subtitle.setText(self.actions.status())
        self._opened_at = time.monotonic()
        self.show()
        self.raise_()
        self.activateWindow()
        self.entry.setFocus()

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.open()

    def set_state(self, state: str) -> None:
        self.state = state

    def show_answer(self, text: str) -> None:
        if text and not text.startswith("«"):
            self.answer.setText(text)

    def event(self, ev: QEvent) -> bool:  # noqa: D102
        # Like Control Center: clicking elsewhere closes it.
        if ev.type() == QEvent.Type.WindowDeactivate:
            if time.monotonic() - self._opened_at > 0.4:
                QTimer.singleShot(120, self._close_if_inactive)
        return super().event(ev)

    def _close_if_inactive(self) -> None:
        if not self.isActiveWindow() and QGuiApplication.focusWindow() is None:
            self.hide()

    def keyPressEvent(self, ev: Any) -> None:  # noqa: N802
        if ev.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(ev)

    def _talk(self) -> None:
        self.hide()
        self.actions.talk()

    def _send(self) -> None:
        text = self.entry.text().strip()
        if not text:
            return
        self.entry.clear()
        self.answer.setText(f"«{text}»\n\nPensando…")
        self.actions.send(text)

    def _save(self, **changes: Any) -> None:
        cfg = self.actions.config
        if "voice" in changes:
            changes["voice_chosen"] = True  # the user picked it: never migrated
        cfg.update(changes)
        apply_config(cfg)
        self.actions.save_config(cfg)

    def set_level(self, level: float) -> None:
        if hasattr(self, "mic"):
            self.mic.set_level(level)

    def _http(self) -> httpx.Client:
        if self.actions.http is None:
            self.actions.http = httpx.Client(timeout=httpx.Timeout(30, connect=3))
        return self.actions.http

    def _background(self, job: Callable[[], dict], done: Signal) -> None:
        def run() -> None:
            try:
                result = job()
            except Exception as exc:  # noqa: BLE001 — shown in the panel
                result = {"error": str(exc)}
            done.emit(result)

        threading.Thread(target=run, daemon=True).start()

    # -- drawing --------------------------------------------------------------
    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        r = RADIUS
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
        # A faint glow of Sergio's colour along the bottom edge.
        glow = QColor(PALETTES.get(self.state, PALETTES["idle"])[3])
        glow.setAlpha(60)
        p.setPen(QPen(glow, 1.2))
        p.drawLine(
            QPointF(rect.left() + r, rect.bottom() - 0.6),
            QPointF(rect.right() - r, rect.bottom() - 0.6),
        )
        p.end()


__all__ = ["ControlCenter", "PanelActions", "SectionTile", "Switch", "Tile", "Toggle"]

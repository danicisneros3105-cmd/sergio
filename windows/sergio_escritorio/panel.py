"""Sergio's control center: what drops out of the notch when you click it.

Seven sections, as icons only, in the user's language (idioma.py):

* Chat: talk or type to Sergio, the brain, the microphone, the last answer.
* Nodes: your 24/7 digital employees (like OpenAI's Dots): who is working
  on what, who needs you; a quick errand; a new Node.
* Agent Swarm: a huge task split across many agents at once (like Kimi's),
  live progress, and the report.
* Cowork: describe an outcome; Sergio plans and works, and asks here before
  anything delicate (approve or deny each waiting step).
* Health: health, sleep (Night Shift), the mental gym and its results, the
  counselling chair.
* Profile: who you are to Sergio (profile, goals, your face) and how Sergio
  looks and sounds.
* Configuration: the switches (wake word, screen control, camera…),
  multitasking, hiding the notch, language and country.

The look is black and white with one light blue for what you press; one
typeface (estilo.py: Josefin Sans, measured as the closest free match to
the B&O logo), titles in spaced capitals; every measure on a 4 px grid. Native Qt; data comes from
the local Sergio server.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
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

from sergio_escritorio import estilo, idioma
from sergio_escritorio.character import PALETTES, apply_config, draw_character

WIDTH, HEIGHT = 468, 600
RADIUS = 30.0
FONTS = estilo.families()
FAMILY = estilo.css_family()
TEXT = estilo.TEXT  # white
SECONDARY = estilo.SECONDARY
CARD = estilo.CARD  # black
LINE = estilo.LINE
ALUMINIUM = estilo.BLUE  # the one accent: light blue
ACCENT = ALUMINIUM
BRAINS = {
    "auto": "Auto",
    "rapido": "Rápido",
    "equilibrado": "Normal",
    "profundo": "Profundo",
}

STYLE = f"""
QWidget {{ color: {TEXT}; font-family: {FAMILY}; font-size: 15px; }}
QLabel#title {{ font-size: 15px; font-weight: 300; letter-spacing: 3px; }}
QLabel#subtitle, QLabel#hint {{ color: {SECONDARY}; font-size: 13px; }}
QLabel#section, QLabel#heading {{ color: {SECONDARY}; font-size: 10px; font-weight: 600;
                  letter-spacing: 2px; }}
QLabel#answer {{ font-size: 14px; }}
QLabel#tabtip {{ background: {TEXT}; color: #000000; border-radius: 6px; padding: 4px 8px;
                 font-size: 9px; font-weight: 600; letter-spacing: 2px; }}
QLabel#bubble {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px;
                padding: 8px 12px; font-size: 14px; }}
QLabel#mine {{ background: #26251f; border: 1px solid #3a3833; border-radius: 12px;
              padding: 8px 12px; font-size: 14px; }}
QLabel#row {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px;
             padding: 8px 12px; }}
QLineEdit {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px;
             padding: 8px 12px; font-size: 14px;
             selection-background-color: #3a3833; }}
QLineEdit:focus {{ border: 1px solid {ALUMINIUM}; }}
QPushButton {{ background: transparent; border: 1px solid {LINE}; border-radius: 8px;
               padding: 8px 16px; font-weight: 500; letter-spacing: 0.3px; }}
QPushButton:hover {{ border: 1px solid #4a4843; background: #161616; }}
QPushButton#primary {{ background: {ALUMINIUM}; color: #000000; border: none; border-radius: 18px;
                       font-weight: 600; }}
QPushButton#primary:hover {{ background: {estilo.BLUE_HOT}; }}
QPushButton#seg {{ background: transparent; color: {SECONDARY}; border: none;
                   border-radius: 0; padding: 8px 0 7px 0; font-weight: 500;
                   font-size: 13px; letter-spacing: 0.2px;
                   border-bottom: 1px solid transparent; }}
QPushButton#seg:checked {{ color: {TEXT}; border-bottom: 1px solid {ALUMINIUM}; }}
QWidget#segbar {{ background: {CARD}; border-radius: 12px; }}
QWidget#segbar QPushButton#seg {{ padding: 4px 8px; border-radius: 8px; font-size: 11px; }}
QComboBox {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px;
             padding: 4px 12px; min-height: 24px; }}
QComboBox QAbstractItemView {{ background: {CARD}; color: {TEXT};
             selection-background-color: #2a2926; border: 1px solid {LINE}; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px;
                     margin: 0 0 8px 0; padding: 8px 12px; }}
QListWidget::item:selected {{ border: 1px solid {ALUMINIUM}; color: {TEXT}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 4px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 2px; }}
QScrollBar:horizontal {{ height: 0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    estilo.load_fonts()
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
    elif kind == "bubble":  # chat: a speech bubble
        path = QPainterPath()
        path.addRoundedRect(QRectF(x - 9, y - 8, 18, 13), 5, 5)
        p.drawPath(path)
        p.drawLine(QPointF(x - 4, y + 5), QPointF(x - 6, y + 9))
        p.drawLine(QPointF(x - 6, y + 9), QPointF(x + 1, y + 5))
    elif kind == "dots":  # Nodes: persistent agents, a few dots
        p.drawEllipse(QPointF(x - 3.5, y - 2.5), 5.5, 5.5)
        p.drawEllipse(QPointF(x + 5.5, y + 5), 3.8, 3.8)
        p.drawEllipse(QPointF(x + 6.5, y - 6.5), 1.8, 1.8)
    elif kind == "briefcase":  # cowork
        p.drawRoundedRect(QRectF(x - 9, y - 4, 18, 13), 2.5, 2.5)
        p.drawRoundedRect(QRectF(x - 3.5, y - 8, 7, 4), 1.5, 1.5)
        p.drawLine(QPointF(x - 9, y + 1.5), QPointF(x + 9, y + 1.5))
    elif kind == "swarm":  # agent swarm: three linked nodes
        a, b, c = QPointF(x, y - 7), QPointF(x - 7.5, y + 6), QPointF(x + 7.5, y + 6)
        for one, two in ((a, b), (b, c), (c, a)):
            p.drawLine(one, two)
        p.setBrush(QColor(CARD))
        for node in (a, b, c):
            p.drawEllipse(node, 2.8, 2.8)
        p.setBrush(Qt.BrushStyle.NoBrush)
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


class TabIcon(QAbstractButton):
    """A section of the panel shown only as an icon. Under the cursor it
    rises with a little spring and the panel shows its name underneath, in
    spaced capitals (B&O); the open one keeps a light blue dot."""

    SIZE = QSize(56, 52)

    def __init__(self, kind: str, label: str) -> None:
        super().__init__()
        self.kind, self.label = kind, label
        self.hover = 0.0
        self.setCheckable(True)
        self.setFixedSize(self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText(label)  # painted by hand; kept for screen readers and tests
        self.setAccessibleName(label)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(240)
        self._anim.valueChanged.connect(self._step)
        self.on_hover: Callable[["TabIcon", bool], None] | None = None

    def _step(self, value: Any) -> None:
        self.hover = float(value)
        self.update()

    def _go(self, target: float) -> None:
        self._anim.stop()
        self._anim.setEasingCurve(
            QEasingCurve.Type.OutBack if target else QEasingCurve.Type.OutCubic
        )
        self._anim.setStartValue(self.hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, _event: Any) -> None:  # noqa: N802
        self._go(1.0)
        if self.on_hover:
            self.on_hover(self, True)

    def leaveEvent(self, _event: Any) -> None:  # noqa: N802
        self._go(0.0)
        if self.on_hover:
            self.on_hover(self, False)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.hover
        on = self.isChecked()
        colour = QColor(TEXT if (on or h > 0.5) else SECONDARY)
        centre = QPointF(self.width() / 2, 20 - 4 * h)
        p.save()
        p.translate(centre)
        scale = 1.0 + 0.12 * h
        p.scale(scale, scale)
        draw_icon(p, self.kind, QPointF(0, 0), colour)
        p.restore()
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ALUMINIUM))
            p.drawEllipse(QPointF(self.width() / 2, 40), 2.5, 2.5)
        p.end()


class SectionTile(QAbstractButton):
    """One part of Sergio as a row: a ringed icon, its name, one line on
    what it is, a chevron. 56 px tall, 8 px apart, 12 px corners."""

    HEIGHT = 56

    def __init__(self, key: str, label: str, description: str = "") -> None:
        super().__init__()
        self.key, self.label, self.description = key, label, description
        self.icon_kind, self.colour = SECTION_ICONS.get(key, ("gear", ACCENT))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(self.HEIGHT)
        self.setToolTip(description or label)
        self.setAccessibleName(label)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        hot = self.isDown() or self.underMouse()
        p.setPen(QPen(QColor(ALUMINIUM if hot else LINE), 1.0))
        p.setBrush(QColor("#161616" if hot else CARD))
        p.drawRoundedRect(rect, 12, 12)
        bubble = QPointF(rect.left() + 32, rect.center().y())
        p.setPen(QPen(QColor(ALUMINIUM), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(bubble, 16, 16)
        draw_icon(p, self.icon_kind, bubble, QColor(TEXT))
        x = rect.left() + 60
        width = rect.width() - 60 - 36
        p.setPen(QColor(TEXT))
        p.setFont(_font(10, QFont.Weight.DemiBold))
        if self.description:
            p.drawText(QRectF(x, rect.top() + 9, width, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self.label)
            p.setPen(QColor(SECONDARY))
            p.setFont(_font(8.6))
            metrics = QFontMetricsF(p.font())
            left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            p.drawText(QRectF(x, rect.top() + 28, width, 18), left,
                       metrics.elidedText(self.description, Qt.TextElideMode.ElideRight, width))
        else:
            p.drawText(QRectF(x, rect.top(), width, rect.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.label)
        # Chevron
        cx, cy = rect.right() - 20, rect.center().y()
        p.setPen(QPen(QColor(SECONDARY), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx - 3, cy - 5), QPointF(cx + 2, cy))
        p.drawLine(QPointF(cx + 2, cy), QPointF(cx - 3, cy + 5))
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
    nodes_ready = Signal(dict)
    swarms_ready = Signal(dict)

    TABS = ("tab_chat", "tab_nodes", "tab_swarm", "tab_cowork", "tab_health", "tab_profile", "tab_settings")
    CHAT, NODES, SWARM, COWORK, HEALTH, PROFILE, SETTINGS_TAB = range(7)
    HEALTH_SECTIONS = ("health", "night", "gym", "results", "consult")
    PROFILE_SECTIONS = ("profile", "goals", "results", "faces")

    def __init__(self, actions: PanelActions) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        estilo.load_fonts()  # before the style sheet, so every tab gets the typeface
        self.setStyleSheet(STYLE)
        self.setFixedSize(WIDTH, HEIGHT)
        self.actions = actions
        self.lang = str(actions.config.get("language") or idioma.system_language())
        self.state = "idle"
        self._opened_at = 0.0
        self._runs: dict[str, dict] = {}
        self.cowork_ready.connect(self._show_cowork)
        self.nodes_ready.connect(self._show_nodes)
        self.swarms_ready.connect(self._show_swarms)
        self._nodes: list[dict] = []
        self._swarm_lines: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 20)
        root.setSpacing(16)
        root.addLayout(self._header())
        root.addWidget(self._segmented())
        self.pages = QStackedWidget()
        apply_config(self.actions.config)
        self.pages.addWidget(self._chat())
        self.pages.addWidget(self._nodes_page())
        self.pages.addWidget(self._swarm())
        self.pages.addWidget(self._cowork())
        self.pages.addWidget(self._sections_page(self.HEALTH_SECTIONS, "health_hint"))
        self.pages.addWidget(self._profile())
        self.pages.addWidget(self._settings())
        root.addWidget(self.pages, 1)
        self._swarm_timer = QTimer(self)
        self._swarm_timer.timeout.connect(self._refresh_swarm)
        self._swarm_timer.start(1000)
        self._remote_timer = QTimer(self)  # Nodes and swarms live on the server
        self._remote_timer.timeout.connect(self._refresh_remote)
        self._remote_timer.start(3000)

    # -- building blocks -------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(Orb(10, lambda: self.state), 0, Qt.AlignmentFlag.AlignVCenter)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.title = _label("SERGIO", "title")
        texts.addWidget(self.title)
        self.subtitle = _label("", "subtitle")
        self.subtitle.setVisible(False)  # only when there is something to say
        texts.addWidget(self.subtitle)
        row.addLayout(texts, 1)
        close = QPushButton("×")
        close.setFixedSize(28, 28)
        close.setAccessibleName("Cerrar")
        close.setStyleSheet("border-radius: 14px; padding: 0 0 2px 0; font-size: 14px;")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        row.addWidget(close, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    TAB_ICONS = ("bubble", "dots", "swarm", "briefcase", "heart", "person", "gear")

    def _segmented(self) -> QWidget:
        """The six sections as icons only (their names appear on hover)."""
        bar = QWidget()
        bar.setStyleSheet(f"border-bottom: 1px solid {LINE};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.tab_group = QButtonGroup(self)
        for i, (key, kind) in enumerate(zip(self.TABS, self.TAB_ICONS)):
            button = TabIcon(kind, idioma.t(key, self.lang))
            button.on_hover = self._tab_tip
            self.tab_group.addButton(button, i)
            if i:
                row.addStretch(1)  # equal gaps between the icons
            row.addWidget(button)
        self.tab_group.button(0).setChecked(True)
        self.tab_group.idClicked.connect(self.show_tab)
        self.tab_tip = QLabel(self)  # the hovered icon's name, never clipped
        self.tab_tip.setObjectName("tabtip")
        self.tab_tip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.tab_tip.hide()
        return bar

    def _tab_tip(self, tab: "TabIcon", show: bool) -> None:
        if not show:
            self.tab_tip.hide()
            return
        self.tab_tip.setText(tab.label.upper())
        self.tab_tip.adjustSize()
        centre = tab.mapTo(self, QPointF(tab.width() / 2, tab.height()).toPoint())
        x = max(8, min(self.width() - self.tab_tip.width() - 8, centre.x() - self.tab_tip.width() // 2))
        self.tab_tip.move(x, centre.y() + 2)
        self.tab_tip.raise_()
        self.tab_tip.show()

    def _chat(self) -> QWidget:
        """A conversation, like a messenger: the brain on top, what was said
        in the middle (newest at the bottom), the composer at the foot."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        self.brain = Segmented(
            BRAINS,
            str(self.actions.config.get("effort", "auto")),
            lambda k: self._save(effort=k),
        )
        col.addLayout(_row(idioma.t("brain", self.lang), self.brain))
        self.thread = QWidget()
        self.thread_col = QVBoxLayout(self.thread)
        self.thread_col.setContentsMargins(0, 0, 4, 0)
        self.thread_col.setSpacing(8)
        self.thread_col.addStretch(1)
        self.answer = self._bubble(idioma.t("ask_me", self.lang), mine=False)
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_scroll.setWidget(self.thread)
        col.addWidget(self.chat_scroll, 1)
        ask = QHBoxLayout()
        ask.setSpacing(8)
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
        self.mic = LevelBar()
        self.mic.setToolTip(idioma.t("mic", self.lang))
        col.addWidget(self.mic)
        return page

    MAX_BUBBLES = 24

    def _bubble(self, text: str, mine: bool) -> QLabel:
        label = _label(text, "mine" if mine else "bubble", True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setMaximumWidth(int(WIDTH * 0.74))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if mine:
            row.addStretch(1)
        row.addWidget(label)
        if not mine:
            row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        self.thread_col.addWidget(holder)
        while self.thread_col.count() > self.MAX_BUBBLES + 1:  # keep it light
            old = self.thread_col.takeAt(1).widget()
            if old is not None:
                old.deleteLater()
        if hasattr(self, "chat_scroll"):
            QTimer.singleShot(0, lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()))
        return label

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

    def _nodes_page(self) -> QWidget:
        """Your Nodes: who works on what, who needs you, a quick errand."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        col.addWidget(_label(idioma.t("nodes_hint", self.lang), "hint", True))
        self.node_list = QListWidget()
        self.node_list.itemDoubleClicked.connect(lambda _i: self._open_node())
        col.addWidget(self.node_list, 1)
        row = QHBoxLayout()
        self.node_entry = QLineEdit()
        self.node_entry.setPlaceholderText(idioma.t("node_errand", self.lang))
        self.node_entry.returnPressed.connect(self._send_node)
        row.addWidget(self.node_entry, 1)
        send = QPushButton(idioma.t("send", self.lang))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._send_node)
        row.addWidget(send)
        col.addLayout(row)
        buttons = QHBoxLayout()
        create = QPushButton(idioma.t("new_node", self.lang))
        create.setObjectName("primary")
        create.clicked.connect(self._new_node)
        see = QPushButton(idioma.t("open_node", self.lang))
        see.clicked.connect(self._open_node)
        for button in (create, see):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        col.addLayout(buttons)
        return page

    def _swarm(self) -> QWidget:
        """Agent Swarm: one huge task, many agents at once, one report."""
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
        self.swarm_list.itemDoubleClicked.connect(self._open_swarm)
        col.addWidget(self.swarm_list, 1)
        buttons = QHBoxLayout()
        big = QPushButton(idioma.t("open_swarm", self.lang))
        big.clicked.connect(lambda: self.actions.open_url(f"{self.actions.server_url.rstrip('/')}/swarm"))
        cancel = QPushButton(idioma.t("cancel_last", self.lang))
        cancel.clicked.connect(lambda: self.actions.send("cancela la tarea"))
        for button in (big, cancel):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        col.addLayout(buttons)
        return page

    def _section_rows(self, keys: tuple[str, ...]) -> QVBoxLayout:
        rows = QVBoxLayout()
        rows.setSpacing(8)
        for key in keys:
            tile = SectionTile(key, idioma.t(key, self.lang), idioma.t(f"d_{key}", self.lang))
            tile.clicked.connect(lambda _c=False, k=key: self._open_section(k))
            rows.addWidget(tile)
        return rows

    def _sections_page(self, keys: tuple[str, ...], hint: str) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        col.addWidget(_label(idioma.t(hint, self.lang), "hint", True))
        col.addLayout(self._section_rows(keys))
        col.addStretch(1)
        return page

    def _profile(self) -> QWidget:
        """Who you are to Sergio, your results too. Sergio himself is not
        personalised: only agents are (Agent Swarm → Crear agente)."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(12)
        col.addLayout(self._section_rows(self.PROFILE_SECTIONS))
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _web(self, path: str) -> None:
        self.hide()
        self.actions.open_url(f"{self.actions.server_url.rstrip('/')}{path}")

    def _new_node(self) -> None:
        """Nodes are what you personalise, like OpenAI's Dots: name it, say
        what it looks after, connect apps; it introduces itself."""
        self._web("/nodes?nuevo=1")

    def _current_node(self) -> dict | None:
        item = self.node_list.currentItem()
        node_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((n for n in self._nodes if n.get("id") == node_id), None)

    def _open_node(self) -> None:
        node = self._current_node()
        self._web(f"/nodes/{node['id']}" if node else "/nodes")

    def _send_node(self) -> None:
        text = self.node_entry.text().strip()
        node = self._current_node() or (self._nodes[0] if self._nodes else None)
        if not text or node is None:
            return
        self.node_entry.clear()
        base = self.actions.server_url
        node_id = node["id"]

        def job() -> dict:
            self._http().post(f"{base}/v1/nodes/{node_id}/messages", json={"text": text}).raise_for_status()
            return self._http().get(f"{base}/v1/nodes").json()

        self._background(job, self.nodes_ready)

    def _show_nodes(self, data: dict) -> None:
        if data.get("error"):
            self._nodes = []
            self.node_list.clear()
            self.node_list.addItem(idioma.t("no_server", self.lang))
            return
        self._nodes = list(data.get("nodes") or [])
        chosen = self.node_list.currentItem()
        keep = chosen.data(Qt.ItemDataRole.UserRole) if chosen else None
        self.node_list.clear()
        if not self._nodes:
            self.node_list.addItem(idioma.t("no_nodes", self.lang))
            return
        for node in self._nodes:
            status = node.get("status", "idle")
            if status == "working" and node.get("doing"):
                line = node["doing"]
            elif status == "needs_you" and node.get("waiting"):
                line = node["waiting"]
            else:
                line = idioma.t(f"node_{status}", self.lang)
            flag = "  ●" if node.get("approvals") or status == "needs_you" else ""
            item = QListWidgetItem(f"{node.get('name', '')}{flag}\n{str(line)[:70]}")
            item.setData(Qt.ItemDataRole.UserRole, node.get("id"))
            self.node_list.addItem(item)
            if node.get("id") == keep:
                self.node_list.setCurrentItem(item)

    def _open_swarm(self, item: QListWidgetItem) -> None:
        run_id = item.data(Qt.ItemDataRole.UserRole)
        self._web(f"/swarm/{run_id}" if run_id else "/swarm")

    def _show_swarms(self, data: dict) -> None:
        lines: list[tuple[str, str]] = []
        for run in (data.get("runs") or [])[:6]:
            counts = run.get("counts") or {}
            total = len(run.get("subtasks") or [])
            status = idioma.t(f"swarm_{run.get('status', 'done')}", self.lang)
            title = run.get("title") or run.get("task", "")
            lines.append((f"{title}\n{counts.get('done', 0)}/{total} · {status}", run.get("id", "")))
        for line in self.actions.swarm() or []:  # this PC's own background tasks
            lines.append((line, ""))
        if not lines:
            lines = [(idioma.t("nothing_running", self.lang), "")]
        if [self.swarm_list.item(i).text() for i in range(self.swarm_list.count())] == [t for t, _ in lines]:
            return
        self.swarm_list.clear()
        for text, run_id in lines:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, run_id)
            self.swarm_list.addItem(item)

    def _refresh_remote(self) -> None:
        if not self.isVisible():
            return
        index = self.pages.currentIndex()
        base = self.actions.server_url
        if index == self.NODES:
            self._background(lambda: self._http().get(f"{base}/v1/nodes").json(), self.nodes_ready)
        elif index == self.SWARM:
            self._background(lambda: self._http().get(f"{base}/v1/swarm").json(), self.swarms_ready)

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
        base = self.actions.server_url

        def job() -> dict:
            run = self._http().post(f"{base}/v1/swarm", data={"task": text, "parallel": "8"})
            run.raise_for_status()
            self.actions.open_url(f"{base.rstrip('/')}/swarm/{run.json()['id']}")
            return self._http().get(f"{base}/v1/swarm").json()

        self._background(job, self.swarms_ready)

    def _refresh_swarm(self) -> None:
        """The local lines tick every second; the server's swarms every 3 s."""
        if not self.isVisible() or self.pages.currentIndex() != self.SWARM:
            return
        if not self.swarm_list.count():
            self._show_swarms({})

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
        self.language_box.setFixedWidth(208)
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
        self.country_box.setFixedWidth(208)
        col.addLayout(_row(idioma.t("country", self.lang), self.country_box))
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _pick_country(self, _index: int) -> None:
        self._save(country=self.country_box.currentData() or "")

    def show_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.tab_group.button(index).setChecked(True)
        if index == self.COWORK:
            self._load_cowork()
        elif index in (self.NODES, self.SWARM):
            self._refresh_remote()

    def open(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            self.move(geo.x() + (geo.width() - WIDTH) // 2, geo.y())
        for tile in self.tiles:
            tile.sync()
        self.multi_switch.setChecked(self.actions.multitasking())
        status = self.actions.status()
        self.subtitle.setText(status)
        self.subtitle.setVisible(bool(status))
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
        if not text or text.startswith("«"):
            return
        if getattr(self, "_thinking", None) is not None:
            self._thinking.setText(text)  # the «…» bubble becomes the answer
            self.answer, self._thinking = self._thinking, None
        else:
            self.answer = self._bubble(text, mine=False)

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
        self._bubble(text, mine=True)
        self._thinking = self._bubble("…", mine=False)
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

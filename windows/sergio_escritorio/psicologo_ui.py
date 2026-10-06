"""The consulting room: Sergio in a lounge chair, glasses on, taking notes.

A warm room, a mid-century lounge chair (white leather, dark hazelnut wood,
black swivel base) with its ottoman, and Sergio sitting in it with round
glasses and a black notebook. He breathes and blinks, looks at you while
you talk, looks down and writes a line in the notebook after each thing
you say (the page fills, then turns), and looks up to answer.

Beside it, the conversation (type or press the microphone), the PHQ-9 /
GAD-7 questionnaires and, always visible, the crisis lines.
"""

from __future__ import annotations

import math
import random
import time
from html import escape
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from sergio_escritorio import character
from sergio_escritorio.coach_ui import in_background
from sergio_escritorio.psicologo import OPTIONS, PERIOD, QUESTIONNAIRES, Consult, explain_score, score

LEATHER = QColor(244, 240, 232)
LEATHER_SHADE = QColor(214, 207, 194)
WOOD = QColor(92, 58, 34)  # dark hazelnut
WOOD_LIGHT = QColor(128, 84, 50)
METAL = QColor(28, 28, 30)
NOTEBOOK = QColor(22, 22, 24)
PAGE = QColor(246, 242, 232)
INK = QColor(40, 40, 52)
CRISIS_LINE = "Emergencias: ECU 911 · Apoyo psicológico gratuito: Línea 171, opción 6 (7:00-20:00)"


def _round(colour: QColor, width: float) -> QPen:
    pen = QPen(colour, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def _font(size: float, bold: bool = False) -> QFont:
    f = QFont(["Segoe UI Variable Display", "SF Pro Display", "Segoe UI"])
    f.setPointSizeF(size)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


class Scene(QWidget):
    """The animated consulting room."""

    def __init__(self, parent: QWidget | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(parent)
        self.clock = clock
        self.t0 = clock()
        self.state = "listening"  # listening | writing | speaking
        self._until = 0.0
        self.lines: list[float] = []  # lengths (0..1) of the lines on the page
        self._line_start = 0.0
        self._flip_at = -10.0
        self.rng = random.Random(7)
        self.setMinimumSize(420, 420)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    # what he does
    def write(self, seconds: float = 2.2) -> None:
        """Look down and write a line (the page turns when it is full)."""
        now = self.clock()
        if len(self.lines) >= 9:
            self.lines = []
            self._flip_at = now
        self.lines.append(0.55 + 0.4 * self.rng.random())
        self._line_start = now
        self.state = "writing"
        self._until = now + seconds

    def speak(self, seconds: float) -> None:
        self.state = "speaking"
        self._until = self.clock() + max(1.5, seconds)

    def listen(self) -> None:
        self.state = "listening"
        self._until = 0.0

    def _tick(self) -> None:
        if self._until and self.clock() > self._until and self.state != "writing_hold":
            self.state = "listening"
            self._until = 0.0
        self.update()

    def write_progress(self) -> float:
        return min(1.0, (self.clock() - self._line_start) / 1.6) if self.state == "writing" else 1.0

    # drawing
    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.draw(p, QRectF(self.rect()), self.clock() - self.t0)
        finally:
            p.end()

    def draw(self, p: QPainter, rect: QRectF, t: float) -> None:
        w, h = rect.width(), rect.height()
        u = min(w / 9.0, h / 8.4)
        cx = rect.left() + w * 0.44
        floor = rect.top() + h * 0.88
        seat_y = floor - 2.35 * u
        self._room(p, rect, floor, u, t)
        self._ottoman(p, QPointF(cx + 3.15 * u, floor), u)
        self._base(p, QPointF(cx - 0.1 * u, seat_y + 0.55 * u), floor, u)
        self._chair_back(p, QPointF(cx, seat_y), u)
        self._seat(p, QPointF(cx, seat_y), u)
        self._sergio(p, QPointF(cx - 0.25 * u, seat_y - 1.6 * u), u, t)
        self._armrest(p, QPointF(cx, seat_y), u)
        self._notebook(p, QPointF(cx + 0.75 * u, seat_y - 0.62 * u), u, t)

    def _room(self, p: QPainter, rect: QRectF, floor: float, u: float, t: float) -> None:
        wall = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        wall.setColorAt(0, QColor(46, 38, 34))
        wall.setColorAt(1, QColor(28, 24, 22))
        p.fillRect(rect, wall)
        # lamp light, softly breathing
        glow = QRadialGradient(QPointF(rect.left() + rect.width() * 0.12, rect.top() + rect.height() * 0.18), rect.width() * 0.75)
        glow.setColorAt(0, QColor(255, 200, 140, int(70 + 8 * math.sin(t * 0.7))))
        glow.setColorAt(1, QColor(255, 200, 140, 0))
        p.fillRect(rect, glow)
        # floor and rug
        p.fillRect(QRectF(rect.left(), floor - 0.35 * u, rect.width(), rect.bottom() - floor + 0.35 * u), QColor(36, 30, 27))
        rug = QRadialGradient(QPointF(rect.center().x(), floor), rect.width() * 0.5)
        rug.setColorAt(0, QColor(120, 110, 98, 120))
        rug.setColorAt(1, QColor(120, 110, 98, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rug)
        p.drawEllipse(QPointF(rect.center().x() + u, floor + 0.05 * u), rect.width() * 0.48, 0.7 * u)
        # arc floor lamp
        base = QPointF(rect.left() + 0.55 * u, floor)
        p.setPen(_round(QColor(170, 170, 176), 0.09 * u))
        arc = QPainterPath(base)
        arc.cubicTo(base + QPointF(0, -6.8 * u), base + QPointF(2.6 * u, -8.2 * u), base + QPointF(3.6 * u, -6.9 * u))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(arc)
        shade = base + QPointF(3.6 * u, -6.9 * u)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(210, 210, 214))
        p.drawPie(QRectF(shade.x() - 0.55 * u, shade.y() - 0.35 * u, 1.1 * u, 0.8 * u), 0, 180 * 16)
        light = QRadialGradient(shade + QPointF(0, 0.2 * u), 1.4 * u)
        light.setColorAt(0, QColor(255, 226, 170, 150))
        light.setColorAt(1, QColor(255, 226, 170, 0))
        p.setBrush(light)
        p.drawEllipse(shade + QPointF(0, 0.2 * u), 1.4 * u, 1.4 * u)
        # plant
        pot = QRectF(rect.right() - 1.25 * u, floor - 1.0 * u, 0.85 * u, 1.0 * u)
        p.setBrush(QColor(200, 196, 188))
        p.drawRoundedRect(pot, 0.12 * u, 0.12 * u)
        p.setBrush(QColor(54, 92, 64))
        for k in range(7):
            angle = -math.pi / 2 + (k - 3) * 0.32
            tip = QPointF(pot.center().x() + math.cos(angle) * 1.4 * u, pot.top() + math.sin(angle) * 1.6 * u)
            leaf = QPainterPath(QPointF(pot.center().x(), pot.top()))
            leaf.quadTo(tip + QPointF(-0.3 * u, 0.3 * u), tip)
            leaf.quadTo(tip + QPointF(0.3 * u, 0.4 * u), QPointF(pot.center().x(), pot.top()))
            p.drawPath(leaf)

    def _wood_shell(self, p: QPainter, rect: QRectF, radius: float) -> None:
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, WOOD_LIGHT)
        grad.setColorAt(1, WOOD)
        p.setPen(QPen(WOOD.darker(130), max(1.0, radius * 0.06)))
        p.setBrush(grad)
        p.drawRoundedRect(rect, radius, radius)

    def _cushion(self, p: QPainter, rect: QRectF, radius: float, tufts: int = 1) -> None:
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0, LEATHER)
        grad.setColorAt(1, LEATHER_SHADE)
        p.setPen(QPen(LEATHER_SHADE.darker(115), max(0.8, radius * 0.05)))
        p.setBrush(grad)
        p.drawRoundedRect(rect, radius, radius)
        p.setPen(QPen(LEATHER_SHADE.darker(125), max(0.8, radius * 0.04)))
        for k in range(1, tufts + 1):  # stitched tufting
            y = rect.top() + rect.height() * k / (tufts + 1)
            p.drawLine(QPointF(rect.left() + radius * 0.6, y), QPointF(rect.right() - radius * 0.6, y))
            p.setBrush(LEATHER_SHADE.darker(120))
            for x in (rect.left() + rect.width() * 0.33, rect.left() + rect.width() * 0.67):
                p.drawEllipse(QPointF(x, y), radius * 0.09, radius * 0.09)

    def _chair_back(self, p: QPainter, seat: QPointF, u: float) -> None:
        p.save()
        p.translate(seat + QPointF(-1.0 * u, -0.2 * u))
        p.rotate(-14)
        self._wood_shell(p, QRectF(-1.25 * u, -3.25 * u, 2.5 * u, 3.15 * u), 0.45 * u)
        self._cushion(p, QRectF(-1.08 * u, -3.1 * u, 2.16 * u, 2.9 * u), 0.4 * u, 2)
        # headrest
        self._wood_shell(p, QRectF(-1.15 * u, -4.55 * u, 2.3 * u, 1.35 * u), 0.4 * u)
        self._cushion(p, QRectF(-1.0 * u, -4.42 * u, 2.0 * u, 1.12 * u), 0.36 * u, 1)
        p.restore()

    def _seat(self, p: QPainter, seat: QPointF, u: float) -> None:
        p.save()
        p.translate(seat)
        p.rotate(-5)
        self._wood_shell(p, QRectF(-2.05 * u, -0.25 * u, 4.0 * u, 0.85 * u), 0.35 * u)
        self._cushion(p, QRectF(-1.9 * u, -0.55 * u, 3.7 * u, 0.8 * u), 0.32 * u, 1)
        p.restore()

    def _armrest(self, p: QPainter, seat: QPointF, u: float) -> None:
        p.save()
        p.translate(seat + QPointF(0.0, -0.55 * u))
        p.rotate(-4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(150, 150, 156))  # aluminium support
        p.drawRoundedRect(QRectF(1.05 * u, 0.0, 0.2 * u, 0.6 * u), 0.08 * u, 0.08 * u)
        p.setBrush(METAL)
        p.drawRoundedRect(QRectF(-0.4 * u, -0.08 * u, 1.9 * u, 0.24 * u), 0.12 * u, 0.12 * u)
        p.restore()

    def _base(self, p: QPainter, top: QPointF, floor: float, u: float) -> None:
        p.setPen(_round(METAL, 0.22 * u))
        p.drawLine(top, QPointF(top.x(), floor - 0.45 * u))
        hub = QPointF(top.x(), floor - 0.45 * u)
        for dx, dy in ((-1.9, 0.38), (1.6, 0.42), (0.35, 0.6), (-0.9, 0.28), (1.0, 0.25)):
            end = QPointF(top.x() + dx * u, floor + (dy - 0.3) * u)
            p.setPen(_round(METAL, 0.18 * u))
            p.drawLine(hub, end)
            p.setPen(_round(QColor(120, 120, 126), 0.05 * u))
            p.drawLine(hub + QPointF(0, -0.04 * u), end + QPointF(0, -0.05 * u))

    def _ottoman(self, p: QPainter, at: QPointF, u: float) -> None:
        p.setPen(_round(METAL, 0.14 * u))
        for dx in (-0.9, 0.0, 0.9):
            p.drawLine(at + QPointF(0, -0.75 * u), at + QPointF(dx * u, -0.08 * u))
        self._wood_shell(p, QRectF(at.x() - 1.15 * u, at.y() - 1.45 * u, 2.3 * u, 0.7 * u), 0.3 * u)
        self._cushion(p, QRectF(at.x() - 1.02 * u, at.y() - 1.75 * u, 2.04 * u, 0.62 * u), 0.28 * u, 1)

    def _sergio(self, p: QPainter, centre: QPointF, u: float, t: float) -> None:
        r = 1.15 * u
        writing = self.state == "writing"
        look = QPointF(0.55, 0.95) if writing else QPointF(0.45, -0.1)
        nod = math.sin(t * 2.0) * 0.04 * u if self.state == "listening" else 0.0
        state = "speaking" if self.state == "speaking" else "idle"
        saved = dict(character.SETTINGS)
        try:
            character.SETTINGS["style"] = "muse"
            character.SETTINGS["eyes"] = True
            if character.SETTINGS.get("eye_style") == "felices":
                character.SETTINGS["eye_style"] = "ovalos"
            c = centre + QPointF(0, nod)
            character.draw_character(p, c, r, state, t, look=look, mood="" if writing else "")
        finally:
            character.SETTINGS.clear()
            character.SETTINGS.update(saved)
        # round glasses on the eyes (same gaze offset the face uses)
        breathe = 1.0 + 0.025 * math.sin(t * 1.8)
        rr = r * breathe
        gaze = QPointF(look.x() * rr * 0.12, look.y() * rr * 0.1)
        eye_y = -rr * 0.08
        p.setBrush(QColor(255, 255, 255, 28))
        p.setPen(QPen(QColor(30, 26, 22), max(1.2, rr * 0.045)))
        lenses = []
        for side in (-1, 1):
            ec = c + QPointF(side * rr * 0.3, eye_y) + gaze
            lenses.append(ec)
            p.drawEllipse(ec, rr * 0.17, rr * 0.15)
        p.drawLine(lenses[0] + QPointF(rr * 0.15, -rr * 0.03), lenses[1] + QPointF(-rr * 0.15, -rr * 0.03))
        p.drawLine(lenses[0] + QPointF(-rr * 0.17, -rr * 0.02), lenses[0] + QPointF(-rr * 0.42, -rr * 0.06))
        p.drawLine(lenses[1] + QPointF(rr * 0.17, -rr * 0.02), lenses[1] + QPointF(rr * 0.42, -rr * 0.06))
        p.setPen(QPen(QColor(255, 255, 255, 120), max(0.8, rr * 0.02)))
        for ec in lenses:  # a glint
            p.drawArc(QRectF(ec.x() - rr * 0.12, ec.y() - rr * 0.11, rr * 0.24, rr * 0.22), 100 * 16, 50 * 16)

    def _notebook(self, p: QPainter, at: QPointF, u: float, t: float) -> None:
        body = QColor(character.SETTINGS.get("body") or "#f3e9d2")
        p.save()
        p.translate(at)
        p.rotate(-12)
        p.scale(0.82, 0.82)
        # black cover with the open pages on it
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(NOTEBOOK)
        p.drawRoundedRect(QRectF(-0.95 * u, -0.62 * u, 1.9 * u, 1.24 * u), 0.08 * u, 0.08 * u)
        page = QRectF(-0.88 * u, -0.56 * u, 1.76 * u, 1.12 * u)
        p.setBrush(PAGE)
        p.drawRoundedRect(page, 0.05 * u, 0.05 * u)
        p.setPen(QPen(QColor(200, 194, 182), 0.02 * u))
        p.drawLine(QPointF(0, page.top()), QPointF(0, page.bottom()))  # the spine
        p.setBrush(NOTEBOOK)  # elastic band
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(0.78 * u, -0.62 * u, 0.06 * u, 1.24 * u))
        # lines of handwriting
        progress = self.write_progress()
        pen = _round(INK, 0.035 * u)
        tip = QPointF(-0.75 * u, -0.4 * u)
        for i, length in enumerate(self.lines):
            column = 0 if i < 5 else 1
            row = i if i < 5 else i - 5
            left = page.left() + 0.1 * u + column * 0.9 * u
            y = page.top() + 0.16 * u + row * 0.19 * u
            done = length * (progress if i == len(self.lines) - 1 else 1.0)
            path = QPainterPath(QPointF(left, y))
            steps = max(2, int(24 * done))
            for k in range(1, steps + 1):
                x = left + 0.72 * u * done * k / steps
                path.lineTo(QPointF(x, y + math.sin(k * 1.9 + i) * 0.025 * u))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            if i == len(self.lines) - 1:
                tip = QPointF(left + 0.72 * u * done, y)
        flip = self.clock() - self._flip_at
        if 0 <= flip < 0.6:  # the page turning
            k = flip / 0.6
            p.setBrush(QColor(236, 230, 218))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(QPolygonF([QPointF(0, page.top()), QPointF(page.right() * (1 - 2 * k), page.top() - 0.1 * u * math.sin(k * math.pi)),
                                     QPointF(page.right() * (1 - 2 * k), page.bottom()), QPointF(0, page.bottom())]))  # fmt: skip
        # the hand with the pen
        wobble = math.sin(t * 22) * 0.03 * u if self.state == "writing" and progress < 1 else 0.0
        hand = tip + QPointF(0.18 * u, 0.12 * u + wobble)
        p.setPen(_round(QColor(200, 170, 90), 0.06 * u))
        p.drawLine(tip + QPointF(0, wobble), hand + QPointF(0.32 * u, -0.28 * u))
        p.setPen(QPen(body.darker(130), 0.02 * u))
        p.setBrush(body)
        p.drawEllipse(hand + QPointF(0.12 * u, -0.1 * u), 0.2 * u, 0.17 * u)
        p.restore()


class ConsultWindow(QWidget):
    """The consulting room: the scene and the conversation."""

    def __init__(
        self,
        consult: Consult,
        ask: Callable[[list[dict[str, str]], list[dict[str, Any]]], dict[str, Any]],
        speak: Callable[[str], None],
        talk: Callable[[], None],
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("Sergio · Consulta")
        self.setStyleSheet(
            "QWidget#room { background: #1E1A18; } QLabel { color: #EDE6DC; }"
            "QTextBrowser { background: #26211E; color: #EDE6DC; border: none; border-radius: 14px; padding: 10px; font-size: 14px; }"
            "QLineEdit { background: #2E2824; color: white; border: none; border-radius: 12px; padding: 10px; font-size: 14px; }"
            "QPushButton { background: #C9A27E; color: #1E1A18; border: none; border-radius: 12px; padding: 9px 14px; font-weight: 600; }"
            "QPushButton#plain { background: #3A332E; color: #EDE6DC; }"
        )
        self.setObjectName("room")
        self.consult, self._ask, self._speak, self._talk = consult, ask, speak, talk
        self.quiz: dict[str, Any] | None = None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 16, 12)
        self.scene = Scene()
        row.addWidget(self.scene, 5)
        side = QVBoxLayout()
        title = QLabel("Consulta")
        title.setFont(_font(18, True))
        sub = QLabel("Un espacio para hablar. Lo que diga aquí queda cifrado en su PC.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#A89C8E;")
        self.chat = QTextBrowser()
        self.answers = QHBoxLayout()
        entry = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setPlaceholderText("Escriba lo que quiera contarme…")
        self.text.returnPressed.connect(self._send_typed)
        mic, send = QPushButton("🎤"), QPushButton("Enviar")
        mic.setObjectName("plain")
        mic.clicked.connect(self._talk)
        send.clicked.connect(self._send_typed)
        entry.addWidget(self.text, 1)
        entry.addWidget(mic)
        entry.addWidget(send)
        tools = QHBoxLayout()
        for key, label in (("phq9", "Cuestionario de ánimo"), ("gad7", "Cuestionario de ansiedad")):
            b = QPushButton(label)
            b.setObjectName("plain")
            b.clicked.connect(lambda _c=False, k=key: self.start_quiz(k))
            tools.addWidget(b)
        tools.addStretch()
        crisis = QLabel(CRISIS_LINE)
        crisis.setWordWrap(True)
        crisis.setStyleSheet("color:#E8A090; font-size: 12px;")
        for w in (title, sub, self.chat):
            side.addWidget(w)
        side.addLayout(self.answers)
        side.addLayout(entry)
        side.addLayout(tools)
        side.addWidget(crisis)
        holder = QWidget()
        holder.setLayout(side)
        row.addWidget(holder, 4)
        self.resize(1100, 680)
        self._history: list[tuple[str, str]] = []
        for m in consult.current()["mensajes"]:
            self._history.append((m["role"], m["content"]))
        if not self._history:
            self._bubble("assistant", "Buenas, señor. Póngase cómodo. ¿Qué le trae por aquí hoy?")
        self._render()

    # conversation
    def _bubble(self, role: str, text: str) -> None:
        self._history.append((role, text))
        self._render()

    def _render(self) -> None:
        html = []
        for role, text in self._history[-60:]:
            if role == "user":
                html.append(f"<p align='right' style='margin:8px 0'><span style='background:#4A3F37;padding:6px'>{escape(text)}</span></p>")
            else:
                html.append(f"<p style='margin:8px 0;color:#F3EADF'>{escape(text)}</p>")
        self.chat.setHtml("".join(html))
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def _send_typed(self) -> None:
        text = self.text.text().strip()
        self.text.clear()
        if text:
            self.hear(text)

    def hear(self, text: str) -> None:
        """Something you said (typed or by voice)."""
        if self.quiz is not None:
            return
        self._bubble("user", text)
        self.consult.said(text)
        self.scene.write(2.4)
        messages, notes = self.consult.messages(), self.consult.notes()
        in_background(lambda: self._ask(messages, notes), self._answered)

    def _answered(self, reply: Any) -> None:
        if isinstance(reply, Exception):
            reply = {"respuesta": "Perdone, se me cortó la conexión. Sigo aquí; ¿me lo repite?"}
        self.consult.replied(reply)
        text = str(reply.get("respuesta", ""))
        self._bubble("assistant", text)
        self.scene.speak(len(text) / 15.0)
        self._speak(text)

    # questionnaires
    def start_quiz(self, key: str) -> None:
        q = QUESTIONNAIRES[key]
        self.quiz = {"q": q, "answers": []}
        self._bubble("assistant", f"{q.name}. {PERIOD} Responda con los botones; puede parar cuando quiera.")
        self._ask_item()

    def _ask_item(self) -> None:
        while self.answers.count():
            item = self.answers.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if self.quiz is None:
            return
        q, done = self.quiz["q"], self.quiz["answers"]
        if len(done) == len(q.items):
            self._finish_quiz()
            return
        self._bubble("assistant", f"{len(done) + 1}/{len(q.items)} · {q.items[len(done)]}")
        for value, label in enumerate(OPTIONS):
            b = QPushButton(label)
            b.setObjectName("plain")
            b.clicked.connect(lambda _c=False, v=value: self._quiz_answer(v))
            self.answers.addWidget(b)
        stop = QPushButton("Parar")
        stop.setObjectName("plain")
        stop.clicked.connect(self._stop_quiz)
        self.answers.addWidget(stop)

    def _quiz_answer(self, value: int) -> None:
        if self.quiz is None:
            return
        self._history.append(("user", OPTIONS[value]))
        self.quiz["answers"].append(value)
        self.scene.write(1.2)
        self._ask_item()

    def _stop_quiz(self) -> None:
        self.quiz = None
        self._ask_item()
        self._bubble("assistant", "De acuerdo, lo dejamos aquí. Seguimos hablando cuando quiera.")

    def _finish_quiz(self) -> None:
        q, answers = self.quiz["q"], self.quiz["answers"]
        self.quiz = None
        result = score(q, answers)
        previous = self.consult.add_test(result)
        text = explain_score(result, previous)
        if result["riesgo"]:
            text += " Marcó pensamientos de hacerse daño: eso me importa mucho. " + CRISIS_LINE + ". ¿Quiere contarme un poco más? Estoy aquí."
        self._bubble("assistant", text)
        self.scene.speak(len(text) / 15.0)
        self._speak(text)

    def open(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()


__all__ = ["CRISIS_LINE", "ConsultWindow", "Scene"]

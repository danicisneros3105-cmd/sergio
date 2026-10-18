"""Night Shift on screen: the last-resort veil and the settings sheet.

The screen itself is tinted by ``nocturno.NightEngine`` (Windows' colour
matrix or a verified gamma ramp, on its own thread). The veil here is only
for PCs where neither works: a click-through window that dims with pure
black (which keeps contrast) and adds very little amber, so it never looks
like a grey film.

The sheet is what the «Night» tile opens: on/off, the intensity (dragging it
previews the bedtime look live), «Noche ya», and tonight's curve with the
times it follows.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Callable

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sergio_escritorio import estilo, nocturno
from sergio_escritorio.nocturno import DAY_K, NIGHT_K


def veil(kelvin: float, brightness: float) -> tuple[QColor, QColor]:
    """(warm amber, dark) layers: warmer as kelvin falls, darker as light falls.

    Amber is kept light (an overlay adds colour to blacks); most of the work
    is the black layer, which only scales the light."""
    warm = max(0.0, min(1.0, (DAY_K - kelvin) / (DAY_K - NIGHT_K)))
    return QColor(255, 120, 20, int(warm * 48)), QColor(0, 0, 0, int(max(0.0, 1 - brightness) * 230))


class Veil(QWidget):
    def __init__(self, geometry) -> None:  # noqa: ANN001
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(geometry)
        self.layers = veil(DAY_K, 1.0)

    def paintEvent(self, _event) -> None:  # noqa: ANN001, N802
        p = QPainter(self)
        for colour in self.layers:
            p.fillRect(self.rect(), colour)
        p.end()


class NightScreen:
    """One veil per screen, shown only while the evening needs it."""

    def __init__(self) -> None:
        self.veils: list[Veil] = []

    def set(self, kelvin: float, brightness: float) -> None:
        if kelvin >= DAY_K and brightness >= 1.0:
            self.clear()
            return
        if not self.veils:
            self.veils = [Veil(screen.geometry()) for screen in QGuiApplication.screens()]
        layers = veil(kelvin, brightness)
        for v in self.veils:
            if v.layers != layers:
                v.layers = layers
                v.update()
            if not v.isVisible():
                v.show()

    def clear(self) -> None:
        for v in self.veils:
            v.close()
            v.deleteLater()
        self.veils = []


class _VeilBridge(QObject):
    look = Signal(float, float)


class VeilTint:
    """The veil as the engine's last backend: the engine thread posts the
    look to the interface thread, a few times a second (no 60 fps repaints)."""

    name, fps = "veil", 4.0

    def __init__(self, screen: NightScreen | None = None) -> None:
        self.screen = screen or NightScreen()
        self._bridge = _VeilBridge()
        self._bridge.look.connect(self.screen.set, Qt.ConnectionType.QueuedConnection)

    def apply(self, kelvin: float, brightness: float) -> bool:
        self._bridge.look.emit(float(kelvin), float(brightness))
        return True

    def reset(self) -> None:
        self._bridge.look.emit(float(DAY_K), 1.0)


# -- the sheet ------------------------------------------------------------------
def kelvin_colour(kelvin: float, brightness: float = 1.0) -> QColor:
    r, g, b = nocturno.white_point(kelvin)
    return QColor.fromRgbF(r * brightness, g * brightness, b * brightness)


class IntensitySlider(QAbstractButton):
    """A hairline track that warms from left to right and an aluminium knob."""

    moved = Signal(float)  # 0.2 … 1.0 while dragging
    released_at = Signal(float)

    LO, HI = 0.2, 1.0

    def __init__(self, value: float) -> None:
        super().__init__()
        self.value = value
        self.dragging = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setAccessibleName("Intensidad")

    def _x(self, value: float) -> float:
        return 12 + (value - self.LO) / (self.HI - self.LO) * (self.width() - 24)

    def _value(self, x: float) -> float:
        f = (x - 12) / max(1.0, self.width() - 24)
        return round(max(self.LO, min(self.HI, self.LO + f * (self.HI - self.LO))), 2)

    def set_value(self, value: float) -> None:
        self.value = max(self.LO, min(self.HI, value))
        self.update()

    def mousePressEvent(self, ev: Any) -> None:  # noqa: N802
        self.dragging = True
        self.set_value(self._value(ev.position().x()))
        self.moved.emit(self.value)

    def mouseMoveEvent(self, ev: Any) -> None:  # noqa: N802
        if self.dragging:
            v = self._value(ev.position().x())
            if v != self.value:
                self.set_value(v)
                self.moved.emit(self.value)

    def mouseReleaseEvent(self, _ev: Any) -> None:  # noqa: N802
        self.dragging = False
        self.released_at.emit(self.value)

    def keyPressEvent(self, ev: Any) -> None:  # noqa: N802
        step = {Qt.Key.Key_Left: -0.05, Qt.Key.Key_Right: 0.05}.get(ev.key())
        if step is None:
            super().keyPressEvent(ev)
            return
        self.set_value(round(self.value + step, 2))
        self.released_at.emit(self.value)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = self.height() / 2
        grad = QLinearGradient(12, 0, self.width() - 12, 0)
        for f in (0.0, 0.5, 1.0):
            v = self.LO + f * (self.HI - self.LO)
            grad.setColorAt(f, kelvin_colour(nocturno.mix_kelvin(DAY_K, NIGHT_K, v)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(estilo.LINE))
        p.drawRoundedRect(QRectF(12, y - 2, self.width() - 24, 4), 2, 2)
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(12, y - 2, self._x(self.value) - 12, 4), 2, 2)
        x = self._x(self.value)
        p.setBrush(QColor(estilo.ALUMINIUM_HOT if self.dragging else estilo.ALUMINIUM))
        p.setPen(QPen(QColor(estilo.INK), 1))
        p.drawEllipse(QPointF(x, y), 10, 10)
        p.end()


class EveningCurve(QWidget):
    """Tonight from the start of the evening to waking: the screen's colour
    along the strip, the light as its height, a hairline at «now»."""

    def __init__(self, settings: Callable[[], nocturno.Settings], dusk: Callable[[], dt.time | None]) -> None:
        super().__init__()
        self.settings, self.dusk = settings, dusk
        self.now: Callable[[], dt.datetime] = dt.datetime.now
        self.setFixedHeight(72)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self.settings()
        now = self.now()
        t = nocturno.schedule(now, s, self.dusk())
        a = t["start"] - dt.timedelta(minutes=30)
        b = t["bed"] + dt.timedelta(hours=1)
        span = (b - a).total_seconds()
        w, top, h = self.width(), 4.0, 40.0
        path = QPainterPath(QPointF(0, top + h))
        grad = QLinearGradient(0, 0, w, 0)
        steps = 48
        for i in range(steps + 1):
            f = i / steps
            m = nocturno.moment(a + dt.timedelta(seconds=span * f), s, self.dusk())
            grad.setColorAt(f, kelvin_colour(m.kelvin))
            path.lineTo(QPointF(f * w, top + h * (1 - m.brightness) * 1.6))
        path.lineTo(QPointF(w, top + h))
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPath(path)
        p.setFont(estilo.font(8, "regular"))
        for key in ("start", "wind", "bed"):
            x = (t[key] - a).total_seconds() / span * w
            p.setPen(QPen(QColor(estilo.LINE_HOT), 1))
            p.drawLine(QPointF(x, top), QPointF(x, top + h + 4))
            p.setPen(QColor(estilo.SECONDARY))
            p.drawText(QRectF(x - 30, top + h + 8, 60, 16), Qt.AlignmentFlag.AlignCenter, t[key].strftime("%H:%M"))
        if a <= now <= b:
            x = (now - a).total_seconds() / span * w
            p.setPen(QPen(QColor(estilo.TEXT), 1.5))
            p.drawLine(QPointF(x, top - 2), QPointF(x, top + h + 2))
        p.end()


class NightSheet(QWidget):
    """The Night Shift settings: what the «Night» tile opens."""

    WIDTH, HEIGHT = 400, 360

    def __init__(self, get: Callable[[], nocturno.Settings], save: Callable[[nocturno.Settings], None],
                 preview: Callable[[float, float], None], dusk: Callable[[], dt.time | None] = lambda: None) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.get, self.save, self.preview, self.dusk = get, save, preview, dusk
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setWindowTitle("Night Shift")
        s = get()
        col = QVBoxLayout(self)
        col.setContentsMargins(estilo.MARGIN, estilo.MARGIN - 4, estilo.MARGIN, estilo.MARGIN - 4)
        col.setSpacing(estilo.GAP + 4)

        head = QHBoxLayout()
        title = QLabel("Night Shift")
        title.setFont(estilo.font(13, "light", caps=True, spacing=18))
        title.setStyleSheet(f"color: {estilo.TEXT};")
        head.addWidget(title, 1)
        from sergio_escritorio.panel import Switch

        self.switch = Switch(s.on and s.warmth)
        self.switch.setAccessibleName("Night Shift activo")
        self.switch.toggled.connect(self._toggle)
        head.addWidget(self.switch)
        col.addLayout(head)

        row = QHBoxLayout()
        label = QLabel("Intensidad")
        label.setFont(estilo.font(10.5, "regular"))
        label.setStyleSheet(f"color: {estilo.SECONDARY};")
        self.level = QLabel(f"{round(s.intensity * 100)} %")
        self.level.setFont(estilo.font(10.5, "semibold"))
        self.level.setStyleSheet(f"color: {estilo.TEXT};")
        row.addWidget(label, 1)
        row.addWidget(self.level)
        col.addLayout(row)
        self.slider = IntensitySlider(s.intensity)
        self.slider.moved.connect(self._preview)
        self.slider.released_at.connect(self._set_intensity)
        col.addWidget(self.slider)

        self.curve = EveningCurve(self.get, self.dusk)
        col.addWidget(self.curve)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setFont(estilo.font(10, "regular"))
        self.status.setStyleSheet(f"color: {estilo.TEXT};")
        col.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.setSpacing(estilo.GAP)
        self.now_button = QPushButton()
        self.now_button.clicked.connect(self._toggle_now)
        done = QPushButton("Listo")
        done.setObjectName("primary")
        done.clicked.connect(self.hide)
        buttons.addWidget(self.now_button, 1)
        buttons.addWidget(done, 1)
        col.addLayout(buttons)

        note = QLabel("Poca luz desde 3 h antes de dormir (Brown et al., PLOS Biology 2022).")
        note.setWordWrap(True)
        note.setFont(estilo.font(8.5, "regular"))
        note.setStyleSheet(f"color: {estilo.SECONDARY};")
        col.addWidget(note)
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {estilo.TEXT}; border: 1px solid {estilo.LINE};"
            f" border-radius: {estilo.RADIUS_S}px; padding: 8px 12px; font-family: {estilo.css_family()}; }}"
            f"QPushButton:hover {{ border-color: {estilo.LINE_HOT}; background: {estilo.CARD_HOT}; }}"
            f"QPushButton#primary {{ background: {estilo.ALUMINIUM}; color: {estilo.INK}; border: none; }}"
            f"QPushButton#primary:hover {{ background: {estilo.ALUMINIUM_HOT}; }}")
        self.refresh()

    def refresh(self) -> None:
        s = self.get()
        m = nocturno.moment(dt.datetime.now(), s, self.dusk())
        self.status.setText(f"Ahora: {nocturno.PHASE_ES.get(m.phase, m.phase)} · {m.kelvin} K · "
                            f"{round(m.brightness * 100)} % de luz · azul {round(m.blue * 100)} %")
        self.now_button.setText("Volver al horario" if m.phase == "ahora" else "Noche ya")
        self.level.setText(f"{round(s.intensity * 100)} %")
        self.curve.update()

    def _toggle(self, on: bool) -> None:
        s = self.get()
        s.on = s.warmth = on
        if not on:
            s.force_until = ""
        self.save(s)
        self.refresh()

    def _preview(self, value: float) -> None:
        self.level.setText(f"{round(value * 100)} %")
        s = self.get()
        k, b = nocturno.looks(nocturno.set_intensity(s, value))["night"]
        self.preview(k, b)  # how bedtime will look, live while dragging

    def _set_intensity(self, value: float) -> None:
        s = nocturno.set_intensity(self.get(), value)
        self.save(s)  # the saver goes back to the scheduled look, faded
        self.refresh()

    def _toggle_now(self) -> None:
        s = self.get()
        if nocturno.moment(dt.datetime.now(), s, self.dusk()).phase == "ahora":
            s.force_until = ""
        else:
            nocturno.force_now(s)
        self.save(s)
        self.refresh()
        self.switch.setChecked(s.on and s.warmth)

    def open(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.WIDTH // 2, screen.top() + 72)
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(estilo.LINE), 1))
        p.setBrush(QColor(estilo.GLASS))
        p.drawRoundedRect(rect, estilo.RADIUS_L, estilo.RADIUS_L)
        p.end()


__all__ = ["EveningCurve", "IntensitySlider", "NightScreen", "NightSheet", "VeilTint", "kelvin_colour", "veil"]

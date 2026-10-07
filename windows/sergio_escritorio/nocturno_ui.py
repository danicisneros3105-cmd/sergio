"""The screen at night when the graphics driver refuses a warm gamma ramp:
a click-through amber and dark veil over every screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from sergio_escritorio.nocturno import DAY_K, NIGHT_K


def veil(kelvin: float, brightness: float) -> tuple[QColor, QColor]:
    """(warm amber, dark) layers: warmer as kelvin falls, darker as light falls."""
    warm = max(0.0, min(1.0, (DAY_K - kelvin) / (DAY_K - NIGHT_K)))
    return QColor(255, 140, 30, int(warm * 70)), QColor(0, 0, 0, int(max(0.0, 1 - brightness) * 230))


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
        for v in self.veils:
            v.layers = veil(kelvin, brightness)
            v.show()
            v.update()

    def clear(self) -> None:
        for v in self.veils:
            v.close()
            v.deleteLater()
        self.veils = []


__all__ = ["NightScreen", "veil"]

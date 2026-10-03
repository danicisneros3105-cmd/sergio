"""'Personalizar a Sergio': theme, eyes, size next to the cursor, and voice."""

from __future__ import annotations

import time
from typing import Any, Callable

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sergio_escritorio.character import THEMES, draw_character, set_theme
from sergio_escritorio.neural_voice import VOICES

SIZES = {"Pequeño": 7.0, "Normal": 9.0, "Grande": 12.0}
LOCAL_VOICE = "Voz local (sin internet)"

STYLE = """
QDialog { background: #121214; color: #f2f2f4; }
QLabel { color: #c7c7cc; font-size: 13px; }
QLabel#title { color: #f2f2f4; font-size: 17px; font-weight: 600; }
QComboBox, QCheckBox { color: #f2f2f4; font-size: 13px; }
QComboBox { background: #1f1f22; border: 1px solid #2c2c30; border-radius: 8px;
            padding: 6px 10px; min-width: 190px; }
QComboBox QAbstractItemView { background: #1f1f22; color: #f2f2f4;
            selection-background-color: #0a6cff; }
QPushButton { background: #f2f2f4; color: #121214; border: none; border-radius: 16px;
              padding: 8px 18px; font-weight: 600; }
QPushButton#secondary { background: #2a2a2e; color: #f2f2f4; }
"""


class OrbPreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(150, 150)
        self.state = "idle"
        self._t0 = time.monotonic()
        timer = QTimer(self)
        timer.timeout.connect(self.update)
        timer.start(16)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        t = time.monotonic() - self._t0
        draw_character(p, QPointF(75, 75), 40, self.state, t)
        p.end()


class PersonalizeDialog(QDialog):
    def __init__(self, config: dict, on_save: Callable[[dict], None]) -> None:
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Personalizar a Sergio")
        self.setStyleSheet(STYLE)
        self.config = config
        self.on_save = on_save
        original = (config.get("theme", "Océano"), config.get("eyes", True))

        title = QLabel("Personalizar a Sergio")
        title.setObjectName("title")
        self.preview = OrbPreview()

        self.theme = QComboBox()
        self.theme.addItems(list(THEMES))
        self.theme.setCurrentText(original[0])
        self.eyes = QCheckBox("Mostrar sus ojos")
        self.eyes.setChecked(bool(original[1]))
        self.size = QComboBox()
        self.size.addItems(list(SIZES))
        current = next(
            (k for k, v in SIZES.items() if v == config.get("cursor_size", 9.0)),
            "Normal",
        )
        self.size.setCurrentText(current)
        self.voice = QComboBox()
        for voice_id, label in VOICES:
            self.voice.addItem(label, voice_id)
        self.voice.addItem(LOCAL_VOICE, "")
        index = self.voice.findData(config.get("voice", VOICES[0][0]))
        self.voice.setCurrentIndex(max(0, index))

        for widget in (self.theme, self.eyes):
            signal = (
                widget.currentTextChanged
                if isinstance(widget, QComboBox)
                else widget.toggled
            )
            signal.connect(
                lambda *_: set_theme(self.theme.currentText(), self.eyes.isChecked())
            )

        form = QFormLayout()
        form.addRow("Colores", self.theme)
        form.addRow("", self.eyes)
        form.addRow("Tamaño junto al cursor", self.size)
        form.addRow("Voz", self.voice)

        save = QPushButton("Guardar")
        save.clicked.connect(self._save)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(lambda: (set_theme(*original), self.reject()))
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        top = QHBoxLayout()
        top.addWidget(self.preview)
        top.addLayout(form)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addLayout(top)
        layout.addLayout(buttons)
        set_theme(self.theme.currentText(), self.eyes.isChecked())  # live preview

    def _save(self) -> None:
        self.config.update(
            theme=self.theme.currentText(),
            eyes=self.eyes.isChecked(),
            cursor_size=SIZES[self.size.currentText()],
            voice=self.voice.currentData() or "",
        )
        self.on_save(self.config)
        self.accept()


__all__ = ["PersonalizeDialog", "SIZES"]

"""The «Bloqueo» window: apps, websites and searches, and the big switch."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sergio_escritorio.bloqueo import Store

FONT = ["Segoe UI Variable Display", "SF Pro Display", "Segoe UI"]
STYLE = """
QWidget#block { background: #0f1012; }
QLabel { color: #f5f5f7; }
QLabel#hint { color: #8e8e93; font-size: 12px; }
QLabel#col { color: #8e8e93; font-size: 11px; font-weight: 600; letter-spacing: 0.4px; }
QListWidget { background: #1c1c1e; color: #f5f5f7; border: none; border-radius: 14px; padding: 6px;
              font-size: 13px; }
QListWidget::item { padding: 6px 8px; border-radius: 8px; }
QListWidget::item:selected { background: #2c2c2e; }
QLineEdit { background: #1c1c1e; color: #f5f5f7; border: 1px solid #2c2c2e; border-radius: 12px;
            padding: 7px 10px; }
QPushButton { background: #2c2c2e; color: #f5f5f7; border: none; border-radius: 12px; padding: 7px 12px;
              font-weight: 600; }
QPushButton#on { background: #ff453a; color: white; font-size: 14px; padding: 11px; border-radius: 16px; }
QPushButton#off { background: #30d158; color: #0f1012; font-size: 14px; padding: 11px; border-radius: 16px; }
"""
COLUMNS = (
    ("apps", "APPS", "Discord, Steam, configuración…"),
    ("sites", "WEBS", "youtube.com, tiktok.com…"),
    ("words", "BÚSQUEDAS", "palabras a evitar…"),
)


def _font(size: float, bold: bool = False) -> QFont:
    f = QFont(FONT)
    f.setPointSizeF(size)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


class BlockWindow(QWidget):
    def __init__(
        self,
        store: Store,
        turn_on: Callable[[], str],
        turn_off: Callable[[], str],
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("block")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Sergio · Bloqueo")
        self.store, self.turn_on, self.turn_off = store, turn_on, turn_off
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        title = QLabel("Bloqueo")
        title.setFont(_font(20, True))
        lay.addWidget(title)
        hint = QLabel(
            "Lo que pongas aquí queda fuera mientras el bloqueo está activo. Las webs se bloquean en "
            "Chrome, Edge y Brave; las apps se cierran al abrirse; una búsqueda con estas palabras "
            "cierra su pestaña. Solo tu cara lo desactiva."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        cols = QHBoxLayout()
        cols.setSpacing(12)
        self.lists: dict[str, QListWidget] = {}
        self.entries: dict[str, QLineEdit] = {}
        for kind, label, placeholder in COLUMNS:
            col = QVBoxLayout()
            head = QLabel(label)
            head.setObjectName("col")
            col.addWidget(head)
            items = QListWidget()
            self.lists[kind] = items
            col.addWidget(items, 1)
            row = QHBoxLayout()
            entry = QLineEdit()
            entry.setPlaceholderText(placeholder)
            entry.returnPressed.connect(lambda k=kind: self._add(k))
            self.entries[kind] = entry
            row.addWidget(entry, 1)
            plus = QPushButton("+")
            plus.clicked.connect(lambda _c=False, k=kind: self._add(k))
            row.addWidget(plus)
            minus = QPushButton("−")
            minus.clicked.connect(lambda _c=False, k=kind: self._remove(k))
            row.addWidget(minus)
            col.addLayout(row)
            cols.addLayout(col, 1)
        lay.addLayout(cols, 1)
        self.switch = QPushButton()
        self.switch.clicked.connect(self._toggle)
        lay.addWidget(self.switch)
        self.note = QLabel("")
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.resize(760, 520)
        self.refresh()

    def refresh(self) -> None:
        bl = self.store.list
        for kind, items in self.lists.items():
            items.clear()
            items.addItems(getattr(bl, kind))
        self.switch.setObjectName("on" if not bl.on else "off")
        self.switch.setText("Activar el bloqueo" if not bl.on else "Bloqueo activo · quitar (con tu cara)")
        self.switch.setStyleSheet(self.styleSheet())

    def _add(self, kind: str) -> None:
        entry = self.entries[kind]
        added = self.store.list.add(kind, entry.text())
        if added:
            self.store.save()
            entry.clear()
            if self.store.list.on and kind == "sites":
                self.note.setText(self.turn_on())
        self.refresh()

    def _remove(self, kind: str) -> None:
        item = self.lists[kind].currentItem()
        if item is None:
            return
        if self.store.list.on:
            self.note.setText("Para quitar algo de la lista, primero desactiva el bloqueo (con tu cara).")
            return
        self.store.list.remove(kind, item.text())
        self.store.save()
        self.refresh()

    def _toggle(self) -> None:
        self.note.setText(self.turn_off() if self.store.list.on else self.turn_on())
        self.refresh()

    def open(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()


__all__ = ["BlockWindow"]

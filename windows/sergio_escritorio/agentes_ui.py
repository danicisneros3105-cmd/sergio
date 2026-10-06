"""The «Agentes» window: the pro agents, yours, give one a job, create one."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sergio_escritorio.agentes import Agents, describe

STYLE = """
QWidget#agents { background: #0f1012; }
QLabel { color: #f5f5f7; }
QLabel#hint { color: #8e8e93; font-size: 12px; }
QListWidget { background: #1c1c1e; color: #f5f5f7; border: none; border-radius: 14px; padding: 6px; font-size: 13px; }
QListWidget::item { padding: 8px 10px; border-radius: 10px; margin-bottom: 2px; }
QListWidget::item:selected { background: #0a84ff; color: white; }
QLineEdit { background: #1c1c1e; color: #f5f5f7; border: 1px solid #2c2c2e; border-radius: 12px; padding: 9px 12px; }
QPushButton { background: #0a84ff; color: white; border: none; border-radius: 12px; padding: 9px 14px; font-weight: 600; }
QPushButton#plain { background: #2c2c2e; }
"""


class AgentsWindow(QWidget):
    def __init__(
        self,
        agents: Agents,
        run: Callable[[dict[str, Any], str], str],
        create: Callable[[str], str],
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("agents")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Sergio · Agentes")
        self.agents, self.run, self.create = agents, run, create
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        title = QLabel("Agentes")
        font = QFont(["Segoe UI Variable Display", "Segoe UI"])
        font.setPointSizeF(20)
        font.setWeight(QFont.Weight.DemiBold)
        title.setFont(font)
        lay.addWidget(title)
        hint = QLabel("Elige un agente y dale un trabajo: lo hace en segundo plano y lo verás en el notch.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        lay.addWidget(self.list, 1)
        job = QHBoxLayout()
        self.job = QLineEdit()
        self.job.setPlaceholderText("¿Qué hace? p. ej. compara las RTX 5070 y 5080 para Blender")
        self.job.returnPressed.connect(self._run)
        job.addWidget(self.job, 1)
        go = QPushButton("Encargar")
        go.clicked.connect(self._run)
        job.addWidget(go)
        lay.addLayout(job)
        new = QHBoxLayout()
        self.new = QLineEdit()
        self.new.setPlaceholderText("Crear agente: p. ej. cada lunes a las 8 resúmeme las noticias de IA")
        self.new.returnPressed.connect(self._create)
        new.addWidget(self.new, 1)
        make = QPushButton("Crear")
        make.setObjectName("plain")
        make.clicked.connect(self._create)
        new.addWidget(make)
        lay.addLayout(new)
        self.note = QLabel("")
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.resize(620, 620)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for agent in self.agents.all():
            mark = "PRO · " if agent.get("pro") else ""
            item = QListWidgetItem(f"{mark}{describe(agent)}")
            item.setData(Qt.ItemDataRole.UserRole, agent["nombre"])
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _run(self) -> None:
        item = self.list.currentItem()
        text = self.job.text().strip()
        if item is None or not text:
            return
        agent = self.agents.find(item.data(Qt.ItemDataRole.UserRole))
        if agent is not None:
            self.note.setText(self.run(agent, text))
            self.job.clear()

    def _create(self) -> None:
        text = self.new.text().strip()
        if text:
            self.note.setText("Diseñando el agente…")
            self.note.setText(self.create(text))
            self.new.clear()
            self.refresh()

    def open(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()


__all__ = ["AgentsWindow"]

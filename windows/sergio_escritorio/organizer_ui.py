"""Organizer widgets: sticky notes on the desktop, the alarm that rings and
the «Organizador» window (alarms, notes, reminders, homework)."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sergio_escritorio.organizer import NOTE_COLORS, Alarm, Alarms, Note, Notes

FONT = ["Segoe UI Variable Display", "SF Pro Display", "Segoe UI"]


def _font(size: float, bold: bool = False) -> QFont:
    f = QFont(FONT)
    f.setPointSizeF(size)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


# -- sticky notes ------------------------------------------------------------------
class StickyNote(QWidget):
    """One paper-like note: drag it by the top, type in it, change colour."""

    def __init__(self, note: Note, store: Notes, on_close: Callable[[str], None] | None = None) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if note.on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.note, self.store, self.on_close = note, store, on_close
        self._drag: QPoint | None = None
        self.edit = QTextEdit(self)
        self.edit.setPlainText(note.text)
        self.edit.setFrameStyle(0)
        self.edit.setFont(_font(11))
        self.edit.setStyleSheet("background: transparent; color: #2b2b2b;")
        self.edit.textChanged.connect(self._typed)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(lambda: self.store.update(self.note.id, text=self.edit.toPlainText()))
        self.resize(note.w, note.h)
        self.edit.setGeometry(14, 30, note.w - 28, note.h - 42)
        self._place()

    def _place(self) -> None:
        if self.note.x >= 0 and self.note.y >= 0:
            self.move(self.note.x, self.note.y)
            return
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 800)
        k = (-self.note.x - 1) % 8
        self.move(geo.right() - self.note.w - 40 - k * 28, geo.top() + 60 + k * 34)

    def _typed(self) -> None:
        self._save_timer.start(600)

    def colour(self) -> QColor:
        return QColor(NOTE_COLORS.get(self.note.color, NOTE_COLORS["amarillo"]))

    def _buttons(self) -> tuple[QRect, QRect]:
        return QRect(self.width() - 30, 6, 20, 20), QRect(self.width() - 56, 6, 20, 20)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i in range(5):  # soft shadow
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 10))
            p.drawRoundedRect(QRect(4 - i, 6 - i + 2, self.width() - 8 + 2 * i, self.height() - 10 + 2 * i), 10, 10)
        body = QRect(4, 4, self.width() - 8, self.height() - 10)
        p.setBrush(self.colour())
        p.drawRoundedRect(body, 10, 10)
        p.setBrush(self.colour().darker(108))
        p.drawRoundedRect(QRect(4, 4, self.width() - 8, 24), 10, 10)
        p.drawRect(QRect(4, 16, self.width() - 8, 12))
        close, colour = self._buttons()
        p.setPen(QPen(QColor(60, 60, 60, 170), 1.6))
        p.drawLine(close.topLeft() + QPoint(6, 6), close.bottomRight() - QPoint(6, 6))
        p.drawLine(close.topRight() + QPoint(-6, 6), close.bottomLeft() + QPoint(6, -6))
        p.setBrush(self.colour().darker(130))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(colour.adjusted(5, 5, -5, -5))
        p.setFont(_font(7.5, True))
        p.setPen(QColor(60, 60, 60, 160))
        p.drawText(QRect(14, 6, 150, 18), Qt.AlignmentFlag.AlignVCenter, time.strftime("%d/%m", time.localtime(self.note.created)))

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        pos = event.position().toPoint()
        close, colour = self._buttons()
        if close.contains(pos):
            self.store.remove(self.note.id)
            if self.on_close:
                self.on_close(self.note.id)
            self.close()
            return
        if colour.contains(pos):
            names = list(NOTE_COLORS)
            self.note.color = names[(names.index(self.note.color) + 1) % len(names)] if self.note.color in names else names[0]
            self.store.update(self.note.id, color=self.note.color)
            self.update()
            return
        self._drag = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _event: Any) -> None:  # noqa: N802
        if self._drag is not None:
            self._drag = None
            self.store.update(self.note.id, x=self.x(), y=self.y())


class NotesBoard:
    """All sticky notes on the desktop."""

    def __init__(self, store: Notes) -> None:
        self.store = store
        self.widgets: dict[str, StickyNote] = {}

    def show_all(self) -> int:
        for note in self.store.items:
            self.show(note)
        return len(self.store.items)

    def show(self, note: Note) -> StickyNote:
        widget = self.widgets.get(note.id)
        if widget is None:
            widget = StickyNote(note, self.store, on_close=lambda nid: self.widgets.pop(nid, None))
            self.widgets[note.id] = widget
        widget.show()
        widget.raise_()
        return widget

    def hide_all(self) -> None:
        for widget in list(self.widgets.values()):
            widget.hide()

    def remove(self, note_id: str) -> None:
        widget = self.widgets.pop(note_id, None)
        if widget is not None:
            widget.close()
        self.store.remove(note_id)


# -- the alarm ringing ---------------------------------------------------------------
class AlarmCard(QWidget):
    """Big card while an alarm rings: «Posponer» or «Detener»."""

    def __init__(self, alarm: Alarm, on_snooze: Callable[[], None], on_stop: Callable[[], None]) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.alarm = alarm
        self._t0 = time.monotonic()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 28)
        clock = QLabel(f"{alarm.hour:02d}:{alarm.minute:02d}")
        clock.setFont(_font(44, True))
        clock.setStyleSheet("color: white;")
        clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(alarm.label or "Alarma")
        label.setFont(_font(14))
        label.setStyleSheet("color: rgba(255,255,255,0.85);")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout()
        snooze = QPushButton(f"Posponer {5} min")
        stop = QPushButton("Detener")
        for b, bg in ((snooze, "rgba(255,255,255,0.18)"), (stop, "#FF9F0A")):
            b.setFont(_font(12, True))
            b.setMinimumHeight(44)
            b.setStyleSheet(f"QPushButton{{background:{bg};color:white;border:none;border-radius:22px;padding:0 24px;}}")
        snooze.clicked.connect(lambda: (on_snooze(), self.close()))
        stop.clicked.connect(lambda: (on_stop(), self.close()))
        row.addWidget(snooze)
        row.addWidget(stop)
        lay.addWidget(clock)
        lay.addWidget(label)
        lay.addSpacing(10)
        lay.addLayout(row)
        self.resize(420, 250)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - 210, geo.top() + 80)
        self._pulse = QTimer(self)
        self._pulse.timeout.connect(self.update)
        self._pulse.start(50)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        import math

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = 0.5 + 0.5 * math.sin((time.monotonic() - self._t0) * 4)
        p.setPen(QPen(QColor(255, 159, 10, int(80 + 120 * glow)), 2))
        p.setBrush(QColor(28, 28, 30, 235))
        p.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 28, 28)


def ring_sound() -> None:
    """A short chime (Windows), or the system beep."""
    try:
        import winsound  # type: ignore[import-not-found]

        winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:  # noqa: BLE001 — not Windows
        from PySide6.QtWidgets import QApplication

        QApplication.beep()


# -- the organizer window -------------------------------------------------------------
STYLE = """
QWidget#org { background: #1C1C1E; }
QLabel { color: #F5F5F7; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #8E8E93; padding: 8px 16px; font-size: 13px; }
QTabBar::tab:selected { color: white; border-bottom: 2px solid #0A84FF; }
QListWidget { background: #2C2C2E; color: #F5F5F7; border: none; border-radius: 12px; padding: 6px; font-size: 13px; }
QListWidget::item { padding: 8px; border-radius: 8px; }
QListWidget::item:selected { background: #3A3A3C; }
QLineEdit, QSpinBox, QComboBox { background: #2C2C2E; color: white; border: none; border-radius: 8px; padding: 6px 8px; font-size: 13px; }
QPushButton { background: #0A84FF; color: white; border: none; border-radius: 8px; padding: 7px 14px; font-size: 13px; }
QPushButton#plain { background: #3A3A3C; }
"""


class OrganizerWindow(QWidget):
    def __init__(
        self,
        alarms: Alarms,
        notes: Notes,
        board: NotesBoard,
        reminders: Any = None,
        homework: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("org")
        self.setWindowTitle("Sergio · Organizador")
        self.setStyleSheet(STYLE)
        self.alarms, self.notes, self.board, self.reminders = alarms, notes, board, reminders
        self.homework = homework or (lambda: [])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        title = QLabel("Organizador")
        title.setFont(_font(20, True))
        lay.addWidget(title)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self._alarm_tab()
        self._notes_tab()
        self._reminders_tab()
        self._homework_tab()
        self.resize(620, 560)
        self.refresh()

    # alarms
    def _alarm_tab(self) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        self.alarm_list = QListWidget()
        v.addWidget(self.alarm_list)
        row = QHBoxLayout()
        self.hour, self.minute = QSpinBox(), QSpinBox()
        self.hour.setRange(0, 23)
        self.minute.setRange(0, 59)
        self.hour.setValue(7)
        self.days = QComboBox()
        self.days.addItems(["Una vez", "Todos los días", "Lunes a viernes", "Fines de semana"])
        self.alarm_label = QLineEdit()
        self.alarm_label.setPlaceholderText("Etiqueta (opcional)")
        add = QPushButton("Añadir")
        add.clicked.connect(self._add_alarm)
        for w in (self.hour, QLabel(":"), self.minute, self.days, self.alarm_label, add):
            row.addWidget(w)
        v.addLayout(row)
        tools = QHBoxLayout()
        toggle, delete = QPushButton("Activar / desactivar"), QPushButton("Borrar")
        toggle.setObjectName("plain")
        delete.setObjectName("plain")
        toggle.clicked.connect(lambda: self._selected_alarm(lambda a: self.alarms.toggle(a)))
        delete.clicked.connect(lambda: self._selected_alarm(self.alarms.remove))
        tools.addWidget(toggle)
        tools.addWidget(delete)
        tools.addStretch()
        v.addLayout(tools)
        self.tabs.addTab(page, "Alarmas")

    def _add_alarm(self) -> None:
        days = [[], list(range(7)), [0, 1, 2, 3, 4], [5, 6]][self.days.currentIndex()]
        self.alarms.add(self.hour.value(), self.minute.value(), days, self.alarm_label.text())
        self.alarm_label.clear()
        self.refresh()

    def _selected_alarm(self, fn: Callable[[str], Any]) -> None:
        item = self.alarm_list.currentItem()
        if item is not None:
            fn(item.data(Qt.ItemDataRole.UserRole))
            self.refresh()

    # notes
    def _notes_tab(self) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        self.note_list = QListWidget()
        v.addWidget(self.note_list)
        row = QHBoxLayout()
        self.note_text = QLineEdit()
        self.note_text.setPlaceholderText("Escribe una nota…")
        self.note_text.returnPressed.connect(self._add_note)
        self.note_color = QComboBox()
        self.note_color.addItems(list(NOTE_COLORS))
        add = QPushButton("Pegar en el escritorio")
        add.clicked.connect(self._add_note)
        row.addWidget(self.note_text, 1)
        row.addWidget(self.note_color)
        row.addWidget(add)
        v.addLayout(row)
        tools = QHBoxLayout()
        show, delete = QPushButton("Mostrar todas"), QPushButton("Borrar")
        show.setObjectName("plain")
        delete.setObjectName("plain")
        show.clicked.connect(self.board.show_all)
        delete.clicked.connect(self._delete_note)
        tools.addWidget(show)
        tools.addWidget(delete)
        tools.addStretch()
        v.addLayout(tools)
        self.tabs.addTab(page, "Notas")

    def _add_note(self) -> None:
        text = self.note_text.text().strip()
        if text:
            self.board.show(self.notes.add(text, self.note_color.currentText()))
            self.note_text.clear()
            self.refresh()

    def _delete_note(self) -> None:
        item = self.note_list.currentItem()
        if item is not None:
            self.board.remove(item.data(Qt.ItemDataRole.UserRole))
            self.refresh()

    # reminders and homework
    def _reminders_tab(self) -> None:
        self.reminder_list = QListWidget()
        self.tabs.addTab(self.reminder_list, "Recordatorios")

    def _homework_tab(self) -> None:
        self.homework_list = QListWidget()
        self.tabs.addTab(self.homework_list, "Tareas y exámenes")

    def refresh(self) -> None:
        self.alarm_list.clear()
        for a in self.alarms.items:
            item = QListWidgetItem(("⏰ " if a.enabled else "○ ") + a.describe())
            item.setData(Qt.ItemDataRole.UserRole, a.id)
            if not a.enabled:
                item.setForeground(QColor(142, 142, 147))
            self.alarm_list.addItem(item)
        self.note_list.clear()
        for n in self.notes.items:
            item = QListWidgetItem(f"● {n.text[:80]}")
            item.setForeground(QColor(NOTE_COLORS.get(n.color, "#FFE873")))
            item.setData(Qt.ItemDataRole.UserRole, n.id)
            self.note_list.addItem(item)
        self.reminder_list.clear()
        if self.reminders is not None:
            for r in self.reminders.pending():
                when = datetime.fromtimestamp(r.due).strftime("%d/%m %H:%M")
                self.reminder_list.addItem(f"🔔 {when} · {r.text or 'recordatorio'}")
        if not self.reminder_list.count():
            self.reminder_list.addItem("Sin recordatorios. Di «recuérdame en 20 minutos…».")
        self.homework_list.clear()
        for h in self.homework():
            self.homework_list.addItem(f"{'📝' if h.get('tipo') == 'tarea' else '📚'} {h.get('fecha') or 'sin fecha'} · {h.get('materia', '')}: {h.get('titulo', '')}")
        if not self.homework_list.count():
            self.homework_list.addItem("Di «revisa mi plataforma escolar» y apunto tus tareas y exámenes.")

    def open(self, tab: int = 0) -> None:
        self.refresh()
        self.tabs.setCurrentIndex(tab)
        self.show()
        self.raise_()
        self.activateWindow()


__all__ = ["AlarmCard", "NotesBoard", "OrganizerWindow", "StickyNote", "ring_sound"]

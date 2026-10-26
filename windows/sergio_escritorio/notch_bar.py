"""The notch's quick bar: small tasks without opening the control center.

A click on the notch grows it, like Apple's island, into a black bar with one
line to type in and a row of chips for the usual small jobs (remind me,
search, open, run in the background). Enter sends the line through the same
path as the control center's chat (instant commands first, then the agent),
the bar folds back into the pill and the answer shows there. Esc, a click
elsewhere or an empty Enter closes it. It looks like the rest of the app:
black, white, one typeface (estilo.py), cards and a white pill button.
"""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from sergio_escritorio import estilo
from sergio_escritorio.character import draw_character
from sergio_escritorio.notch import notch_path

BAR_W, BAR_H = 560.0, 132.0
START_W, START_H = 132.0, 36.0  # the compact pill it grows from
MARGIN = 20  # transparent room round the shape, for the ears
GRACE_S = 0.4  # ignore the deactivation that comes with opening

# (icon, label, what it starts the line with)
CHIPS: list[tuple[str, str, str]] = [
    ("bell", "Recordar", "Recuérdame "),
    ("search", "Buscar", "Busca "),
    ("app-window", "Abrir", "Abre "),
    ("layers", "Tarea larga", "En segundo plano, "),
]
FIELD_H = 44  # the line and the round send button
CHIP_H = 30

# Every round thing has radius = half its height: Qt draws a square corner
# when the radius is larger (why the old buttons looked like boxes).
STYLE = f"""
QLineEdit {{ background: {estilo.CARD}; color: {estilo.TEXT}; border: 1px solid {estilo.LINE};
  border-radius: {FIELD_H // 2}px; padding: 0 18px; min-height: {FIELD_H - 2}px; max-height: {FIELD_H - 2}px;
  font-family: {estilo.css_family()}; font-size: 14px; selection-background-color: {estilo.LINE_HOT}; }}
QLineEdit:focus {{ border: 1px solid {estilo.LINE_HOT}; }}
QPushButton#chip {{ background: {estilo.GLASS}; color: {estilo.SECONDARY}; border: 1px solid {estilo.LINE};
  border-radius: {CHIP_H // 2}px; padding: 0 12px 0 10px; min-height: {CHIP_H - 2}px; max-height: {CHIP_H - 2}px;
  font-family: {estilo.css_family()}; font-size: 12px; text-align: left; }}
QPushButton#chip:hover {{ background: {estilo.CARD_HOT}; color: {estilo.TEXT}; }}
QPushButton#round {{ background: {estilo.GLASS}; border: 1px solid {estilo.LINE}; border-radius: {CHIP_H // 2}px; }}
QPushButton#round:hover {{ background: {estilo.CARD_HOT}; }}
QPushButton#send {{ background: {estilo.BLUE}; border: none; border-radius: {FIELD_H // 2}px; }}
QPushButton#send:hover {{ background: {estilo.BLUE_HOT}; }}
QToolTip {{ background: {estilo.CARD}; color: {estilo.TEXT}; border: 1px solid {estilo.LINE}; padding: 4px 8px; }}
"""


class NotchBar(QWidget):
    def __init__(
        self,
        *,
        on_submit: Callable[[str], None],
        on_talk: Callable[[], None] | None = None,
        on_panel: Callable[[], None] | None = None,
        reduced_motion: Callable[[], bool] = lambda: False,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.on_submit = on_submit
        self.on_talk = on_talk
        self.on_panel = on_panel
        self.reduced_motion = reduced_motion  # asked each time: the setting can change
        self._opened_at = 0.0
        self._grow = 1.0  # 0 = the pill, 1 = the open bar
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._set_grow)
        self._anim.finished.connect(self._after_anim)
        self._closing = False

        self.setFixedSize(int(BAR_W) + 2 * MARGIN, int(BAR_H) + MARGIN)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Pídele algo a Sergio…")
        self.entry.returnPressed.connect(self.submit)
        from PySide6.QtCore import QSize

        from sergio_escritorio.iconos import icon

        send = QPushButton()
        send.setObjectName("send")
        send.setIcon(icon("arrow-up", estilo.TEXT, 20))
        send.setIconSize(QSize(20, 20))
        send.setFixedSize(FIELD_H, FIELD_H)
        send.setToolTip("Enviar")
        send.setAccessibleName("Enviar")
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self.submit)

        row = QHBoxLayout()
        row.setSpacing(estilo.GAP)
        row.addSpacing(34)  # room for the orb
        row.addWidget(self.entry, 1)
        row.addWidget(send)

        chips = QHBoxLayout()
        chips.setSpacing(estilo.GAP)
        chips.addSpacing(34)
        self.chips: list[QPushButton] = []
        for name, label, prefix in CHIPS:
            chip = QPushButton(label)
            chip.setObjectName("chip")
            chip.setIcon(icon(name, estilo.SECONDARY, 14))
            chip.setIconSize(QSize(14, 14))
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, p=prefix: self.start_with(p))
            chips.addWidget(chip)
            self.chips.append(chip)
        chips.addStretch(1)
        for name, tip, action in (("mic", "Hablar", self._talk), ("sliders", "Centro de control", self._panel)):
            button = QPushButton()
            button.setObjectName("round")
            button.setIcon(icon(name, estilo.TEXT, 15))
            button.setIconSize(QSize(15, 15))
            button.setFixedSize(CHIP_H, CHIP_H)
            button.setToolTip(tip)
            button.setAccessibleName(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(action)
            chips.addWidget(button)
        self._controls = [self.entry, send, *self.chips]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            MARGIN + estilo.PAD + 4, 36, MARGIN + estilo.PAD + 4, estilo.PAD + 2
        )
        layout.setSpacing(estilo.GAP + 4)
        layout.addLayout(row)
        layout.addLayout(chips)
        self._body = [row, chips]

    # -- behaviour ---------------------------------------------------------------
    def start_with(self, prefix: str) -> None:
        self.entry.setText(prefix)
        self.entry.setFocus()
        self.entry.setCursorPosition(len(prefix))

    def submit(self) -> None:
        text = self.entry.text().strip()
        self.entry.clear()
        self.close_bar()
        if text:
            self.on_submit(text)

    def _talk(self) -> None:
        self.close_bar()
        if self.on_talk is not None:
            self.on_talk()

    def _panel(self) -> None:
        self.close_bar()
        if self.on_panel is not None:
            self.on_panel()

    def toggle(self) -> None:
        if self.isVisible() and not self._closing:
            self.close_bar()
        else:
            self.open_bar()

    def open_bar(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            self.move(geo.x() + (geo.width() - self.width()) // 2, geo.y())
        self._opened_at = time.monotonic()
        self._closing = False
        self.entry.clear()
        self._run(1.0 if self.reduced_motion() else 0.0, 1.0, 320)
        self.show()
        self.raise_()
        self.activateWindow()
        self.entry.setFocus()

    def close_bar(self) -> None:
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        self._show_controls(False)
        self._run(self._grow, 1.0 if self.reduced_motion() else 0.0, 220)

    def _run(self, start: float, end: float, ms: int) -> None:
        self._anim.stop()
        self._set_grow(start)
        if start == end:
            self._after_anim()
            return
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setDuration(ms)
        self._anim.start()

    def _set_grow(self, value: float) -> None:
        self._grow = float(value)
        self._show_controls(self._grow > 0.85 and not self._closing)
        self.update()

    def _after_anim(self) -> None:
        if self._closing:
            self.hide()
            self._closing = False
        else:
            self._show_controls(True)

    def _show_controls(self, on: bool) -> None:
        for w in self._controls:
            w.setVisible(on)
        for button in self.findChildren(QPushButton):
            button.setVisible(on)

    def keyPressEvent(self, ev) -> None:  # noqa: ANN001, N802 (Qt API)
        if ev.key() == Qt.Key.Key_Escape:
            self.close_bar()
        else:
            super().keyPressEvent(ev)

    def event(self, ev) -> bool:  # noqa: ANN001
        # Like the control center: a click elsewhere closes it.
        if (
            ev.type() == ev.Type.WindowDeactivate
            and time.monotonic() - self._opened_at > GRACE_S
        ):
            QTimer.singleShot(120, self._close_if_inactive)
        return super().event(ev)

    def _close_if_inactive(self) -> None:
        if self.isVisible() and not self.isActiveWindow():
            self.close_bar()

    # -- drawing -----------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: ANN001, N802 (Qt API)
        k = self._grow
        # An ease that overshoots a little, like the notch's own spring.
        e = 1 + 1.4 * (k - 1) ** 3 + 0.4 * (k - 1) ** 2 if k < 1 else 1.0
        w = START_W + (BAR_W - START_W) * k
        h = START_H + (BAR_H - START_H) * max(0.0, min(1.1, e))
        rect = QRectF((self.width() - w) / 2, 0, w, h)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(estilo.INK))
        p.drawPath(notch_path(rect))
        if k > 0.5:
            p.setOpacity(min(1.0, (k - 0.5) * 2))
            draw_character(
                p,
                QPointF(rect.left() + estilo.PAD + 15, rect.top() + 36 + FIELD_H / 2),
                11.0,
                "idle",
                time.monotonic(),
                QPointF(0, 0),
            )

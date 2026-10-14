"""A calm native confirmation sheet. Only the OS verdict grants consent."""

from __future__ import annotations

import math
import threading
import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from sergio_escritorio import estilo
from sergio_escritorio.faceid_anim import FaceIDGlyph
from sergio_escritorio.platform_auth import Consent, verify


class ConsentDialog(QDialog):
    completed = Signal(object)

    def __init__(self, request: str, *, verifier=verify, reduce_motion: bool = False):
        super().__init__()
        self.verifier = verifier
        self.reduce_motion = reduce_motion
        self.cancelled = threading.Event()
        self.verified = False
        self.checking = False
        self.started = time.monotonic()
        self.request = request
        long_request = len(self.request) > 240 or "\n" in self.request
        self.setWindowTitle("Confirmar con Windows Hello")
        QTimer.singleShot(60_000, self.reject)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(400, 620 if long_request else 440)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 164, 32, 28)
        layout.setSpacing(12)
        title = QLabel("Confirmar acción")
        title.setFont(estilo.font(21, "light"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        action = QLabel("Revise la acción completa:" if long_request else self.request)
        action.setTextFormat(Qt.TextFormat.PlainText)
        action.setWordWrap(True)
        action.setAlignment(Qt.AlignmentFlag.AlignCenter)
        action.setFont(estilo.font(11))
        layout.addWidget(action)
        if long_request:
            details = QPlainTextEdit(self.request)
            details.setReadOnly(True)
            details.setMinimumHeight(140)
            details.setMaximumHeight(160)
            details.setFont(estilo.font(10))
            details.setStyleSheet("color:#eef1f7;background:#18212d;border:1px solid #323c4a;border-radius:8px")
            layout.addWidget(details)
        self.detail = QLabel(
            "Windows Hello · rostro, huella o PIN\nLa cámara de Sergio no autoriza esta acción."
        )
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setFont(estilo.font(9))
        self.detail.setStyleSheet("color:#9ba5b4")
        layout.addWidget(self.detail)
        layout.addStretch()
        self.button = QPushButton("Verificar con Windows Hello")
        self.button.setMinimumHeight(44)
        self.button.clicked.connect(self._start)
        layout.addWidget(self.button)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.setStyleSheet(
            "QLabel{color:#eef1f7;background:transparent}"
            "QPushButton{border:1px solid #323c4a;border-radius:12px;"
            "padding:10px;color:#e8edf4;background:#18212d}"
            "QPushButton:hover{background:#243247}"
            "QPushButton:disabled{color:#7c8797}"
        )
        self.completed.connect(self._finish)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        # Face ID's animation (scan → wink and check, or the shake).
        self.glyph = FaceIDGlyph()

    def _start(self):
        if self.checking:
            return
        self.checking = True
        self.glyph.start("scan")
        if not self.reduce_motion:
            self.timer.start(16)
        self.button.setEnabled(False)
        self.detail.setText("Complete la verificación en la ventana de Windows.")
        hwnd = int(self.winId())

        def work():
            try:
                result = self.verifier(hwnd, self.request, cancel=self.cancelled)
            except Exception:  # noqa: BLE001 — no successful animation on error
                result = Consent(False, "La verificación no está disponible.")
            self.completed.emit(result)

        threading.Thread(target=work, daemon=True, name="windows-hello-consent").start()

    def _finish(self, result):
        if self.cancelled.is_set():
            return
        self.checking = False
        self.verified = isinstance(result, Consent) and result.verified is True
        self.glyph.start("success" if self.verified else "fail")
        if self.reduce_motion:
            self.timer.stop()
        self.button.setEnabled(True)
        self.detail.setText(
            result.reason if isinstance(result, Consent) else "No verificado"
        )
        if self.verified:
            # let the wink and the check play before closing
            QTimer.singleShot(1100 if not self.reduce_motion else 0, self.accept)
        self.update()

    def reject(self):
        self.timer.stop()
        self.cancelled.set()
        self.verified = False
        super().reject()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#303947"), 1))
        painter.setBrush(QColor("#11171f"))
        painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), 28, 28)
        ring = QRectF(147, 32, 106, 106)
        if not self.reduce_motion:
            self.glyph.paint(painter, ring, "#dce9f5")
            if self.glyph.finished() and not self.checking:
                self.timer.stop()
            painter.end()
            return
        pulse = 0
        for i in range(36):
            alpha = (
                210
                if self.verified
                else 70 + int(95 * (0.5 + 0.5 * math.sin(i * 0.18 - pulse)))
            )
            painter.setPen(
                QPen(
                    QColor(177, 215, 246, alpha),
                    3,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawArc(ring, i * 10 * 16, 5 * 16)
        painter.setPen(
            QPen(QColor("#dce9f5"), 2.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        # Familiar scan brackets with an original glyph and blue-white palette.
        for x, y, angle in (
            (177, 58, 90),
            (207, 58, 0),
            (177, 91, 180),
            (207, 91, 270),
        ):
            painter.drawArc(QRectF(x, y, 16, 16), angle * 16, 90 * 16)
        if self.verified:
            painter.drawLine(189, 83, 197, 91)
            painter.drawLine(197, 91, 215, 73)
        else:
            painter.drawPoint(190, 77)
            painter.drawPoint(211, 77)
            painter.drawArc(QRectF(190, 83, 21, 13), 200 * 16, 140 * 16)
        painter.end()


__all__ = ["ConsentDialog"]

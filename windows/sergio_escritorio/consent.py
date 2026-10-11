"""Explicit local consent; identity recognition alone is not authorization."""

from __future__ import annotations


def confirm_dialog(request: str, seconds: float = 30.0) -> bool:
    """Show the exact request on the Qt thread; dismissal/timeout means no."""
    from PySide6.QtCore import Qt, QThread, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance()
    if app is None or QThread.currentThread() != app.thread() or not request.strip():
        return False
    box = QMessageBox()
    box.setWindowTitle("Sergio — autorización")
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText("¿Autoriza esta acción de Sergio?")
    box.setInformativeText(
        request
        if len(request) <= 600
        else request[:600] + "\nVea los detalles completos."
    )
    box.setDetailedText(request)
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.setEscapeButton(QMessageBox.StandardButton.No)
    timer = QTimer(box)
    timer.setSingleShot(True)
    timer.timeout.connect(box.reject)
    timer.start(max(1, int(seconds * 1000)))
    try:
        return box.exec() == QMessageBox.StandardButton.Yes
    finally:
        timer.stop()

"""Sergio's eyes: the webcam feed and a small floating, movable camera window.

* ``CameraFeed`` reads the webcam in a background thread (OpenCV) and keeps the
  latest frame. It only runs while the window is open or Sergio is looking,
  and switches the camera off by itself afterwards (the LED goes off).
* ``CameraWindow`` is a rounded, always-on-top preview you can drag anywhere
  (mouse wheel resizes it), so you can guide Sergio with gestures/objects.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)
IDLE_OFF_SECONDS = 20.0  # camera turns off this long after its last use
WARM_UP_SECONDS = 1.5  # webcams start dark/blurry while exposure settles


class CameraFeed:
    def __init__(self, index: int = 0) -> None:
        self.index = index
        self._frame: Any = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_use = 0.0
        self.keep_on = False  # True while the window is visible
        self.error = ""
        self._first_frame_at = 0.0

    # -- control ------------------------------------------------------------
    def start(self) -> None:
        self._last_use = time.monotonic()
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def _loop(self) -> None:
        import cv2

        cap = (
            cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
            if hasattr(cv2, "CAP_DSHOW")
            else cv2.VideoCapture(self.index)
        )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)  # detail for objects in hand
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        if not cap.isOpened():
            self.error = "No encuentro la cámara (¿la usa otra app?)"
            self._running = False
            return
        self.error = ""
        try:
            while self._running:
                ok, frame = cap.read()
                if ok:
                    with self._lock:
                        if self._frame is None:
                            self._first_frame_at = time.monotonic()
                        self._frame = frame
                idle = time.monotonic() - self._last_use > IDLE_OFF_SECONDS
                if idle and not self.keep_on:
                    break
                time.sleep(0.03)
        finally:
            cap.release()
            self._running = False
            with self._lock:
                self._frame = None

    # -- frames -------------------------------------------------------------
    def frame(self) -> Any:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def jpeg(self, wait: float = 4.0) -> bytes:
        """Latest frame as JPEG, starting the camera if needed."""
        import cv2

        self.start()
        deadline = time.monotonic() + wait
        frame = self.frame()
        while frame is None and time.monotonic() < deadline:
            if self.error:
                raise RuntimeError(self.error)
            time.sleep(0.1)
            frame = self.frame()
        if frame is None:
            raise RuntimeError(self.error or "La cámara no dio imagen a tiempo")
        settle = self._first_frame_at + WARM_UP_SECONDS - time.monotonic()
        if settle > 0:  # just switched on: let exposure and focus settle
            time.sleep(settle)
            latest = self.frame()
            if latest is not None:
                frame = latest
        ok, data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise RuntimeError("No pude codificar la imagen")
        return data.tobytes()


def to_qimage(frame: Any, mirror: bool = True) -> QImage:
    """OpenCV BGR frame -> QImage (mirrored like a selfie view)."""
    import cv2

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    if mirror:
        rgb = cv2.flip(rgb, 1)
    h, w, _ = rgb.shape
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class CameraWindow(QWidget):
    """Rounded floating preview. Drag to move, wheel to resize, × to close."""

    BASE = (320.0, 240.0)

    def __init__(self, feed: CameraFeed) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.feed = feed
        self.scale = 1.0
        self.overlay = ""  # e.g. what Sergio recognised last
        self._overlay_until = 0.0
        self._drag: QPointF | None = None
        self._image: QImage | None = None
        self._apply_size()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # -- API ------------------------------------------------------------------
    def open(self) -> None:
        self.feed.keep_on = True
        self.feed.start()
        if not self.isVisible():
            screen = self.screen().availableGeometry()
            self.move(
                screen.right() - self.width() - 24, screen.bottom() - self.height() - 24
            )
        self.show()
        self._timer.start(33)

    def close_camera(self) -> None:
        self.feed.keep_on = False
        self._timer.stop()
        self.hide()

    def toggle(self) -> None:
        if self.isVisible():
            self.close_camera()
        else:
            self.open()

    def show_overlay(self, text: str, seconds: float = 8.0) -> None:
        self.overlay = text
        self._overlay_until = time.monotonic() + seconds

    # -- internals ------------------------------------------------------------
    def _apply_size(self) -> None:
        w, h = self.BASE
        self.resize(int(w * self.scale), int(h * self.scale))

    def _tick(self) -> None:
        frame = self.feed.frame()
        if frame is not None:
            self._image = to_qimage(frame)
        if self.overlay and time.monotonic() > self._overlay_until:
            self.overlay = ""
        self.update()

    def _close_rect(self) -> QRectF:
        return QRectF(self.width() - 34, 10, 24, 24)

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        pos = event.position()
        if self._close_rect().contains(pos):
            self.close_camera()
            return
        self._drag = event.globalPosition() - QPointF(self.pos())

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._drag is not None:
            self.move((event.globalPosition() - self._drag).toPoint())

    def mouseReleaseEvent(self, _event: Any) -> None:  # noqa: N802
        self._drag = None

    def wheelEvent(self, event: Any) -> None:  # noqa: N802
        step = 0.1 if event.angleDelta().y() > 0 else -0.1
        self.scale = max(0.6, min(1.8, self.scale + step))
        self._apply_size()

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)
        p.setClipPath(path)
        p.fillRect(rect, QColor(12, 12, 14))
        if self._image is not None:
            img = self._image.scaled(
                rect.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawImage(
                QPointF(
                    rect.center().x() - img.width() / 2,
                    rect.center().y() - img.height() / 2,
                ),
                img,
            )
        else:
            p.setPen(QColor(200, 200, 210))
            p.setFont(QFont("Segoe UI", 10))
            msg = self.feed.error or "Encendiendo la cámara…"
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, msg)
        # Live pill
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(QRectF(10, 10, 92, 24), 12, 12)
        p.setBrush(QColor(255, 69, 58))
        p.drawEllipse(QPointF(22, 22), 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        p.drawText(QRectF(30, 10, 70, 24), Qt.AlignmentFlag.AlignVCenter, "Sergio ve")
        # Close button
        close = self._close_rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawEllipse(close)
        p.setPen(QPen(QColor(255, 255, 255), 1.6))
        c = close.center()
        p.drawLine(QPointF(c.x() - 4, c.y() - 4), QPointF(c.x() + 4, c.y() + 4))
        p.drawLine(QPointF(c.x() + 4, c.y() - 4), QPointF(c.x() - 4, c.y() + 4))
        # What Sergio recognised
        if self.overlay:
            p.setFont(QFont("Segoe UI", 9))
            box = QRectF(10, rect.bottom() - 44, rect.width() - 20, 34)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 170))
            p.drawRoundedRect(box, 12, 12)
            p.setPen(QColor(255, 255, 255))
            p.drawText(
                box.adjusted(10, 0, -10, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextSingleLine,
                p.fontMetrics().elidedText(
                    self.overlay, Qt.TextElideMode.ElideRight, int(box.width() - 20)
                ),
            )
        # Hairline border
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 18, 18)
        p.end()


__all__ = ["CameraFeed", "CameraWindow", "to_qimage"]

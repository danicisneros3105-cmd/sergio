"""Sergio's eyes: the webcam feed and a small floating, movable camera window.

* ``CameraFeed`` reads the webcam in a background thread (OpenCV) and keeps the
  latest frame. It only runs while the window is open or Sergio is looking,
  and switches the camera off by itself afterwards (the LED goes off).
* ``CameraWindow`` is a rounded, always-on-top preview you can drag anywhere
  (mouse wheel resizes it), so you can guide Sergio with gestures/objects.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
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


def detect_faces(frame: Any) -> list[tuple[int, int, int, int]]:
    """Face boxes (x, y, w, h) in frame pixels — fast, local (Haar)."""
    import cv2

    global _CASCADE
    if _CASCADE is None:
        if not hasattr(cv2, "CascadeClassifier"):  # OpenCV 5: no Haar detector
            _CASCADE = False
        else:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            _CASCADE = cv2.CascadeClassifier(path)
    if _CASCADE is False:
        return []
    h, w = frame.shape[:2]
    scale = 320 / max(1, w)
    small = cv2.resize(frame, (320, max(1, int(h * scale))))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    found = _CASCADE.detectMultiScale(gray, 1.2, 5, minSize=(24, 24))
    return [
        (int(x / scale), int(y / scale), int(fw / scale), int(fh / scale))
        for (x, y, fw, fh) in found
    ]


_CASCADE: Any = None
MARGIN = 10.0  # room for the soft shadow
BUTTONS = (("ask", "¿Qué ves?"), ("mirror", "Espejo"), ("photo", "Foto"))


class CameraWindow(QWidget):
    """Sergio's eyes on screen: drag to move, wheel to resize.

    Live face boxes, Sergio's last answer typed over the image, and a glass
    toolbar: ¿Qué ves? (ask him), Espejo (mirror), Foto (save a picture).
    """

    BASE = (360.0, 270.0)

    def __init__(
        self, feed: CameraFeed, on_ask: Callable[[], None] | None = None
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.feed = feed
        self.on_ask = on_ask
        self.scale = 1.0
        self.mirror = True
        self.overlay = ""
        self._overlay_at = 0.0
        self._overlay_until = 0.0
        self._flash_until = 0.0
        self._drag: QPointF | None = None
        self._image: QImage | None = None
        self._frame: Any = None
        self._faces: list[tuple[int, int, int, int]] = []
        self._ticks = 0
        self._t0 = time.monotonic()
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
                screen.right() - self.width() - 16, screen.bottom() - self.height() - 16
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

    def show_overlay(self, text: str, seconds: float = 0.0) -> None:
        self.overlay = " ".join(text.split())
        self._overlay_at = time.monotonic()
        self._overlay_until = self._overlay_at + (
            seconds or min(16.0, 4.0 + len(self.overlay) / 14)
        )

    def save_photo(self) -> str:
        """Save what the camera sees to Pictures\\Sergio; returns the path."""
        import cv2

        frame = self.feed.frame()
        if frame is None:
            return ""
        if self.mirror:
            frame = cv2.flip(frame, 1)
        folder = Path.home() / "Pictures" / "Sergio"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"sergio-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
        cv2.imwrite(str(path), frame)
        self._flash_until = time.monotonic() + 0.25
        self.show_overlay(f"Foto guardada en Imágenes\\Sergio\\{path.name}", 4)
        return str(path)

    # -- geometry ---------------------------------------------------------------
    def _apply_size(self) -> None:
        w, h = self.BASE
        self.resize(int(w * self.scale + 2 * MARGIN), int(h * self.scale + 2 * MARGIN))

    def card(self) -> QRectF:
        return QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)

    def _close_rect(self) -> QRectF:
        c = self.card()
        return QRectF(c.right() - 36, c.top() + 10, 26, 26)

    def button_rects(self) -> dict[str, QRectF]:
        c = self.card()
        widths = {"ask": 92.0, "mirror": 70.0, "photo": 58.0}
        total = sum(widths.values()) + 8 * (len(widths) - 1)
        x = c.center().x() - total / 2
        rects = {}
        for key, _label in BUTTONS:
            rects[key] = QRectF(x, c.bottom() - 42, widths[key], 30)
            x += widths[key] + 8
        return rects

    # -- behaviour --------------------------------------------------------------
    def _tick(self) -> None:
        frame = self.feed.frame()
        if frame is not None:
            self._frame = frame
            self._image = to_qimage(frame, self.mirror)
            self._ticks += 1
            if self._ticks % 5 == 0:  # ~6 face checks a second is plenty
                try:
                    self._faces = detect_faces(frame)
                except Exception:  # noqa: BLE001 — boxes are a bonus
                    self._faces = []
        if self.overlay and time.monotonic() > self._overlay_until:
            self.overlay = ""
        self.update()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        pos = event.position()
        if self._close_rect().contains(pos):
            self.close_camera()
            return
        for key, rect in self.button_rects().items():
            if rect.contains(pos):
                self._press(key)
                return
        self._drag = event.globalPosition() - QPointF(self.pos())

    def _press(self, key: str) -> None:
        if key == "ask" and self.on_ask is not None:
            self.show_overlay("Mirando…", 30)
            self.on_ask()
        elif key == "mirror":
            self.mirror = not self.mirror
        elif key == "photo":
            self.save_photo()

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._drag is not None:
            self.move((event.globalPosition() - self._drag).toPoint())

    def mouseReleaseEvent(self, _event: Any) -> None:  # noqa: N802
        self._drag = None

    def wheelEvent(self, event: Any) -> None:  # noqa: N802
        step = 0.1 if event.angleDelta().y() > 0 else -0.1
        self.scale = max(0.7, min(2.0, self.scale + step))
        self._apply_size()

    # -- drawing ------------------------------------------------------------------
    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        card = self.card()
        t = time.monotonic() - self._t0
        # Soft shadow.
        for i in range(6):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 14))
            p.drawRoundedRect(card.adjusted(-i, -i + 3, i, i + 3), 24 + i, 24 + i)
        path = QPainterPath()
        path.addRoundedRect(card, 22, 22)
        p.setClipPath(path)
        p.fillRect(card, QColor(12, 12, 14))
        if self._image is not None:
            img = self._image.scaled(
                card.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            origin = QPointF(
                card.center().x() - img.width() / 2,
                card.center().y() - img.height() / 2,
            )
            p.drawImage(origin, img)
            self._draw_faces(p, origin, img.width())
        else:
            p.setPen(QColor(200, 200, 210))
            p.setFont(_font(10))
            p.drawText(
                card,
                Qt.AlignmentFlag.AlignCenter,
                self.feed.error or "Encendiendo la cámara…",
            )
        # Gentle vignette at top and bottom so text is legible.
        for top, rect in (
            (True, QRectF(card.left(), card.top(), card.width(), 64)),
            (False, QRectF(card.left(), card.bottom() - 110, card.width(), 110)),
        ):
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0 if top else 1.0, QColor(0, 0, 0, 140))
            grad.setColorAt(1.0 if top else 0.0, QColor(0, 0, 0, 0))
            p.fillRect(rect, grad)
        if time.monotonic() < self._flash_until:
            p.fillRect(card, QColor(255, 255, 255, 170))
        self._draw_pill(p, card, t)
        self._draw_close(p)
        if self.overlay:
            self._draw_caption(p, card)
        self._draw_buttons(p)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 46), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(card, 22, 22)
        p.end()

    def _draw_faces(self, p: QPainter, origin: QPointF, shown_w: int) -> None:
        if self._frame is None or not self._faces:
            return
        fw = self._frame.shape[1]
        k = shown_w / max(1, fw)
        accent = QColor(10, 132, 255)
        for x, y, w, h in self._faces:
            if self.mirror:
                x = fw - x - w
            rect = QRectF(origin.x() + x * k, origin.y() + y * k, w * k, h * k)
            p.setPen(QPen(accent, 2))
            p.setBrush(QColor(10, 132, 255, 28))
            p.drawRoundedRect(rect, 12, 12)

    def _draw_pill(self, p: QPainter, card: QRectF, t: float) -> None:
        pill = QRectF(card.left() + 10, card.top() + 10, 104, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(pill, 13, 13)
        pulse = 0.55 + 0.45 * abs(math.sin(t * 2.2))
        red = QColor(255, 69, 58)
        red.setAlphaF(pulse)
        p.setBrush(red)
        p.drawEllipse(QPointF(pill.left() + 13, pill.center().y()), 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.setFont(_font(8.5, QFont.Weight.DemiBold))
        faces = f" · {len(self._faces)}" if self._faces else ""
        p.drawText(
            QRectF(pill.left() + 23, pill.top(), pill.width() - 26, pill.height()),
            Qt.AlignmentFlag.AlignVCenter,
            f"Sergio ve{faces}",
        )

    def _draw_close(self, p: QPainter) -> None:
        close = self._close_rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawEllipse(close)
        p.setPen(QPen(QColor(255, 255, 255), 1.6))
        c = close.center()
        p.drawLine(QPointF(c.x() - 4, c.y() - 4), QPointF(c.x() + 4, c.y() + 4))
        p.drawLine(QPointF(c.x() + 4, c.y() - 4), QPointF(c.x() - 4, c.y() + 4))

    def _draw_caption(self, p: QPainter, card: QRectF) -> None:
        shown = int((time.monotonic() - self._overlay_at) * 60)
        text = self.overlay[: max(0, shown)]
        p.setFont(_font(9.5))
        box = QRectF(card.left() + 12, card.bottom() - 98, card.width() - 24, 46)
        p.setPen(QColor(255, 255, 255))
        p.drawText(
            box,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignBottom
            | Qt.TextFlag.TextWordWrap,
            text,
        )

    def _draw_buttons(self, p: QPainter) -> None:
        p.setFont(_font(8.5, QFont.Weight.DemiBold))
        for key, label in BUTTONS:
            rect = self.button_rects()[key]
            active = key == "mirror" and self.mirror
            p.setPen(QPen(QColor(255, 255, 255, 50), 1))
            p.setBrush(
                QColor(255, 255, 255, 230) if key == "ask" else QColor(30, 30, 34, 190)
            )
            p.drawRoundedRect(rect, 15, 15)
            p.setPen(
                QColor(20, 20, 22)
                if key == "ask"
                else QColor(255, 255, 255, 255 if active else 170)
            )
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "SF Pro Text", "Segoe UI"])
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


__all__ = ["CameraFeed", "CameraWindow", "detect_faces", "to_qimage"]

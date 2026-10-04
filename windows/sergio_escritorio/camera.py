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
    QPolygonF,
    QRadialGradient,
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


class FaceWatcher:
    """Automatic face recognition while the camera is on.

    Every *interval* seconds the latest frame goes to Sergio's face models
    (YuNet + SFace on the server); results carry names, boxes and, for
    strangers, a number ("Persona 2"). A person is greeted (``on_person``)
    only after being recognised in two looks in a row, and at most once
    every *greet_after* seconds: one lucky frame never greets a stranger.
    """

    def __init__(
        self,
        frames: Callable[[], Any],
        identify: Callable[[bytes], list[dict]],
        *,
        interval: float = 1.5,
        greet_after: float = 600.0,
        on_person: Callable[[str], None] = lambda _name: None,
        on_faces: Callable[[list[dict]], None] = lambda _faces: None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.frames = frames
        self.identify = identify
        self.interval = interval
        self.greet_after = greet_after
        self.on_person = on_person
        self.on_faces = on_faces
        self.clock = clock
        self.faces: list[dict] = []  # {"name", "score", "box" (px), "nbox" (0..1)}
        self.updated = 0.0
        self.error = ""
        self._last_seen: dict[str, float] = {}
        self._away_since: dict[str, float] = {}
        self._streak: dict[str, int] = {}
        self._running = False

    def start(self) -> None:
        if not self._running:
            self._running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False

    def check(self, frame: Any) -> list[dict]:
        """Recognise the faces in one frame (scaled down to 640 px wide)."""
        import cv2

        h, w = frame.shape[:2]
        scale = min(1.0, 640 / max(1, w))
        small = (
            cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1 else frame
        )
        ok, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return []
        found = []
        for face in self.identify(jpeg.tobytes()):
            x, y, fw, fh = face.get("box") or (0, 0, 0, 0)
            box = (x / scale, y / scale, fw / scale, fh / scale)
            found.append(
                {
                    "name": face.get("name") or "",
                    "score": float(face.get("score") or 0.0),
                    "box": box,
                    "nbox": (box[0] / w, box[1] / h, box[2] / w, box[3] / h),
                    "guest": int(face.get("guest") or 0),
                    "quality": face.get("quality") or "ok",
                }
            )
        self.faces, self.updated = found, self.clock()
        self.on_faces(found)
        self._greet({f["name"] for f in found if f["name"]}, self.clock())
        return found

    def _greet(self, names: set[str], now: float) -> None:
        """Greet someone on their second look in a row, after a long absence."""
        for name in list(self._streak):
            gap = now - self._last_seen.get(name, -1e9)
            if name not in names or gap > 3 * self.interval:
                self._streak[name] = 0
        for name in names:
            streak = self._streak.get(name, 0) + 1
            self._streak[name] = streak
            if streak == 1:
                self._away_since[name] = self._last_seen.get(name, -1e9)
            if streak == 2 and now - self._away_since.get(name, -1e9) > self.greet_after:
                self.on_person(name)
            self._last_seen[name] = now

    def fresh(self) -> list[dict]:
        """Faces from the last few seconds (else nothing: they may be gone)."""
        return self.faces if self.clock() - self.updated < 3 * self.interval else []

    def _loop(self) -> None:
        while self._running:
            frame = self.frames()
            if frame is not None:
                try:
                    self.check(frame)
                    self.error = ""
                except Exception as exc:  # noqa: BLE001 — server busy/offline
                    self.error = str(exc)[:200]
            time.sleep(self.interval)


MARGIN = 10.0  # room for the soft shadow
BUTTONS = (
    ("ask", "¿Qué ves?"),
    ("analyze", "Analizar"),
    ("hands", "Manos"),
    ("physics", "Física"),
    ("mirror", "Espejo"),
    ("photo", "Foto"),
)
BUTTON_WIDTHS = {
    "ask": 78.0,
    "analyze": 74.0,
    "hands": 66.0,
    "physics": 58.0,
    "mirror": 60.0,
    "photo": 48.0,
}
HAND_MODES = ("off", "gestos", "mouse", "3d")
HAND_LABELS = {"off": "Manos", "gestos": "Gestos", "mouse": "Mouse", "3d": "3D", "fisica": "Manos"}
KIND_COLORS = {
    "conocido": QColor(48, 209, 88),
    "persona": QColor(10, 132, 255),
    "animal": QColor(255, 159, 10),
    "objeto": QColor(100, 210, 255),
}
# MediaPipe hand skeleton (pairs of landmark indices).
BONES = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (5, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (9, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (13, 17),
    (17, 18),
    (18, 19),
    (19, 20),
    (0, 17),
)


class CameraWindow(QWidget):
    """Sergio's eyes on screen: drag to move, wheel to resize.

    JARVIS-style overlay: every person, animal and object gets a frame and
    its name (known people by name, strangers as "Persona 2", animals with
    their species), the face mesh with the expression, your hands' skeleton
    and, in "Física", real objects you make and throw with your hands.
    Toolbar: ¿Qué ves? · Analizar (Gemini looks at everything) · Manos ·
    Física · Espejo · Foto. Click a stranger's frame to tell Sergio who it is.
    """

    BASE = (480.0, 270.0)

    def __init__(
        self,
        feed: CameraFeed,
        on_ask: Callable[[], None] | None = None,
        hands: Any = None,
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
        self.on_analyze: Callable[[], None] | None = None
        self.on_name_face: Callable[[tuple[float, float, float, float]], None] | None = None
        self.hands = hands  # HandControl (mode + latest hands), optional
        self.watcher: FaceWatcher | None = None  # automatic face recognition
        self.vision: Any = None  # VisionEngine: objects, species, face mesh
        self.sandbox: Any = None  # physics world, made when first needed
        self.scale = 1.0
        self.mirror = True
        self.overlay = ""
        self._overlay_at = 0.0
        self._overlay_until = 0.0
        self._flash_until = 0.0
        self._drag: QPointF | None = None
        self._pressed_at: QPointF | None = None
        self._image: QImage | None = None
        self._frame: Any = None
        self._faces: list[tuple[int, int, int, int]] = []
        self._ticks = 0
        self._t0 = time.monotonic()
        self._last_tick = time.monotonic()
        self._shown: tuple[QPointF, float, float] | None = None  # image origin, w, h
        self._apply_size()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # -- API ------------------------------------------------------------------
    def open(self) -> None:
        self.feed.keep_on = True
        self.feed.start()
        if self.watcher is not None:
            self.watcher.start()
        if self.vision is not None:
            self.vision.start()
        if not self.isVisible():
            screen = self.screen().availableGeometry()
            self.move(
                screen.right() - self.width() - 16, screen.bottom() - self.height() - 16
            )
        self.show()
        self._timer.start(33)

    def close_camera(self) -> None:
        if self.watcher is not None:
            self.watcher.stop()
        if self.vision is not None:
            self.vision.stop()
        if getattr(self.hands, "mode", "off") == "fisica":
            self.hands.set_mode("off")
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

    def physics(self) -> Any:
        """The physics world (made on first use; pymunk may be missing)."""
        if self.sandbox is None:
            from sergio_escritorio.physics import Sandbox

            frame = self._frame
            aspect = frame.shape[0] / frame.shape[1] if frame is not None else 9 / 16
            self.sandbox = Sandbox(aspect=aspect)
        return self.sandbox

    def set_physics(self, on: bool) -> str:
        """Física on/off: your hands touch, grab and make real objects."""
        if self.hands is None:
            return "No puedo ver tus manos (falta MediaPipe)."
        try:
            world = self.physics()
        except Exception as exc:  # noqa: BLE001 — pymunk not installed
            return f"No hay motor de física: {exc}"
        if on:
            self.hands.set_mode("fisica")
            self.feed.keep_on = True
            if not world.things:
                world.command("crea 3 pelotas")
            return (
                "Física: pellizca para agarrar y lanzar; pellizca con las dos "
                "manos y sepáralas para crear una caja."
            )
        self.hands.set_mode("off")
        return "Física apagada."

    def track_at(self, pos: QPointF) -> Any:
        """The person/animal/object frame under the mouse, if any."""
        if self.vision is None or self._shown is None or self._frame is None:
            return None
        now = time.monotonic()
        for track in self.vision.tracker.visible(now):
            if self._map_box(track.box).contains(pos):
                return track
        return None

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
        k = min(1.0, (c.width() - 24) / (sum(BUTTON_WIDTHS.values()) + 6 * (len(BUTTONS) - 1)))
        widths = {key: w * k for key, w in BUTTON_WIDTHS.items()}
        gap = 6 * k
        total = sum(widths.values()) + gap * (len(widths) - 1)
        x = c.center().x() - total / 2
        rects = {}
        for key, _label in BUTTONS:
            rects[key] = QRectF(x, c.bottom() - 40, widths[key], 28)
            x += widths[key] + gap
        return rects

    def _map_box(self, box: tuple[float, float, float, float]) -> QRectF:
        """A 0..1 frame box -> widget rect (mirror aware)."""
        origin, w, h = self._shown  # type: ignore[misc]
        x, y, bw, bh = box
        if self.mirror:
            x = 1 - x - bw
        return QRectF(origin.x() + x * w, origin.y() + y * h, bw * w, bh * h)

    def _map_point(self, x: float, y: float) -> QPointF:
        origin, w, h = self._shown  # type: ignore[misc]
        return QPointF(origin.x() + ((1 - x) if self.mirror else x) * w, origin.y() + y * h)

    # -- behaviour --------------------------------------------------------------
    def _tick(self) -> None:
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        frame = self.feed.frame()
        if frame is not None:
            self._frame = frame
            self._image = to_qimage(frame, self.mirror)
            self._ticks += 1
            if self.vision is None and self._ticks % 5 == 0:
                try:  # no MediaPipe: quick local face boxes at least
                    self._faces = detect_faces(frame)
                except Exception:  # noqa: BLE001 — boxes are a bonus
                    self._faces = []
        if getattr(self.hands, "mode", "off") == "fisica" and self.sandbox is not None:
            try:
                self.sandbox.update_hands(self.hands.hands, dt, self.mirror, now)
                self.sandbox.step(dt)
            except Exception:  # noqa: BLE001 — never break the camera
                log.exception("physics step failed")
        if self.overlay and now > self._overlay_until:
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
        self._pressed_at = pos

    def _press(self, key: str) -> None:
        if key == "hands" and self.hands is not None:
            current = getattr(self.hands, "mode", "off")
            if current not in HAND_MODES:
                current = "off"
            nxt = HAND_MODES[(HAND_MODES.index(current) + 1) % len(HAND_MODES)]
            self.hands.set_mode(nxt)
            self.feed.keep_on = True
            tips = {
                "gestos": (
                    "Gestos: pulgar arriba = sí, mano abierta = calla, dos dedos = "
                    "¿qué ves?, desliza la mano = siguiente/anterior, asiente = sí"
                ),
                "mouse": (
                    "Mouse: mueve la mano; pellizco = clic (mantén = arrastrar), "
                    "pulgar con el medio = clic derecho, dos dedos = desplazar, "
                    "dos manos pellizcando = zoom, puño = pausa"
                ),
                "3d": (
                    "3D en Blender: pellizca y mueve para girar, "
                    "dos manos para escalar, puño mueve"
                ),
                "off": "Control con las manos apagado",
            }
            self.show_overlay(tips[nxt], 6)
        elif key == "physics":
            on = getattr(self.hands, "mode", "off") != "fisica"
            self.show_overlay(self.set_physics(on), 6)
        elif key == "ask" and self.on_ask is not None:
            self.show_overlay("Mirando…", 30)
            self.on_ask()
        elif key == "analyze":
            if self.on_analyze is not None:
                self.show_overlay("Analizando todo lo que veo…", 30)
                self.on_analyze()
        elif key == "mirror":
            self.mirror = not self.mirror
        elif key == "photo":
            self.save_photo()

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._drag is not None:
            self.move((event.globalPosition() - self._drag).toPoint())

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        pressed, self._pressed_at = self._pressed_at, None
        self._drag = None
        if pressed is None:
            return
        pos = event.position()
        if (pos - pressed).manhattanLength() > 6:
            return  # it was a drag
        track = self.track_at(pos)
        if track is not None and track.kind == "persona" and not track.name:
            if self.on_name_face is not None:
                self.on_name_face(getattr(track, "face_box", None) or track.box)

    def wheelEvent(self, event: Any) -> None:  # noqa: N802
        step = 0.1 if event.angleDelta().y() > 0 else -0.1
        self.scale = max(0.7, min(2.4, self.scale + step))
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
            self._shown = (origin, float(img.width()), float(img.height()))
            if self.vision is not None:
                self._draw_tracks(p)
                self._draw_mesh(p)
            else:
                self._draw_faces(p, origin, img.width())
            self._draw_hands(p)
            self._draw_physics(p)
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

    def _draw_tracks(self, p: QPainter) -> None:
        """JARVIS frames: corner brackets + a name tag per thing."""
        now = time.monotonic()
        for track in self.vision.tracker.visible(now):
            rect = self._map_box(track.box)
            if track.kind == "persona":
                colour = KIND_COLORS["conocido" if track.name else "persona"]
            else:
                colour = KIND_COLORS.get(track.kind, KIND_COLORS["objeto"])
            arm = max(8.0, min(rect.width(), rect.height()) * 0.18)
            p.setPen(QPen(colour, 2.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for cx, cy, dx, dy in (
                (rect.left(), rect.top(), 1, 1),
                (rect.right(), rect.top(), -1, 1),
                (rect.left(), rect.bottom(), 1, -1),
                (rect.right(), rect.bottom(), -1, -1),
            ):
                p.drawLine(QPointF(cx, cy), QPointF(cx + dx * arm, cy))
                p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * arm))
            fill = QColor(colour)
            fill.setAlpha(18)
            p.fillRect(rect, fill)
            label = track.title(now)
            if track.kind == "persona" and track.name and track.face_score:
                label += f"  {track.face_score * 100:.0f}%"
            elif track.kind != "persona":
                label += f"  {track.score * 100:.0f}%"
            p.setFont(_font(8, QFont.Weight.DemiBold))
            tw = min(p.fontMetrics().horizontalAdvance(label) + 14, max(60.0, rect.width() + 40))
            top = rect.top() - 20 if rect.top() - 20 > MARGIN + 40 else rect.top() + 4
            tag = QRectF(rect.left(), top, tw, 17)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colour)
            p.drawRoundedRect(tag, 8.5, 8.5)
            p.setPen(QColor(10, 10, 12) if track.kind == "objeto" else QColor(255, 255, 255))
            p.drawText(
                tag.adjusted(6, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                p.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, int(tw - 10)),
            )

    def _draw_mesh(self, p: QPainter) -> None:
        """Face mesh outlines, where the head points and the expression."""
        from sergio_escritorio.vision import OUTLINES

        faces = list(getattr(self.vision, "faces", []) or [])
        if not faces or not getattr(self.vision, "mesh", True):
            return
        line = QColor(100, 210, 255, 210)
        for face in faces:
            pts = face.points
            if len(pts) < 468:
                continue
            p.setPen(QPen(line, 1.3))
            for outline in OUTLINES:
                poly = QPolygonF([self._map_point(*pts[i]) for i in outline])
                p.drawPolyline(poly)
            # Where the head points: a short ray from the nose tip.
            nose = self._map_point(*pts[1])
            yaw = -face.yaw if self.mirror else face.yaw
            length = self._map_box(face.box).width() * 0.6
            end = QPointF(
                nose.x() + length * math.sin(math.radians(yaw)),
                nose.y() - length * math.sin(math.radians(face.pitch)),
            )
            p.setPen(QPen(QColor(255, 214, 10, 200), 1.6))
            p.drawLine(nose, end)
            if face.expressions:
                rect = self._map_box(face.box)
                text = " · ".join(face.expressions)
                p.setFont(_font(7.5, QFont.Weight.DemiBold))
                tw = p.fontMetrics().horizontalAdvance(text) + 12
                chip = QRectF(rect.center().x() - tw / 2, rect.bottom() + 4, tw, 16)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 160))
                p.drawRoundedRect(chip, 8, 8)
                p.setPen(QColor(255, 214, 10))
                p.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_faces(self, p: QPainter, origin: QPointF, shown_w: int) -> None:
        """Without MediaPipe: face boxes with names from face recognition."""
        if self._frame is None:
            return
        named = self.watcher.fresh() if self.watcher is not None else []
        faces = named or [
            {"name": None, "score": 0.0, "box": box, "guest": 0} for box in self._faces
        ]
        if not faces:
            return
        fw = self._frame.shape[1]
        k = shown_w / max(1, fw)
        for face in faces:
            x, y, w, h = face["box"]
            if self.mirror:
                x = fw - x - w
            rect = QRectF(origin.x() + x * k, origin.y() + y * k, w * k, h * k)
            known = bool(face["name"])
            colour = KIND_COLORS["conocido" if known else "persona"]
            p.setPen(QPen(colour, 2))
            fill = QColor(colour)
            fill.setAlpha(28)
            p.setBrush(fill)
            p.drawRoundedRect(rect, 12, 12)
            if face["name"] is None:
                continue  # quick local box, recognition pending
            guest = face.get("guest") or 0
            label = (
                f"{face['name']}  {face['score'] * 100:.0f}%"
                if known
                else (f"Persona {guest}" if guest else "Desconocido")
            )
            p.setFont(_font(8.5, QFont.Weight.DemiBold))
            tw = p.fontMetrics().horizontalAdvance(label) + 16
            top = rect.top() - 24
            if top < MARGIN + 44:  # near the top edge: put it inside the box
                top = rect.bottom() - 26 if rect.top() < MARGIN + 44 else rect.top() + 4
            tag = QRectF(rect.left() + 4, top, tw, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colour)
            p.drawRoundedRect(tag, 10, 10)
            p.setPen(QColor(255, 255, 255))
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_hands(self, p: QPainter) -> None:
        hands = getattr(self.hands, "hands", None) or []
        if not hands or getattr(self.hands, "mode", "off") == "off" or self._shown is None:
            return
        green = QColor(48, 209, 88)
        physics = getattr(self.hands, "mode", "off") == "fisica"
        for hand in hands:
            pts = [self._map_point(x, y) for x, y, *_ in hand.landmarks]
            p.setPen(QPen(QColor(255, 255, 255, 170), 2))
            for a, b in BONES:
                p.drawLine(pts[a], pts[b])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(green)
            for pt in pts:
                p.drawEllipse(pt, 3, 3)
            if physics:  # fingertips are solid: show them as glowing pads
                p.setBrush(QColor(100, 210, 255, 90))
                for i in (4, 8, 12, 16, 20):
                    p.drawEllipse(pts[i], 7, 7)
            else:
                p.setPen(QColor(255, 255, 255))
                p.setFont(_font(8, QFont.Weight.DemiBold))
                p.drawText(pts[8] + QPointF(8, -8), hand.gesture)

    def _draw_physics(self, p: QPainter) -> None:
        world = self.sandbox
        if world is None or self._shown is None or getattr(self.hands, "mode", "off") != "fisica":
            return
        origin, w, h = self._shown
        kx, ky = w / world.width, h / world.height

        def to_view(x: float, y: float) -> QPointF:
            return QPointF(origin.x() + x * kx, origin.y() + y * ky)

        floor_y = origin.y() + world.floor * ky - 6 * ky
        for thing in world.things:
            colour = QColor(thing.color)
            x, y = thing.position
            centre = to_view(x, y)
            radius = thing.size / 2 * kx
            # soft shadow on the floor, smaller when it is high up
            height = max(0.0, floor_y - centre.y())
            spread = max(0.25, 1 - height / max(1.0, h))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, int(70 * spread)))
            p.drawEllipse(QPointF(centre.x(), floor_y), radius * spread, radius * 0.22 * spread)
            if thing.shape == "pelota":
                grad = QRadialGradient(centre + QPointF(-radius * 0.35, -radius * 0.35), radius * 1.3)
                grad.setColorAt(0.0, colour.lighter(170))
                grad.setColorAt(0.5, colour)
                grad.setColorAt(1.0, colour.darker(210))
                p.setBrush(grad)
                p.drawEllipse(centre, radius, radius)
                p.setBrush(QColor(255, 255, 255, 120))
                p.drawEllipse(centre + QPointF(-radius * 0.35, -radius * 0.4), radius * 0.22, radius * 0.14)
            else:
                poly = QPolygonF([to_view(px, py) for px, py in thing.outline()])
                grad = QLinearGradient(poly.boundingRect().topLeft(), poly.boundingRect().bottomRight())
                grad.setColorAt(0.0, colour.lighter(150))
                grad.setColorAt(1.0, colour.darker(180))
                p.setBrush(grad)
                p.setPen(QPen(colour.lighter(170), 1.2))
                p.drawPolygon(poly)
        for state in world.hands.values():  # what you are holding glows
            if state.grabbed:
                thing = state.grabbed[0]
                c = to_view(*thing.position)
                p.setPen(QPen(QColor(255, 255, 255, 160), 1.5, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                r = thing.size / 2 * kx + 6
                p.drawEllipse(c, r, r)
        if world.preview is not None:  # a box growing between your hands
            a, b = world.preview
            rect = QRectF(to_view(*a), to_view(*b)).normalized()
            side = max(rect.width(), rect.height())
            square = QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)
            p.setPen(QPen(QColor(255, 255, 255, 220), 1.6, Qt.PenStyle.DashLine))
            p.setBrush(QColor(10, 132, 255, 50))
            p.drawRoundedRect(square, 6, 6)

    def _draw_pill(self, p: QPainter, card: QRectF, t: float) -> None:
        text = "Sergio ve"
        if self.vision is not None:
            from collections import Counter

            tracks = self.vision.tracker.visible(time.monotonic())
            counts = Counter(tr.kind for tr in tracks)
            parts = []
            if counts.get("persona"):
                n = counts["persona"]
                parts.append(f"{n} persona{'s' if n > 1 else ''}")
            if counts.get("animal"):
                n = counts["animal"]
                parts.append(f"{n} animal{'es' if n > 1 else ''}")
            if counts.get("objeto"):
                n = counts["objeto"]
                parts.append(f"{n} objeto{'s' if n > 1 else ''}")
            if parts:
                text += " · " + " · ".join(parts)
        else:
            count = len(self.watcher.fresh()) if self.watcher is not None else 0
            count = count or len(self._faces)
            if count:
                text += f" · {count}"
        p.setFont(_font(8.5, QFont.Weight.DemiBold))
        width = p.fontMetrics().horizontalAdvance(text) + 34
        pill = QRectF(card.left() + 10, card.top() + 10, width, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(pill, 13, 13)
        pulse = 0.55 + 0.45 * abs(math.sin(t * 2.2))
        red = QColor(255, 69, 58)
        red.setAlphaF(pulse)
        p.setBrush(red)
        p.drawEllipse(QPointF(pill.left() + 13, pill.center().y()), 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.drawText(
            QRectF(pill.left() + 23, pill.top(), pill.width() - 26, pill.height()),
            Qt.AlignmentFlag.AlignVCenter,
            text,
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
        box = QRectF(card.left() + 12, card.bottom() - 96, card.width() - 24, 50)
        p.setPen(QColor(255, 255, 255))
        p.drawText(
            box,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignBottom
            | Qt.TextFlag.TextWordWrap,
            text,
        )

    def _draw_buttons(self, p: QPainter) -> None:
        mode = getattr(self.hands, "mode", "off")
        rects = self.button_rects()
        size = 8.0 if self.scale >= 1 else 7.0
        p.setFont(_font(size, QFont.Weight.DemiBold))
        for key, label in BUTTONS:
            rect = rects[key]
            active = (
                (key == "mirror" and self.mirror)
                or (key == "hands" and mode not in ("off", "fisica"))
                or (key == "physics" and mode == "fisica")
            )
            if key == "hands":
                label = HAND_LABELS.get(mode, "Manos")
            p.setPen(QPen(QColor(255, 255, 255, 50), 1))
            if key == "ask":
                p.setBrush(QColor(255, 255, 255, 230))
            elif active:
                p.setBrush(QColor(10, 132, 255, 220))
            else:
                p.setBrush(QColor(30, 30, 34, 190))
            p.drawRoundedRect(rect, 14, 14)
            p.setPen(
                QColor(20, 20, 22)
                if key == "ask"
                else QColor(255, 255, 255, 255 if active else 190)
            )
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "SF Pro Text", "Segoe UI"])
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


__all__ = ["CameraFeed", "CameraWindow", "FaceWatcher", "detect_faces", "to_qimage"]

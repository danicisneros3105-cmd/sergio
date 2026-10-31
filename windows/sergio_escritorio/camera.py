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
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
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

from sergio_escritorio import estilo

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
        # MJPG first: many webcams give 720p uncompressed at only 5-10 FPS
        # through DirectShow, which made Sergio ve and the hands lag.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)  # detail for objects in hand
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # the newest frame, not an old one
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
                if not ok:
                    time.sleep(0.03)
                # read() already waits for the next frame: an extra sleep
                # here halved the frame rate and added delay.
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


def frosted(frame: Any, size: tuple[int, int], mirror: bool = True) -> QImage:
    """The camera picture as frosted glass sees it: blurred, a little brighter.

    Done small (1/8) and scaled up, so it costs well under a millisecond."""
    import cv2

    h, w = frame.shape[:2]
    small = cv2.resize(frame, (max(8, w // 8), max(8, h // 8)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 2.2)
    small = cv2.addWeighted(small, 0.80, small * 0 + 255, 0.20, 0)  # milky
    img = to_qimage(small, mirror)
    return img.scaled(size[0], size[1], Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)



def detect_faces(frame: Any) -> list[tuple[int, int, int, int]]:
    """Face boxes (x, y, w, h) in frame pixels — fast, local (Haar)."""
    import cv2

    global _CASCADE
    if _CASCADE is None:  # OpenCV 5 / builds without the XML: no Haar
        _CASCADE = _cascade("haarcascade_frontalface_default.xml")
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



_PROFILE: Any = None


def _cascade(name: str) -> Any:
    import cv2

    if not hasattr(cv2, "CascadeClassifier"):
        return False
    found = cv2.CascadeClassifier(cv2.data.haarcascades + name)
    return False if found.empty() else found  # some OpenCV builds ship no XML


def face_or_profile(frame: Any) -> bool:
    """A face looking at the screen, or turned to either side (Haar)."""
    import cv2

    global _PROFILE, _CASCADE
    if _CASCADE is None:
        _CASCADE = _cascade("haarcascade_frontalface_default.xml")
    if _PROFILE is None:
        _PROFILE = _cascade("haarcascade_profileface.xml")
    if _CASCADE is False and _PROFILE is False:
        raise RuntimeError("no Haar cascades")
    if _CASCADE is not False and detect_faces(frame):
        return True
    if _PROFILE is False:
        return False
    h, w = frame.shape[:2]
    small = cv2.cvtColor(cv2.resize(frame, (320, max(1, int(h * 320 / max(1, w))))), cv2.COLOR_BGR2GRAY)
    for img in (small, cv2.flip(small, 1)):  # the cascade only knows one side
        if len(_PROFILE.detectMultiScale(img, 1.2, 5, minSize=(24, 24))):
            return True
    return False


def presence_detector() -> Any:
    """The best local face finder there is: Haar, else MediaPipe's mesh."""
    try:
        import numpy as np

        face_or_profile(np.zeros((90, 160, 3), np.uint8))
        return face_or_profile
    except Exception:  # noqa: BLE001
        pass
    try:
        from sergio_escritorio.vision import FaceMesh

        mesh = FaceMesh(max_faces=1)
        return lambda frame: bool(mesh.find(frame))
    except Exception:  # noqa: BLE001
        return None


def someone_there(
    feed: "CameraFeed", seconds: float = 4.0, detect: Any = None
) -> bool | None:
    """Is someone in front of the computer? A few seconds of webcam, faces
    found locally (nothing saved or sent). None = no camera to ask."""
    detect = detect or presence_detector()
    if detect is None:
        return None  # nothing to look with: the keyboard decides
    was_running = feed.running
    feed.start()
    deadline = time.monotonic() + seconds
    looked = 0
    try:
        while time.monotonic() < deadline:
            if feed.error:
                return None
            frame = feed.frame()
            if frame is not None and time.monotonic() - feed._first_frame_at > 0.6:
                looked += 1
                if detect(frame):
                    return True
            time.sleep(0.25)
    finally:
        if not was_running and not feed.keep_on:
            feed.stop()  # the light goes off at once
    return False if looked else None


class FaceWatcher:
    """Automatic face recognition while the camera is on.

    The latest frame goes to Sergio's face models (YuNet + SFace on the
    server, ~50 ms); results carry names, boxes and, for strangers, a
    number ("Persona 2"). It looks fast (*fast* seconds) while a face in view
    is still unnamed and slowly (*interval*) once everyone is known, and
    ``poke()`` makes it look at once (a new face appeared): a face used to
    wait 1.5 s per look and needed two looks. A person is greeted
    (``on_person``) only after being recognised in two looks in a row, and
    at most once every *greet_after* seconds: one lucky frame never greets a
    stranger.
    """

    def __init__(
        self,
        frames: Callable[[], Any],
        identify: Callable[[bytes], list[dict]],
        *,
        interval: float = 1.5,
        fast: float = 0.25,
        empty: float = 0.6,
        greet_after: float = 600.0,
        on_person: Callable[[str], None] = lambda _name: None,
        on_faces: Callable[[list[dict]], None] = lambda _faces: None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.frames = frames
        self.identify = identify
        self.interval = interval
        self.fast = fast
        self.empty = empty
        self.greet_after = greet_after
        self.on_person = on_person
        self.on_faces = on_faces
        self.clock = clock
        self.faces: list[dict] = []  # {"name", "score", "box" (px), "nbox" (0..1)}
        self.updated = 0.0
        self.error = ""
        self.owner = ""  # whose assistant this is (the server says)
        self._last_seen: dict[str, float] = {}
        self._away_since: dict[str, float] = {}
        self._streak: dict[str, int] = {}
        self._running = False
        self._wake = threading.Event()

    def start(self) -> None:
        if not self._running:
            self._running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        self._wake.set()

    def poke(self) -> None:
        """Look now (a new face appeared)."""
        self._wake.set()

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
                    "strong": bool(face.get("strong")),
                    "owner": bool(face.get("owner")),
                    "angle": face.get("angle") or "",
                    "learned": bool(face.get("learned")),
                }
            )
        self.faces, self.updated = found, self.clock()
        self.on_faces(found)
        self._greet({f["name"] for f in found if f["name"]}, self.clock())
        return found

    def wait(self) -> float:
        """Seconds until the next look: quick while someone is unnamed."""
        if not self.faces:
            return self.empty
        if any(not f["name"] for f in self.faces):
            return self.fast
        return self.interval

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
            self._wake.wait(self.wait() if not self.error else self.interval)
            self._wake.clear()


MARGIN = 10.0  # room for the soft shadow
# Lines between characteristic face points (names from vision.SIGNATURE_POINTS):
# eyes, brows, nose and mouth triangles, cheekbones and jaw.
FACE_NETWORK = (
    ("ex_d", "en_d"), ("en_i", "ex_i"), ("en_d", "n"), ("en_i", "n"), ("p_d", "p_i"),
    ("sci_d", "g"), ("g", "sci_i"), ("sci_d", "ex_d"), ("sci_i", "ex_i"), ("tr", "g"),
    ("g", "n"), ("n", "prn"), ("prn", "al_d"), ("prn", "al_i"), ("al_d", "sn"), ("al_i", "sn"),
    ("sn", "ls"), ("ch_d", "ls"), ("ls", "ch_i"), ("ch_d", "li"), ("li", "ch_i"), ("ls", "sto"),
    ("sto", "li"), ("li", "gn"), ("zy_d", "ex_d"), ("zy_i", "ex_i"), ("zy_d", "al_d"),
    ("zy_i", "al_i"), ("zy_d", "go_d"), ("zy_i", "go_i"), ("go_d", "gn"), ("go_i", "gn"),
    ("go_d", "ch_d"), ("go_i", "ch_i"), ("p_d", "prn"), ("p_i", "prn"), ("ps_d", "pi_d"),
)  # fmt: skip
# The app's look (estilo.py): black, white and greys, no colour in the interface.
INK, CARD, LINE, TEXT = (QColor(estilo.INK), QColor(estilo.CARD), QColor(estilo.LINE), QColor(estilo.TEXT))
KIND_COLORS = {  # lighter = more certain: someone known is pure white
    "conocido": QColor(255, 255, 255),
    "persona": QColor(196, 196, 196),
    "animal": QColor(150, 150, 150),
    "objeto": QColor(110, 110, 110),
}
DARK_TEXT = ("conocido", "persona")  # light tags carry black letters
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
    their species), the face mesh with the expression, and the holograms
    (``holo.py``) you grab, turn, throw, sculpt and draw with your hands.
    No buttons: everything is by voice ("crea un cubo", "analiza lo que
    ves", "toma una foto", "modo espejo"...). Click a stranger's frame to
    tell Sergio who it is.
    """

    BASE = (480.0, 270.0)

    def __init__(
        self,
        feed: CameraFeed,
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
        self.on_analyze: Callable[[], None] | None = None
        self.on_name_face: Callable[[tuple[float, float, float, float]], None] | None = None
        # Clean view: names, what you hold, animals, face points and the
        # holograms. Measurements (distance, eyes, posture, hands, mood,
        # scores) are still taken and said when asked; "muestra los datos"
        # puts them on screen too.
        self.detail = False
        self.hands = hands  # HandControl (mode + latest hands), optional
        self.watcher: FaceWatcher | None = None  # automatic face recognition
        self.vision: Any = None  # VisionEngine: objects, species, face mesh
        self.scanner: Any = None  # facescan.Scanner while a Face ID-style scan runs
        self.scan_text: list[str] = []  # what the last scan learnt (shown with the 3D map)
        self._scan_edges: list[tuple[int, int]] | None = None
        from sergio_escritorio.holo import HoloScene

        self.holo = HoloScene()  # holograms you shape with your hands
        self.guide_until = 0.0  # show the holograms how-to until then
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
    # Owner (29 Oct 2026): «esconde Sergio ve: Sergio te verá siempre, pero
    # no saldrá la pantalla de Sergio ve; solo pedirá permiso para la cámara».
    # The eyes work in the background (faces, objects, what you hold); the
    # window shows only when asked («muéstrame la cámara») or for holograms.
    show_window = False
    active = False
    allow: Callable[[], bool] = staticmethod(lambda: True)  # the camera permission

    def open(self, show: bool | None = None) -> None:
        if not self.allow():
            return
        self.active = True
        self.feed.keep_on = True
        self.feed.start()
        if self.watcher is not None:
            self.watcher.start()
        if self.vision is not None:
            self.vision.start()
        if self.hands is not None and getattr(self.hands, "mode", "off") == "off":
            self.hands.set_mode("ver")  # your hands: never mistaken for things
        if not (self.show_window if show is None else show):
            return  # seeing without the window
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
        if getattr(self.hands, "mode", "off") != "off":
            self.hands.set_mode("off")
        self.feed.keep_on = False
        self.active = False
        self._timer.stop()
        self.hide()

    def toggle(self) -> None:
        """The camera hotkey shows or hides the window (the owner asked)."""
        if self.isVisible():
            self.close_camera()
        else:
            self.open(show=True)

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

    def set_holo(self, on: bool = True, starter: bool = False) -> str:
        """Your hands on the holograms (tracking on), or off.

        No cube appears by itself any more: it used to be added every time the
        holograms opened, so a designed model (or a failed one) came with a
        stray cube and it looked as if Sergio only made cubes."""
        if self.hands is None:
            return "No puedo ver tus manos (falta MediaPipe)."
        self.hands.set_mode("holo" if on else ("ver" if self.isVisible() else "off"))
        self.feed.keep_on = True if on else self.isVisible()
        if not on:
            return "Manos apagadas."
        self.guide_until = time.monotonic() + 25  # the how-to stays on screen
        if starter and not self.holo.objects:
            self.holo.command("crea un cubo")  # only when asked for a first figure
            self.holo.command("céntralo")
            return "Listo: pellizque el cubo para moverlo, gire la muñeca para girarlo."
        return "Listo: pídame cualquier objeto («haz un holograma de un teléfono») y pellízquelo para moverlo."

    def hologram(self, order: str) -> str:
        """A voice order for the holograms ("crea un cubo rojo", "esculpir")."""
        if re.search(r"\b(ayuda|como (se )?(hace|uso|funciona)|instrucciones|guia)\b", order.lower()):
            self.guide_until = time.monotonic() + 30
            return "Le muestro cómo se usan, en la pantalla."
        if self.hands is not None and getattr(self.hands, "mode", "off") != "holo":
            self.set_holo(True, starter=False)
        return self.holo.command(order)

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
        card = self.card()
        self.holo.view = (card.width(), card.height())
        try:
            if getattr(self.hands, "mode", "off") == "holo" and self._shown is not None:
                origin, w, h = self._shown
                box = (origin.x() - card.left(), origin.y() - card.top(), w, h)
                self.holo.update_hands(self.hands.hands, dt, self.mirror, now, box)
            if self.holo.objects:
                self.holo.step(dt)
        except Exception:  # noqa: BLE001 — never break the camera
            log.exception("holograms failed")
        if self.overlay and now > self._overlay_until:
            self.overlay = ""
        self.update()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        pos = event.position()
        if self._close_rect().contains(pos):
            self.close_camera()
            return
        self._holo_drag = None
        if self.holo.objects and self._shown is not None:
            card = self.card()
            hit = self.holo.pick(pos.x() - card.left(), pos.y() - card.top())
            if hit is not None:  # the mouse moves (left) or turns (right) it
                self.holo.selected = hit.id
                self._holo_drag = (pos, event.button() == Qt.MouseButton.RightButton)
                self._pressed_at = None
                self._drag = None
                return
        self._drag = event.globalPosition() - QPointF(self.pos())
        self._pressed_at = pos

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        grab = getattr(self, "_holo_drag", None)
        if grab is not None:
            last, turning = grab
            pos = event.position()
            dx, dy = pos.x() - last.x(), pos.y() - last.y()
            if turning:
                self.holo.turn(dx * 0.6, dy * 0.6)
            else:
                k = 2 * 1.6 / max(1.0, self.card().width())  # px -> scene units
                self.holo.nudge(dx * k, -dy * k)
            self._holo_drag = (pos, turning)
            return
        if self._drag is not None:
            self.move((event.globalPosition() - self._drag).toPoint())

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        self._holo_drag = None
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
        obj = self.holo.current() if self.holo.objects else None
        if obj is not None and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            obj.scale = max(0.2, min(5.0, obj.scale * (1.1 if event.angleDelta().y() > 0 else 1 / 1.1)))
            return  # Ctrl + wheel: the hologram's size
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
        p.fillRect(card, INK)
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
            self._frost = None
            if self.holo.objects and self.holo.style == "cristal" and self._frame is not None:
                try:
                    self._frost = frosted(self._frame, (img.width(), img.height()), self.mirror)
                except Exception:  # noqa: BLE001 — plain glass without the blur
                    self._frost = None
            scanning = self.scanner is not None and (
                self.scanner.active
                or (self.scanner.result is not None and time.monotonic() - self.scanner.finished_at < 6.0)
            )
            if self.vision is not None and not scanning:
                if self.detail:
                    self._draw_pose(p)
                self._draw_tracks(p)
                self._draw_mesh(p)
                if self.detail:
                    self._draw_vitals(p, card)
            elif self.vision is None:
                self._draw_faces(p, origin, img.width())
            if self.scanner is not None:
                self._draw_face_scan(p, card)
            self._draw_holo(p, card)
            self._draw_hands(p)
        else:
            p.setPen(TEXT)
            p.setFont(_font(10, QFont.Weight.DemiBold))
            p.drawText(
                card,
                Qt.AlignmentFlag.AlignCenter,
                self.feed.error or "Encendiendo la cámara…",
            )
        # Gentle vignette at top and bottom so text is legible.
        for top, rect in (
            (True, QRectF(card.left(), card.top(), card.width(), 56)),
            (False, QRectF(card.left(), card.bottom() - 74, card.width(), 74)),
        ):
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0 if top else 1.0, QColor(0, 0, 0, 95))
            grad.setColorAt(1.0 if top else 0.0, QColor(0, 0, 0, 0))
            p.fillRect(rect, grad)
        if time.monotonic() < self._flash_until:
            p.fillRect(card, QColor(255, 255, 255, 190))  # the photo flash
        self._draw_pill(p, card, t)
        self._draw_close(p)
        if self.overlay:
            self._draw_caption(p, card)
        p.setClipping(False)
        p.setPen(QPen(LINE, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(card, 22, 22)
        p.end()

    def _draw_tracks(self, p: QPainter) -> None:
        """JARVIS frames: corner brackets + a name tag per thing."""
        now = time.monotonic()
        faces = list(getattr(self.vision, "faces", []) or []) if getattr(self.vision, "mesh", True) else []
        from sergio_escritorio.vision import salient

        clean = not self.detail
        for track in salient(self.vision.tracker.visible(now), clean=clean):
            rect = self._map_box(track.box)
            if track.kind == "persona":
                if clean:
                    continue  # nothing follows a person in the clean view
                colour = KIND_COLORS["conocido" if track.name else "persona"]
                if self._face_of(track, faces) is not None:
                    # The face reticle carries the name: the body only gets
                    # faint corners (no tag far away from the face).
                    faint = QColor(colour)
                    faint.setAlpha(90)
                    self._brackets(p, rect, faint, 1.4)
                    continue
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
            label = track.title(now, clean=clean)
            if clean:
                pass
            elif track.kind == "persona" and track.name and track.face_score:
                label += f"  {track.face_score * 100:.0f}%"
            elif track.kind == "objeto" and not track.named and track.label == "objeto":
                label += "  ¿?"  # unsure: say so instead of a confident wrong name
            p.setFont(_font(8, QFont.Weight.DemiBold))
            tw = min(p.fontMetrics().horizontalAdvance(label) + 14, max(60.0, rect.width() + 40))
            top = rect.top() - 20 if rect.top() - 20 > MARGIN + 40 else rect.top() + 4
            top = max(top, self.card().top() + 50)  # never under the top pill
            left = rect.left()
            if track.kind == "persona":
                # Over the head, not at the box's corner (an arm stretched
                # sideways made the tag land on the person next to you).
                head = self._map_box(track.face_box).center().x() if track.face_box else rect.center().x()
                left = head - tw / 2
            card = self.card()
            left = min(max(left, card.left() + 6), card.right() - tw - 6)
            tag = QRectF(left, top, tw, 17)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colour)
            p.drawRoundedRect(tag, 8.5, 8.5)
            p.setPen(INK if track.kind in DARK_TEXT else TEXT)
            p.drawText(
                tag.adjusted(6, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                p.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, int(tw - 10)),
            )

    @staticmethod
    def _face_of(track: Any, faces: list) -> Any:
        """The face (mesh) that belongs to this person, if one is in view."""
        from sergio_escritorio.vision import contains, iou

        best = None
        for face in faces:
            if track.face_box is not None and iou(track.face_box, face.box) > 0.25:
                return face
            if contains(track.box, face.box):
                best = best or face
        return best

    def _brackets(self, p: QPainter, rect: QRectF, colour: QColor, width: float) -> None:
        arm = max(8.0, min(rect.width(), rect.height()) * 0.18)
        p.setPen(QPen(colour, width))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for cx, cy, dx, dy in (
            (rect.left(), rect.top(), 1, 1),
            (rect.right(), rect.top(), -1, 1),
            (rect.left(), rect.bottom(), 1, -1),
            (rect.right(), rect.bottom(), -1, -1),
        ):
            p.drawLine(QPointF(cx, cy), QPointF(cx + dx * arm, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * arm))

    def _draw_pose(self, p: QPainter) -> None:
        """Your body: a thin skeleton (posture is measured from it)."""
        from sergio_escritorio.body import POSE_BONES

        pose = list(getattr(self.vision, "pose", []) or [])
        if len(pose) < 33 or self._shown is None:
            return
        pts = [self._map_point(x, y) for x, y, *_ in pose]
        seen = [len(pt) < 4 or pt[3] > 0.5 for pt in pose]
        slouch = bool(getattr(self.vision, "posture", None) and self.vision.posture.last.get("slouch"))
        p.setPen(QPen(QColor(255, 255, 255, 170) if slouch else QColor(255, 255, 255, 70), 2))
        for a, b in POSE_BONES:
            if seen[a] and seen[b]:
                p.drawLine(pts[a], pts[b])

    def _draw_vitals(self, p: QPainter, card: QRectF) -> None:
        """JARVIS read-out: distance, posture, gaze, blinks, hands, body."""
        v = self.vision
        rows: list[str] = []
        if getattr(v, "distance_cm", None):
            near = v.distance_cm < 40
            rows.append(f"Distancia a la pantalla: {v.distance_cm:.0f} cm" + (" (muy cerca)" if near else ""))
        stats = getattr(v, "face_stats", None)
        if stats is not None and stats.summary():
            rows.append("Ojos: " + stats.summary())
        posture = getattr(v, "posture", None)
        if posture is not None and posture.summary():
            rows.append("Cuerpo: " + posture.summary())
        if not rows:
            return
        p.setFont(_font(7.5, QFont.Weight.DemiBold))
        width = max(p.fontMetrics().horizontalAdvance(r) for r in rows) + 22
        height = 16 * len(rows) + 12
        box = QRectF(card.left() + 12, card.bottom() - height - 46, width, height)
        p.setPen(QPen(LINE, 1))
        p.setBrush(CARD)
        p.drawRoundedRect(box, 10, 10)
        p.setPen(TEXT)
        for i, row in enumerate(rows):
            p.drawText(QRectF(box.left() + 11, box.top() + 6 + i * 16, width, 16), Qt.AlignmentFlag.AlignVCenter, row)

    def _draw_mesh(self, p: QPainter) -> None:
        """Face reticle: name on the face, the measured points, head and mood."""
        from sergio_escritorio.vision import SIGNATURE_POINTS

        faces = list(getattr(self.vision, "faces", []) or [])
        if not faces or not getattr(self.vision, "mesh", True):
            return
        now = time.monotonic()
        people = [t for t in self.vision.tracker.visible(now) if t.kind == "persona"]
        for face in faces:
            pts = face.points
            if len(pts) < 468:
                continue
            owner = next((t for t in people if self._face_of(t, [face]) is face), None)
            known = bool(owner and owner.name)
            colour = KIND_COLORS["conocido" if known else "persona"]
            rect = self._map_box(face.box).adjusted(-8, -14, 8, 6)
            if not self.detail:
                # Clean view (owner, 24 Oct. 2026): no box or name follows the
                # face. Sergio keeps recognising it underneath; the detail
                # view still draws everything.
                continue
            self._brackets(p, rect, colour, 2.2)
            # The characteristic points (eyes, brows, nose, mouth, cheekbones,
            # jaw) and the distances between them that identify a person:
            # what the 175 measurements are made of. No face outline.
            spots = {name: self._map_point(*pts[i]) for name, i in SIGNATURE_POINTS.items() if i < len(pts)}
            line = QColor(colour).lighter(140)
            line.setAlpha(170)
            p.setPen(QPen(line, 1.1))
            for a, b in FACE_NETWORK:
                if a in spots and b in spots:
                    p.drawLine(spots[a], spots[b])
            dot = QColor(colour).lighter(160)
            dot.setAlpha(240)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dot)
            for spot in spots.values():
                p.drawEllipse(spot, 2.2, 2.2)
            # Where the head points: a short ray from the nose tip.
            nose = self._map_point(*pts[1])
            yaw = -face.yaw if self.mirror else face.yaw
            length = rect.width() * 0.45
            end = QPointF(
                nose.x() + length * math.sin(math.radians(yaw)),
                nose.y() - length * math.sin(math.radians(face.pitch)),
            )
            p.setPen(QPen(QColor(255, 255, 255, 150), 1.4))
            p.drawLine(nose, end)
            # Name tag right on the face.
            if owner is not None:
                label = owner.title(now)
                if known and owner.face_score:
                    label += f"  {owner.face_score * 100:.0f}%"
                elif not known and not owner.names:
                    label = "Identificando…"
            else:
                label = "Identificando…"
            p.setFont(_font(8.5, QFont.Weight.DemiBold))
            tw = p.fontMetrics().horizontalAdvance(label) + 16
            top = rect.top() - 22 if rect.top() - 22 > MARGIN + 40 else rect.bottom() + 24
            tag = QRectF(rect.center().x() - tw / 2, top, tw, 19)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colour)
            p.drawRoundedRect(tag, 9.5, 9.5)
            p.setPen(INK)  # light tag, black letters
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, label)
            if face.expressions:
                text = " · ".join(face.expressions)
                p.setFont(_font(7.5, QFont.Weight.DemiBold))
                tw = p.fontMetrics().horizontalAdvance(text) + 12
                below = rect.bottom() + 4 if top < rect.top() else tag.bottom() + 4
                chip = QRectF(rect.center().x() - tw / 2, below, tw, 16)
                p.setPen(QPen(LINE, 1))
                p.setBrush(CARD)
                p.drawRoundedRect(chip, 8, 8)
                p.setPen(TEXT)
                p.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_face_scan(self, p: QPainter, card: QRectF) -> None:
        """Face ID-style scan: the ring around your face fills as you turn
        your head; when done, the 3D map of your face turns in a paper card."""
        from sergio_escritorio import facescan

        scan = self.scanner
        now = time.monotonic()
        if scan.active:
            box = scan.box
            if box is not None:
                rect = self._map_box(box)
                centre = rect.center()
                radius = max(rect.width(), rect.height()) * 0.62
            else:
                centre = card.center()
                radius = min(card.width(), card.height()) * 0.28
            # Warm paper veil outside the scan circle.
            shade = QPainterPath()
            shade.addRect(card)
            hole = QPainterPath()
            hole.addEllipse(centre, radius - 4, radius - 4)
            p.fillPath(shade.subtracted(hole), QColor(0, 0, 0, 105))
            facescan.draw_ring(p, centre, radius, scan.ring, now, self.mirror)
            percent = int(round(scan.ring.fraction / facescan.DONE_FRACTION * 100))
            self._scan_pill(p, card, f"{scan.message}   {min(percent, 100)}%")
            return
        if scan.result is None or now - scan.finished_at > 6.0:
            return
        # The learnt face, in 3D, turning in a dark card.
        size = min(card.width(), card.height()) * 0.62
        panel = QRectF(card.center().x() - size * 0.62, card.center().y() - size * 0.5, size * 1.24, size)
        p.setPen(QPen(LINE, 1.2))
        p.setBrush(CARD)
        p.drawRoundedRect(panel, 20, 20)
        if self._scan_edges is None:
            self._scan_edges = facescan.mesh_edges()
        head = panel.adjusted(18, 14, -18, -54)
        turn = math.sin((now - scan.finished_at) * 1.3) * 1.1
        facescan.draw_head(p, head, scan.result.get("points") or [], turn, self._scan_edges)
        p.setPen(TEXT)
        lines = [line for line in (self.scan_text or ["Mapa 3D guardado"])[:2] if line]
        for i, line in enumerate(lines):
            size = 9.0 if i == 0 else 8.0
            p.setFont(_font(size, QFont.Weight.DemiBold if i == 0 else QFont.Weight.Normal))
            while size > 6.5 and p.fontMetrics().horizontalAdvance(line) > panel.width() - 24:
                size -= 0.5
                p.setFont(_font(size, QFont.Weight.DemiBold if i == 0 else QFont.Weight.Normal))
            text = p.fontMetrics().elidedText(line, Qt.TextElideMode.ElideRight, int(panel.width() - 24))
            p.drawText(
                QRectF(panel.left() + 12, panel.bottom() - 48 + i * 19, panel.width() - 24, 18),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )

    def _scan_pill(self, p: QPainter, card: QRectF, text: str) -> None:
        p.setFont(_font(9, QFont.Weight.DemiBold))
        tw = p.fontMetrics().horizontalAdvance(text) + 28
        pill = QRectF(card.center().x() - tw / 2, card.bottom() - 58, tw, 30)
        p.setPen(QPen(LINE, 1))
        p.setBrush(CARD)
        p.drawRoundedRect(pill, 15, 15)
        p.setPen(TEXT)
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_scan(self, p: QPainter, pts: list, rect: QRectF, colour: QColor, now: float) -> None:
        """Analysing a face: a bright line sweeps it top to bottom and back,
        lighting up the mesh points it crosses (a 3D scanner, Face ID style)."""
        phase = (now * 0.9) % 2.0
        sweep = phase if phase < 1.0 else 2.0 - phase  # down, then up
        y = rect.top() + sweep * rect.height()
        band = max(10.0, rect.height() * 0.09)
        glow = QLinearGradient(QPointF(0, y - band * 2), QPointF(0, y + band * 2))
        tint = QColor(colour).lighter(150)
        for stop, alpha in ((0.0, 0), (0.5, 70), (1.0, 0)):
            tint.setAlpha(alpha)
            glow.setColorAt(stop, tint)
        p.fillRect(QRectF(rect.left(), y - band * 2, rect.width(), band * 4), glow)
        line = QColor(colour).lighter(170)
        line.setAlpha(230)
        p.setPen(QPen(line, 1.4))
        p.drawLine(QPointF(rect.left() + 4, y), QPointF(rect.right() - 4, y))
        p.setPen(Qt.PenStyle.NoPen)
        dot = QColor(colour).lighter(175)
        for x, py in pts:
            spot = self._map_point(x, py)
            near = abs(spot.y() - y)
            if near > band * 2.2:
                dot.setAlpha(26)  # the whole mesh, faint: it is being read
                p.setBrush(dot)
                p.drawEllipse(spot, 0.9, 0.9)
                continue
            dot.setAlpha(int(70 + 185 * (1.0 - near / (band * 2.2))))
            p.setBrush(dot)
            p.drawEllipse(spot, 1.7, 1.7)

    def _draw_lock(self, p: QPainter, rect: QRectF, colour: QColor, since: float) -> None:
        """Just recognised: a ring closes on the face and fades (0.7 s)."""
        if not 0.0 <= since < 0.7:
            return
        k = since / 0.7
        ring = QColor(colour).lighter(150)
        ring.setAlpha(int(220 * (1.0 - k)))
        p.setPen(QPen(ring, 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        grow = (1.0 - k) * 18.0
        p.drawRoundedRect(rect.adjusted(-grow, -grow, grow, grow), 16, 16)

    def _face_tag(self, p: QPainter, rect: QRectF, owner: Any, known: bool, now: float) -> None:
        label = owner.title(now, clean=True) if owner is not None else "Identificando…"
        if owner is not None and not known and not owner.names:
            label = "Identificando…"
        p.setFont(_font(8.5, QFont.Weight.DemiBold))
        tw = p.fontMetrics().horizontalAdvance(label) + 16
        top = rect.top() - 22 if rect.top() - 22 > MARGIN + 40 else rect.bottom() + 4
        tag = QRectF(rect.center().x() - tw / 2, top, tw, 19)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(KIND_COLORS["conocido" if known else "persona"])
        p.drawRoundedRect(tag, 9.5, 9.5)
        p.setPen(INK)  # light tag, black letters
        p.drawText(tag, Qt.AlignmentFlag.AlignCenter, label)

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
        if not self.detail:
            return  # clean view: nothing follows the face (it is still recognised)
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
                (f"{face['name']}  {face['score'] * 100:.0f}%" if self.detail else face["name"])
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
            p.setPen(INK)  # light tag, black letters
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_hands(self, p: QPainter) -> None:
        hands = getattr(self.hands, "hands", None) or []
        if not hands or getattr(self.hands, "mode", "off") == "off" or self._shown is None:
            return
        lit = QColor(255, 255, 255)  # what you hold
        seeing = getattr(self.hands, "mode", "off") == "ver"
        for i, hand in enumerate(hands[:2]):
            pts = [self._map_point(x, y) for x, y, *_ in hand.landmarks]
            p.setPen(QPen(QColor(255, 255, 255, 120), 1.4))
            for a, b in BONES:
                p.drawLine(pts[a], pts[b])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 170))
            for pt in pts:
                p.drawEllipse(pt, 2, 2)
            if seeing and not self.detail:
                continue  # clean view: the hand's points, no read-out
            if seeing:
                from sergio_escritorio.body import hand_summary

                text = hand_summary(hand.landmarks, hand.side, self.mirror)
                p.setFont(_font(7.5, QFont.Weight.DemiBold))
                tw = p.fontMetrics().horizontalAdvance(text) + 12
                top = min(pt.y() for pt in pts)
                mid = sum(pt.x() for pt in pts) / len(pts)
                chip = QRectF(mid - tw / 2, max(top - 24, 46), tw, 16)
                p.setBrush(QColor(0, 0, 0, 150))
                p.drawRoundedRect(chip, 8, 8)
                p.setPen(QColor(255, 255, 255))
                p.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)
                continue
            # The pinch point: a ring that closes and glows when you grab.
            pinch = (pts[4] + pts[8]) / 2
            holding = self.holo.pinching.get(i, False)
            hint = ""
            if time.monotonic() < self.guide_until:  # words only while learning; then a clean view
                hint = "gira la muñeca · abre para soltar" if holding else ("pellizca para agarrar" if i in self.holo.hover else "")
            if hint:
                p.setFont(_font(7, QFont.Weight.DemiBold))
                tw = p.fontMetrics().horizontalAdvance(hint) + 14
                chip = QRectF(pinch.x() - tw / 2, pinch.y() + 16, tw, 16)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 140))
                p.drawRoundedRect(chip, 8, 8)
                p.setPen(QColor(255, 255, 255, 230))
                p.drawText(chip, Qt.AlignmentFlag.AlignCenter, hint)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(lit if holding else QColor(255, 255, 255, 150), 2.2 if holding else 1.2))
            r = 7 if holding else 11
            p.drawEllipse(pinch, r, r)
            if holding:
                glow = QColor(lit)
                glow.setAlpha(60)
                p.setPen(QPen(glow, 6))
                p.drawEllipse(pinch, r + 3, r + 3)

    HOLO_GUIDE = (
        ("Junta pulgar e índice sobre una figura", "la agarras · brilla cuando está a tu alcance"),
        ("Mueve la mano y gira la muñeca", "la mueves y la giras (acerca la mano = más cerca)"),
        ("Agárrala con las dos manos y sepáralas", "más grande / más pequeña"),
        ("Abre la mano mientras la mueves", "la lanzas"),
        ("«crea una estrella» · «un corazón rojo» · «un teléfono»", "cualquier figura u objeto"),
        ("«estilo cristal» / «estilo holograma»", "vidrio esmerilado o luz azul JARVIS"),
        ("«pásalo a Blender»", "se abre en Blender y lo sigue moviendo tu mano"),
        ("Sin manos: arrastra · clic derecho gira · Ctrl+rueda", "con el ratón"),
    )

    def _draw_holo_guide(self, p: QPainter, card: QRectF) -> None:
        """The how-to, JARVIS style, while it is new (or when asked)."""
        now = time.monotonic()
        holo_on = getattr(self.hands, "mode", "off") == "holo"
        if not holo_on or now > self.guide_until:
            if holo_on and not self.holo.objects:
                p.setFont(_font(9, QFont.Weight.DemiBold))
                p.setPen(TEXT)
                p.drawText(QRectF(card.left(), card.top() + 46, card.width(), 20), Qt.AlignmentFlag.AlignCenter,
                           "Di «crea un cubo» · «ayuda hologramas» para ver los gestos")
            return
        fade = min(1.0, (self.guide_until - now) / 1.5)
        width, row = min(400.0, card.width() * 0.52), 34.0
        box = QRectF(card.right() - width - 12, card.top() + 48, width, 30 + row * len(self.HOLO_GUIDE))
        p.setOpacity(fade)
        p.setPen(QPen(LINE, 1.2))
        p.setBrush(QColor(33, 33, 33, 235))
        p.drawRoundedRect(box, 12, 12)
        p.setFont(_font(8, QFont.Weight.Bold))
        p.setPen(TEXT)
        p.drawText(QRectF(box.left() + 12, box.top() + 6, width, 18), Qt.AlignmentFlag.AlignLeft, "HOLOGRAMAS · CÓMO SE USAN")
        for i, (how, what) in enumerate(self.HOLO_GUIDE):
            y = box.top() + 28 + i * row
            p.setFont(_font(9, QFont.Weight.DemiBold))
            p.setPen(QColor(estilo.SECONDARY))
            p.drawText(QRectF(box.left() + 8, y, 28, row), Qt.AlignmentFlag.AlignCenter, str(i + 1))
            p.setFont(_font(7.5, QFont.Weight.DemiBold))
            p.setPen(TEXT)
            how = p.fontMetrics().elidedText(how, Qt.TextElideMode.ElideRight, int(width - 48))
            p.drawText(QRectF(box.left() + 40, y + 2, width - 48, 16), Qt.AlignmentFlag.AlignLeft, how)
            p.setFont(_font(7))
            p.setPen(QColor(estilo.SECONDARY))
            p.drawText(QRectF(box.left() + 40, y + 16, width - 48, 14), Qt.AlignmentFlag.AlignLeft, what)
        p.setOpacity(1.0)

    def _draw_holo(self, p: QPainter, card: QRectF) -> None:
        """Holograms, Iron Man style: glowing blue light, scanlines, a
        projector ring under each one and rotating rings when you hold it."""
        scene = self.holo
        if scene.objects or scene.stroke:
            if scene.style == "cristal":
                self._draw_glass(p, card)
                self._draw_stroke(p, card)
            else:
                self._draw_jarvis(p, card)
        self._draw_holo_guide(p, card)  # on top of everything

    def _draw_jarvis(self, p: QPainter, card: QRectF) -> None:
        """The JARVIS-blue light look («estilo holograma»)."""
        scene = self.holo
        ox, oy = card.left(), card.top()
        w, h = card.width(), card.height()
        if scene.gravity:  # the floor they bounce on, in perspective
            import numpy as np

            from sergio_escritorio.holo import FLOOR, project

            p.setPen(QPen(QColor(100, 210, 255, 50), 1))
            for x in np.linspace(-2.4, 2.4, 13):
                ends, _depth = project(np.array([[x, FLOOR, 1.2], [x, FLOOR, -2.4]]), w, h)
                p.drawLine(QPointF(ox + ends[0][0], oy + ends[0][1]), QPointF(ox + ends[1][0], oy + ends[1][1]))
            for z in np.linspace(1.2, -2.4, 7):
                ends, _depth = project(np.array([[-2.4, FLOOR, z], [2.4, FLOOR, z]]), w, h)
                p.drawLine(QPointF(ox + ends[0][0], oy + ends[0][1]), QPointF(ox + ends[1][0], oy + ends[1][1]))
        import numpy as np

        from sergio_escritorio.holo import project as _proj

        t = time.monotonic()
        for obj in scene.objects:  # projector ring + light cone under each one
            base = obj.pos - np.array([0.0, obj.radius() * 1.15, 0.0])
            (bx, by), = _proj(base[None], w, h)[0]
            (tx, ty), = _proj(obj.pos[None], w, h)[0]
            rx = max(14.0, abs(_proj((obj.pos + np.array([obj.radius(), 0, 0]))[None], w, h)[0][0][0] - tx))
            centre = QPointF(ox + bx, oy + by)
            grad = QLinearGradient(centre, QPointF(ox + tx, oy + ty))
            grad.setColorAt(0, QColor(80, 200, 255, 70))
            grad.setColorAt(1, QColor(80, 200, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawPolygon(QPolygonF([QPointF(centre.x() - rx, centre.y()), QPointF(centre.x() + rx, centre.y()),
                                     QPointF(ox + tx + rx * 0.6, oy + ty), QPointF(ox + tx - rx * 0.6, oy + ty)]))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for k, alpha in ((1.0, 200), (1.25, 90)):
                p.setPen(QPen(QColor(100, 215, 255, alpha), 1.4))
                p.drawEllipse(centre, rx * k, rx * k * 0.28)
            if obj.held:  # targeting rings, turning
                for k, speed in ((1.15, 90), (1.3, -60)):
                    ring = QRectF(ox + tx - rx * k, oy + ty - rx * k, 2 * rx * k, 2 * rx * k)
                    p.setPen(QPen(QColor(120, 225, 255, 170), 1.3, Qt.PenStyle.DashLine))
                    p.drawArc(ring, int((t * speed) % 360 * 16), 250 * 16)
        for face in scene.render(w, h):
            r, g, b = face["color"]
            poly = QPolygonF([QPointF(ox + x, oy + y) for x, y in face["points"]])
            if face.get("model"):
                # A designed object: its real materials, lit, with a blue
                # holographic sheen; no wire grid over curved surfaces.
                if not face["front"]:
                    continue
                k = face["shade"]
                r, g, b = 0.72 * r + 0.08, 0.72 * g + 0.17, 0.72 * b + 0.22
                fill = QColor.fromRgbF(min(1, r * k + 0.04), min(1, g * k + 0.06), min(1, b * k + 0.08), 0.9)
                p.setBrush(fill)
                p.setPen(QPen(fill, 0.6))
                p.drawPolygon(poly)
                continue
            # Hologram light: every colour glows toward JARVIS blue.
            r, g, b = 0.45 * r + 0.25, 0.45 * g + 0.5, 0.45 * b + 0.55
            if face["front"]:
                k = face["shade"]
                alpha = 0.58 if face["held"] else 0.42
                p.setBrush(QColor.fromRgbF(min(1, r * k), min(1, g * k), min(1, b * k), alpha))
                edge = QColor.fromRgbF(min(1, 0.35 + r * 0.8), min(1, 0.35 + g * 0.8), min(1, 0.35 + b * 0.8), 0.95)
                p.setPen(QPen(edge, 1.3 if face["held"] else 0.9))
            else:  # the far side shows through, faintly
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor.fromRgbF(r, g, b, 0.16), 0.7))
            p.drawPolygon(poly)
        # Scanlines drifting over the holograms (the projected-light look).
        p.setPen(QPen(QColor(150, 230, 255, 18), 1))
        offset = (t * 22) % 6
        y = card.top() + offset
        while y < card.bottom():
            p.drawLine(QPointF(card.left(), y), QPointF(card.right(), y))
            y += 6
        # Names and sizes above each hologram.

        from sergio_escritorio.holo import project as _project

        p.setFont(_font(7.5, QFont.Weight.DemiBold))
        for obj in scene.objects:
            top = obj.pos + np.array([0.0, obj.radius() * 1.05, 0.0])
            (tx, ty), = _project(top[None], w, h)[0]
            label = f"{obj.name} · {obj.size_cm()} cm"
            p.setPen(QColor(200, 240, 255, 230 if obj.held else 170))
            ly = max(oy + ty - 4, oy + 62)  # never under the top pill
            p.drawText(QPointF(ox + tx - p.fontMetrics().horizontalAdvance(label) / 2, ly), label)
        self._draw_stroke(p, card)

    def _draw_stroke(self, p: QPainter, card: QRectF) -> None:
        """The stroke you are drawing in the air."""
        ox, oy, w, h = card.left(), card.top(), card.width(), card.height()
        pts = self.holo.stroke_points(w, h)
        if len(pts) >= 2:
            line = QPolygonF([QPointF(ox + x, oy + y) for x, y in pts])
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(100, 210, 255, 70), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPolyline(line)
            p.setPen(QPen(QColor(220, 248, 255), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPolyline(line)

    def _draw_glass(self, p: QPainter, card: QRectF) -> None:
        """Apple-style glass: the room behind seen frosted through each shape,
        lit from the top left, a thin-film rainbow where the surface turns
        away and a crisp iridescent rim along the silhouette."""
        ox, oy, w, h = card.left(), card.top(), card.width(), card.height()
        frost = getattr(self, "_frost", None)
        shown = self._shown

        def pt(xy: Any) -> QPointF:
            return QPointF(ox + float(xy[0]), oy + float(xy[1]))

        shapes = self.holo.glass(w, h)
        busy = any(o.get("hover_k", 0.0) > 0.3 for o in shapes)  # one ornament at a time
        for ob in shapes:
            cx, cy = ob["centre"]
            centre = QPointF(ox + cx, oy + cy)
            radius = max(ob["radius"], 8.0)
            lift, appear, hover_k = ob.get("lift", 0.0), ob.get("appear", 1.0), ob.get("hover_k", 0.0)
            p.setOpacity(max(0.0, min(1.0, appear * 1.15)))  # pops in, fading up
            # Soft contact shadow below: picked up, it drifts lower and softer
            # (the object rises toward you, like a visionOS window in your hand).
            drop = radius * (1.05 + 0.28 * lift)
            spread = radius * (0.7 + 0.25 * lift)
            shadow = QRadialGradient(QPointF(centre.x(), centre.y() + drop), spread)
            shadow.setColorAt(0, QColor(0, 0, 0, int(45 - 18 * lift)))
            shadow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(shadow)
            p.drawEllipse(QPointF(centre.x(), centre.y() + drop), spread, radius * (0.14 + 0.06 * lift))
            body = QPainterPath()
            body.setFillRule(Qt.FillRule.WindingFill)
            for f in ob["faces"]:
                body.addPolygon(QPolygonF([pt(xy) for xy in f["points"]]))
                body.closeSubpath()
            if body.isEmpty():
                continue
            r, g, b = ob["color"]
            p.save()
            p.setClipPath(body)
            if ob["model"]:  # a designed object keeps its real materials
                for f in ob["faces"]:
                    fr, fg, fb = f["color"]
                    k = f["shade"]
                    p.setBrush(QColor.fromRgbF(min(1, fr * k + 0.05), min(1, fg * k + 0.05), min(1, fb * k + 0.06), 0.9))
                    p.drawPolygon(QPolygonF([pt(xy) for xy in f["points"]]))
            elif ob.get("smooth"):
                if frost is not None and shown is not None:
                    p.drawImage(shown[0], frost)
                p.fillPath(body, QColor.fromRgbF(r, g, b, 0.14))
                # Continuous light over the rounded silhouette avoids the
                # staircase of flat face tones, without a per-frame blur.
                light = QLinearGradient(centre.x() - radius, centre.y() - radius,
                                        centre.x() + radius, centre.y() + radius)
                light.setColorAt(0, QColor(245, 251, 255, 72))
                light.setColorAt(0.48, QColor(195, 220, 245, 18))
                light.setColorAt(1, QColor(10, 20, 35, 60))
                p.fillPath(body, QBrush(light))
            else:
                if frost is not None and shown is not None:
                    p.drawImage(shown[0], frost)  # the room, frosted
                p.fillPath(body, QColor.fromRgbF(r, g, b, 0.14))  # a hint of colour
                for f in ob["faces"]:
                    poly = QPolygonF([pt(xy) for xy in f["points"]])
                    k = f["shade"]
                    light = QColor(255, 255, 255, int(max(0.0, k - 0.55) * 150)) if k > 0.55 else QColor(10, 20, 40, int((0.55 - k) * 110))
                    p.setBrush(light)
                    p.drawPolygon(poly)
                    if f["rim"] > 0.55:  # a faint cool sheen toward the edges (Sergio glass)
                        hue = 0.57  # stable cool tint; no distracting colour cycling
                        film = QColor.fromHsvF(hue % 1.0, 0.18, 1.0, min(0.14, (f["rim"] - 0.55) * 0.4))
                        p.setBrush(film)
                        p.drawPolygon(poly)
            # The shine where the light hits, and a glow at the bottom.
            shine = QRadialGradient(QPointF(centre.x() - radius * 0.35, centre.y() - radius * 0.45), radius * 0.8)
            shine.setColorAt(0, QColor(255, 255, 255, 155))
            shine.setColorAt(0.5, QColor(255, 255, 255, 30))
            shine.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillPath(body, QBrush(shine))
            glow = QRadialGradient(QPointF(centre.x() + radius * 0.25, centre.y() + radius * 0.6), radius * 0.7)
            glow.setColorAt(0, QColor(200, 230, 255, 55))
            glow.setColorAt(1, QColor(200, 230, 255, 0))
            p.fillPath(body, QBrush(glow))
            p.restore()

            def segs(lines: list) -> QPainterPath:
                path = QPainterPath()
                for a, b2 in lines:
                    path.moveTo(pt(a))
                    path.lineTo(pt(b2))
                return path

            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 40), 0.8))
            p.drawPath(segs(ob["back_edges"]))  # seen through the glass
            p.setPen(QPen(QColor(255, 255, 255, 150), 1.1))
            p.drawPath(segs(ob["edges"]))
            outline = segs(ob["outline"])
            active = ob["held"] or ob["hover"]
            if hover_k > 0.02:  # what a pinch would take (or is holding) glows, fading in
                p.setPen(QPen(QColor(255, 255, 255, int(90 * hover_k)), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawPath(outline)
            # visionOS glass edge: a fine white rim, brighter where the light
            # comes from (top left), fading toward the bottom right.
            rim = QLinearGradient(centre.x() - radius, centre.y() - radius, centre.x() + radius, centre.y() + radius)
            rim.setColorAt(0.0, QColor(255, 255, 255, 235))
            rim.setColorAt(0.45, QColor(255, 255, 255, 120))
            rim.setColorAt(1.0, QColor(255, 255, 255, 55))
            p.setPen(QPen(QBrush(rim), 1.9 if active else 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(outline)
            show = max(hover_k, 0.75 if ob["selected"] and not busy else 0.0)
            if show > 0.03:
                # visionOS ornament: a glass capsule under the object with its
                # name and real size, and the grab bar beneath it.
                label = f"{ob['name']} · {ob['size_cm']} cm"
                p.setFont(_font(7.5, QFont.Weight.DemiBold))
                tw = p.fontMetrics().horizontalAdvance(label) + 20
                y = min(oy + h - 40, centre.y() + radius * (1.2 + 0.28 * lift) + 6 - 4 * (1 - show))
                chip = QRectF(centre.x() - tw / 2, y, tw, 20)
                p.setPen(QPen(QColor(255, 255, 255, int(110 * show)), 0.8))
                p.setBrush(QColor(38, 40, 46, int(170 * show)))
                p.drawRoundedRect(chip, 10, 10)
                p.setPen(QColor(255, 255, 255, int(240 * show)))
                p.drawText(chip, Qt.AlignmentFlag.AlignCenter, label)
                bar_w = 34 + 10 * lift  # the grab bar stretches while held
                bar = QRectF(centre.x() - bar_w / 2, chip.bottom() + 6, bar_w, 5)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, int((110 + 90 * lift) * show)))
                p.drawRoundedRect(bar, 2.5, 2.5)
            p.setOpacity(1.0)

    def _draw_pill(self, p: QPainter, card: QRectF, t: float) -> None:
        text = "Vista"
        if self.vision is not None:
            from collections import Counter

            from sergio_escritorio.vision import salient

            tracks = salient(self.vision.tracker.visible(time.monotonic()), clean=not self.detail)
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
        if self.holo.objects or getattr(self.hands, "mode", "off") == "holo":
            n = len(self.holo.objects)
            mode = {"mover": "", "esculpir": " · esculpir", "dibujar": f" · dibujar ({self.holo.pen})"}
            text += f" · {n} holograma{'s' if n != 1 else ''}{mode.get(self.holo.mode, '')}"
        p.setFont(_font(8.5, QFont.Weight.DemiBold))
        width = p.fontMetrics().horizontalAdvance(text) + 36
        pill = QRectF(card.left() + 10, card.top() + 10, width, 28)
        p.setPen(QPen(LINE, 1))
        p.setBrush(CARD)
        p.drawRoundedRect(pill, 14, 14)
        pulse = 0.55 + 0.45 * abs(math.sin(t * 2.2))
        dot = QColor(TEXT)
        dot.setAlphaF(pulse)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dot)
        p.drawEllipse(QPointF(pill.left() + 14, pill.center().y()), 4.2, 4.2)
        p.setPen(TEXT)
        p.drawText(
            QRectF(pill.left() + 24, pill.top(), pill.width() - 28, pill.height()),
            Qt.AlignmentFlag.AlignVCenter,
            text,
        )

    def _draw_close(self, p: QPainter) -> None:
        close = self._close_rect()
        p.setPen(QPen(LINE, 1))
        p.setBrush(CARD)
        p.drawEllipse(close)
        p.setPen(QPen(TEXT, 1.6))
        c = close.center()
        p.drawLine(QPointF(c.x() - 4, c.y() - 4), QPointF(c.x() + 4, c.y() + 4))
        p.drawLine(QPointF(c.x() + 4, c.y() - 4), QPointF(c.x() - 4, c.y() + 4))

    def _draw_caption(self, p: QPainter, card: QRectF) -> None:
        shown = int((time.monotonic() - self._overlay_at) * 60)
        text = self.overlay[: max(0, shown)]
        p.setFont(_font(9.5, QFont.Weight.DemiBold))
        box = QRectF(card.left() + 12, card.bottom() - 56, card.width() - 24, 44)
        p.setPen(QPen(LINE, 1))
        p.setBrush(CARD)
        p.drawRoundedRect(box, 12, 12)
        p.setPen(TEXT)
        p.drawText(
            box.adjusted(12, 4, -12, -4),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
            | Qt.TextFlag.TextWordWrap,
            text,
        )


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(estilo.FALLBACK)  # body text in the system font, like the app
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


__all__ = ["CameraFeed", "CameraWindow", "FaceWatcher", "detect_faces", "to_qimage"]

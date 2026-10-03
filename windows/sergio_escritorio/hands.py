"""Sergio sees your hands (webcam + MediaPipe): gestures, an air mouse and 3D.

Modes (camera window "Manos" button, or by voice):

* ``gestos`` — gestures are actions: 👍 says "sí" to Sergio (confirm),
  ✋ open palm stops him talking, ✌️ asks him what he sees.
* ``mouse`` — an air mouse: your index finger moves the pointer, a pinch
  (thumb + index) clicks, holding the pinch drags, a fist pauses.
* ``3d`` — your hands drive Blender live (see :data:`BLENDER_BRIDGE`): pinch
  and move to rotate the selected object, pinch with both hands to scale,
  a fist moves it, 👍 adds a shape, ✌️ duplicates.

The gesture maths is pure (lists of 21 landmarks) so it is tested without a
camera; MediaPipe only turns frames into landmarks.
"""

from __future__ import annotations

import json
import logging
import math
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

log = logging.getLogger(__name__)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
MODEL_PATH = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "SergioEscritorio"
    / "models"
    / "hand_landmarker.task"
)
BLENDER_PORT = 9877
MODES = {
    "off": "Apagado",
    "gestos": "Gestos",
    "mouse": "Mouse en el aire",
    "3d": "Modelar en 3D",
}

# MediaPipe hand landmark indices.
WRIST, THUMB_IP, THUMB_TIP = 0, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20

Point = Sequence[float]  # (x, y[, z]) normalised 0..1, y grows downwards


def _d(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def palm_size(lm: Sequence[Point]) -> float:
    return max(1e-6, _d(lm[WRIST], lm[MIDDLE_MCP]))


def fingers_up(lm: Sequence[Point]) -> list[bool]:
    """[thumb, index, middle, ring, pinky] extended (rotation independent)."""
    wrist = lm[WRIST]
    out = []
    # Thumb: its tip is well away from the index knuckle and the palm.
    thumb = _d(lm[THUMB_TIP], lm[INDEX_MCP]) > 0.55 * palm_size(lm) and _d(
        lm[THUMB_TIP], lm[PINKY_MCP]
    ) > _d(lm[THUMB_IP], lm[PINKY_MCP])
    out.append(thumb)
    for pip, tip in (
        (INDEX_PIP, INDEX_TIP),
        (MIDDLE_PIP, MIDDLE_TIP),
        (RING_PIP, RING_TIP),
        (PINKY_PIP, PINKY_TIP),
    ):
        out.append(_d(lm[tip], wrist) > _d(lm[pip], wrist) * 1.12)
    return out


def pinch_ratio(lm: Sequence[Point]) -> float:
    """Thumb–index tip distance relative to the palm (small = pinching)."""
    return _d(lm[THUMB_TIP], lm[INDEX_TIP]) / palm_size(lm)


def gesture(lm: Sequence[Point]) -> str:
    """'pinch', 'thumbs_up', 'fist', 'open', 'point', 'victory' or 'none'."""
    if len(lm) < 21:
        return "none"
    thumb, index, middle, ring, pinky = fingers_up(lm)
    others = [index, middle, ring, pinky]
    # Pinch: thumb and index tips together with the index reaching out (in a
    # fist the thumb also touches the curled index, but it stays near the wrist).
    reach = _d(lm[INDEX_TIP], lm[WRIST]) / palm_size(lm)
    if pinch_ratio(lm) < 0.28 and reach > 1.1:
        return "pinch"
    if thumb and not any(others):
        # 👍 only if the thumb points up (above the wrist on screen).
        return (
            "thumbs_up"
            if lm[THUMB_TIP][1] < lm[WRIST][1] - 0.4 * palm_size(lm)
            else "none"
        )
    if not any(others):
        return "fist"
    if all(others):
        return "open"
    if index and not middle and not ring and not pinky:
        return "point"
    if index and middle and not ring and not pinky:
        return "victory"
    return "none"


@dataclass
class Hand:
    landmarks: list[tuple[float, float, float]]
    side: str = ""  # "Left" / "Right" as MediaPipe reports it

    @property
    def gesture(self) -> str:
        return gesture(self.landmarks)

    @property
    def tip(self) -> tuple[float, float]:
        return self.landmarks[INDEX_TIP][0], self.landmarks[INDEX_TIP][1]

    @property
    def centre(self) -> tuple[float, float]:
        xs = [p[0] for p in self.landmarks]
        ys = [p[1] for p in self.landmarks]
        return sum(xs) / len(xs), sum(ys) / len(ys)


# -- MediaPipe ----------------------------------------------------------------
def ensure_model(path: Path = MODEL_PATH) -> Path:
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    import httpx

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with httpx.stream("GET", MODEL_URL, timeout=120, follow_redirects=True) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    tmp.replace(path)
    return path


class HandTracker:
    """Frame (OpenCV BGR) -> hands. Loads MediaPipe lazily."""

    def __init__(self, model: Path | None = None, max_hands: int = 2) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model or ensure_model())),
            num_hands=max_hands,
            min_hand_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._mp = mp
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def detect(self, frame_bgr: Any) -> list[Hand]:
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(image)
        hands = []
        for i, marks in enumerate(result.hand_landmarks or []):
            side = ""
            if result.handedness and i < len(result.handedness):
                side = result.handedness[i][0].category_name
            hands.append(Hand([(m.x, m.y, m.z) for m in marks], side))
        return hands


# -- what the gestures do -------------------------------------------------------
@dataclass
class Debounce:
    """A gesture must be held a moment before it counts (no accidents)."""

    hold: float = 0.6
    _current: str = "none"
    _since: float = 0.0
    _fired: bool = False

    def update(self, name: str, now: float) -> str | None:
        if name != self._current:
            self._current, self._since, self._fired = name, now, False
            return None
        if not self._fired and name != "none" and now - self._since >= self.hold:
            self._fired = True
            return name
        return None


@dataclass
class AirMouse:
    """Index finger -> pointer; pinch = click, held pinch = drag, fist = clutch."""

    screen: tuple[int, int]
    box: tuple[float, float, float, float] = (0.2, 0.2, 0.8, 0.8)  # active area
    smooth: float = 0.35
    drag_after: float = 0.6
    _pos: tuple[float, float] | None = None
    _pinch_at: float | None = None
    _dragging: bool = False

    def target(self, tip: tuple[float, float], mirror: bool = True) -> tuple[int, int]:
        x0, y0, x1, y1 = self.box
        u = (tip[0] - x0) / (x1 - x0)
        v = (tip[1] - y0) / (y1 - y0)
        if mirror:  # the camera sees you mirrored
            u = 1 - u
        u, v = min(1.0, max(0.0, u)), min(1.0, max(0.0, v))
        x, y = u * (self.screen[0] - 1), v * (self.screen[1] - 1)
        if self._pos is None:
            self._pos = (x, y)
        else:
            px, py = self._pos
            self._pos = (px + (x - px) * self.smooth, py + (y - py) * self.smooth)
        return round(self._pos[0]), round(self._pos[1])

    def step(self, hand: Hand, now: float) -> list[tuple[str, int, int]]:
        """Events for this frame: ('move'|'click'|'down'|'up', x, y)."""
        name = hand.gesture
        if name == "fist":  # clutch: re-centre your hand without moving
            return self._release()
        x, y = self.target(hand.tip)
        events: list[tuple[str, int, int]] = [("move", x, y)]
        if name == "pinch":
            if self._pinch_at is None:
                self._pinch_at = now
            elif not self._dragging and now - self._pinch_at >= self.drag_after:
                self._dragging = True
                events.append(("down", x, y))
        else:
            if self._pinch_at is not None and not self._dragging:
                events.append(("click", x, y))
            events += self._release()
        return events

    def _release(self) -> list[tuple[str, int, int]]:
        events = []
        if self._dragging and self._pos is not None:
            events.append(("up", round(self._pos[0]), round(self._pos[1])))
        self._dragging = False
        self._pinch_at = None
        return events


def blender_packet(hands: list[Hand], now: float) -> dict:
    """What Blender receives ~20 times a second."""
    data: dict[str, Any] = {"t": now, "hands": []}
    for hand in hands:
        cx, cy = hand.centre
        data["hands"].append(
            {
                "gesture": hand.gesture,
                "x": 1 - cx,  # mirrored, like a selfie
                "y": cy,
                "z": hand.landmarks[INDEX_TIP][2],
                "pinch": pinch_ratio(hand.landmarks),
            }
        )
    return data


@dataclass
class HandControl:
    """Runs the chosen mode on frames from the camera feed (own thread)."""

    frames: Callable[[], Any]  # latest BGR frame or None
    on_gesture: Callable[[str], None] = lambda _g: None
    mouse_events: Callable[[list[tuple[str, int, int]]], None] = lambda _e: None
    screen: tuple[int, int] = (1920, 1080)
    tracker_factory: Callable[[], Any] = HandTracker
    mode: str = "off"
    hands: list[Hand] = field(default_factory=list)
    error: str = ""
    _thread: threading.Thread | None = None
    _sock: Any = None

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in MODES else "off"
        self.error = ""
        if self.mode != "off" and (self._thread is None or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def process(
        self, hands: list[Hand], now: float, debounce: Debounce, mouse: AirMouse
    ) -> None:
        """One frame of work for the current mode (pure enough to test)."""
        self.hands = hands
        main = hands[0] if hands else None
        if self.mode == "gestos":
            fired = debounce.update(main.gesture if main else "none", now)
            if fired:
                self.on_gesture(fired)
        elif self.mode == "mouse" and main is not None:
            events = mouse.step(main, now)
            if events:
                self.mouse_events(events)
        elif self.mode == "3d":
            self._send(blender_packet(hands, now))

    def _send(self, packet: dict) -> None:
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self._sock.sendto(json.dumps(packet).encode(), ("127.0.0.1", BLENDER_PORT))
        except OSError:
            pass

    def _loop(self) -> None:
        try:
            tracker = self.tracker_factory()
        except Exception as exc:  # noqa: BLE001 — no mediapipe / no model
            log.exception("hand tracking unavailable")
            self.error = f"No puedo ver tus manos: {exc}"
            self.mode = "off"
            return
        debounce, mouse = Debounce(), AirMouse(self.screen)
        while self.mode != "off":
            frame = self.frames()
            if frame is None:
                time.sleep(0.1)
                continue
            try:
                hands = tracker.detect(frame)
            except Exception:  # noqa: BLE001
                log.exception("hand detection failed")
                hands = []
            self.process(hands, time.monotonic(), debounce, mouse)
            time.sleep(1 / 20)
        self.hands = []


# Blender add-on (run with blender --python): listens for hand packets and
# moves the active object. Pinch+move rotates, two pinches scale, a fist
# moves it, thumbs up adds a cube, victory duplicates.
BLENDER_BRIDGE = r"""
import bpy, json, socket

PORT = %(port)d
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_sock.bind(("127.0.0.1", PORT))
_sock.setblocking(False)
_state = {"last": None, "spread": None, "cool": 0.0}


def _active():
    obj = bpy.context.view_layer.objects.active
    if obj is None and bpy.context.scene.objects:
        obj = bpy.context.scene.objects[0]
        bpy.context.view_layer.objects.active = obj
    return obj


def _tick():
    packet = None
    try:
        while True:
            data, _ = _sock.recvfrom(65536)
            packet = json.loads(data)
    except (BlockingIOError, OSError, ValueError):
        pass
    if not packet:
        return 0.03
    hands = packet.get("hands", [])
    obj = _active()
    if obj is None:
        return 0.03
    pinching = [h for h in hands if h["gesture"] == "pinch"]
    _state["cool"] = max(0.0, _state["cool"] - 0.03)
    if len(pinching) == 2:  # two hands: scale by their spread
        a, b = pinching
        spread = ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
        if _state["spread"]:
            k = max(0.9, min(1.1, spread / _state["spread"]))
            obj.scale = [s * k for s in obj.scale]
        _state["spread"] = spread
        _state["last"] = None
    elif hands:
        h = hands[0]
        _state["spread"] = None
        here = (h["x"], h["y"])
        last = _state["last"]
        if last is not None:
            dx, dy = here[0] - last[0], here[1] - last[1]
            if h["gesture"] == "pinch":
                obj.rotation_euler[2] += dx * 6.0
                obj.rotation_euler[0] += dy * 6.0
            elif h["gesture"] == "fist":
                obj.location.x += dx * 8.0
                obj.location.z -= dy * 8.0
        _state["last"] = here
        if _state["cool"] == 0.0 and h["gesture"] == "thumbs_up":
            bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
            _state["cool"] = 1.5
        elif _state["cool"] == 0.0 and h["gesture"] == "victory":
            bpy.ops.object.duplicate_move()
            _state["cool"] = 1.5
    else:
        _state["last"] = _state["spread"] = None
    return 0.03


bpy.app.timers.register(_tick, persistent=True)
print("Sergio: control con las manos activo en el puerto", PORT)
""" % {"port": BLENDER_PORT}


__all__ = [
    "AirMouse",
    "BLENDER_BRIDGE",
    "Debounce",
    "Hand",
    "HandControl",
    "HandTracker",
    "MODES",
    "blender_packet",
    "ensure_model",
    "fingers_up",
    "gesture",
    "pinch_ratio",
]

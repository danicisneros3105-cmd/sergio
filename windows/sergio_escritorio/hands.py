"""Sergio sees your hands (webcam + MediaPipe) to shape holograms in Sergio ve.

Both hands are tracked and smoothed (One-Euro filter on every point) and
handed to the holograms (``holo.py``): pinch to grab, twist to turn, both
hands to scale, sculpt and draw in the air. There is no gesture or air-mouse
control of the computer any more: your hands are for the holograms.

The hand maths is pure (lists of 21 landmarks), so it is tested without a
camera; MediaPipe only turns frames into landmarks.
"""

from __future__ import annotations

import logging
import math
import os
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
MODES = {
    "off": "Apagado",
    "ver": "Ver tus manos (Vista)",
    "holo": "Hologramas con las manos",
}
# Older names for the hands (voice, Sergio's tools) -> today's mode.
ALIASES = {"3d": "holo", "fisica": "holo", "modelar": "holo", "hologramas": "holo"}
REMOVED = {"gestos", "mouse"}

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
        # Thumbs up only if the thumb points up (above the wrist on screen).
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
            # VIDEO: tracks the hand between frames — faster and steadier.
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._mp = mp
        self._last_ms = 0
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def detect(self, frame_bgr: Any) -> list[Hand]:
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        stamp = max(self._last_ms + 1, int(time.monotonic() * 1000))
        self._last_ms = stamp
        result = self._landmarker.detect_for_video(image, stamp)
        hands = []
        for i, marks in enumerate(result.hand_landmarks or []):
            side = ""
            if result.handedness and i < len(result.handedness):
                side = result.handedness[i][0].category_name
            hands.append(Hand([(m.x, m.y, m.z) for m in marks], side))
        return hands


# -- smoothing -----------------------------------------------------------------
class OneEuro:
    """One-Euro filter: steady when the hand is still, quick when it moves.

    (Casiez et al., the standard for jitter-free pointers.)
    """

    def __init__(
        self, min_cutoff: float = 1.2, beta: float = 0.02, d_cutoff: float = 1.0
    ):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self._x: float | None = None
        self._dx = 0.0
        self._t: float | None = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        if self._x is None or self._t is None or t <= self._t:
            self._x, self._t = x, t
            return x
        dt = t - self._t
        dx = (x - self._x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx = a_d * dx + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        a = self._alpha(cutoff, dt)
        self._x = a * x + (1 - a) * self._x
        self._t = t
        return self._x


class LandmarkSmoother:
    """One-Euro filter on all 21 points of each hand: no jitter, no lag."""

    def __init__(self, min_cutoff: float = 2.0, beta: float = 0.05) -> None:
        self.min_cutoff, self.beta = min_cutoff, beta
        self._filters: dict[str, list[tuple[OneEuro, OneEuro]]] = {}

    def __call__(self, hands: list[Hand], now: float) -> list[Hand]:
        out = []
        seen = set()
        for i, hand in enumerate(hands):
            key = hand.side or str(i)
            if key in seen:  # two hands reported with the same side
                key = f"{key}{i}"
            seen.add(key)
            filters = self._filters.get(key)
            if filters is None or len(filters) != len(hand.landmarks):
                filters = [
                    (OneEuro(self.min_cutoff, self.beta), OneEuro(self.min_cutoff, self.beta))
                    for _ in hand.landmarks
                ]
                self._filters[key] = filters
            points = [
                (fx(p[0], now), fy(p[1], now), p[2] if len(p) > 2 else 0.0)
                for p, (fx, fy) in zip(hand.landmarks, filters)
            ]
            out.append(Hand(points, hand.side))
        for key in list(self._filters):  # a hand left: forget its filters
            if key not in seen:
                del self._filters[key]
        return out


def main_hand(hands: list[Hand]) -> Hand | None:
    """The hand doing the work: the biggest (closest to the camera)."""
    if not hands:
        return None
    return max(hands, key=lambda h: palm_size(h.landmarks))


@dataclass
class HandControl:
    """Tracks your hands on the camera frames (own thread) for the holograms."""

    frames: Callable[[], Any]  # latest BGR frame or None
    tracker_factory: Callable[[], Any] = HandTracker
    mode: str = "off"
    hands: list[Hand] = field(default_factory=list)
    error: str = ""
    mirror: bool = True
    _thread: threading.Thread | None = None
    _smooth: LandmarkSmoother = field(default_factory=LandmarkSmoother)

    def set_mode(self, mode: str) -> None:
        mode = ALIASES.get(mode, mode)
        self.mode = mode if mode in MODES else "off"
        self.error = ""
        if self.mode != "off" and (self._thread is None or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def process(self, hands: list[Hand], now: float) -> None:
        """One frame: smooth the hands and keep them for the holograms."""
        self.hands = self._smooth(hands, now)

    def _loop(self) -> None:
        try:
            tracker = self.tracker_factory()
        except Exception as exc:  # noqa: BLE001 — no mediapipe / no model
            log.exception("hand tracking unavailable")
            self.error = f"No puedo ver tus manos: {exc}"
            self.mode = "off"
            return
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
            self.process(hands, time.monotonic())
            time.sleep(1 / 30)
        self.hands = []


__all__ = [
    "ALIASES",
    "MODES",
    "Hand",
    "HandControl",
    "HandTracker",
    "LandmarkSmoother",
    "OneEuro",
    "fingers_up",
    "gesture",
    "main_hand",
    "palm_size",
    "pinch_ratio",
]

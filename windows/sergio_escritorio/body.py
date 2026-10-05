"""More of you, measured: hands, face and body (Sergio ve).

* **Hands**: which hand, how many fingers, the gesture, where it points.
* **Face**: blinks per minute, eyes closing (tiredness, PERCLOS), where you
  look (screen, left, right, down), mouth open (talking), distance to the
  screen from the iris size (the iris is ~11.7 mm in every adult).
* **Body** (MediaPipe Pose, 33 points): posture (head forward / slouching),
  shoulders level, arms up, and squats counted (the gym's active break).

Pure maths on the landmark lists (tested without a camera); MediaPipe only
gives the points.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Sequence

log = logging.getLogger(__name__)

IRIS_MM = 11.7  # human iris diameter: nearly the same in all adults
FOCAL = 0.95  # webcam focal length as a fraction of the frame width (typical)
POSE_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)

# -- hands ------------------------------------------------------------------------
GESTURES_ES = {
    "open": "mano abierta",
    "fist": "puño",
    "point": "señala",
    "victory": "victoria",
    "thumbs_up": "pulgar arriba",
    "pinch": "pellizco",
    "none": "",
}


def hand_summary(landmarks: Sequence[Sequence[float]], side: str, mirror: bool = True) -> str:
    """'Derecha · 3 dedos · señala ↗' for one hand."""
    from sergio_escritorio.hands import fingers_up, gesture

    # MediaPipe names hands as if the image were a selfie (mirrored); the
    # webcam frames are not, so its "Left" is your right hand.
    who = {"Left": "Derecha", "Right": "Izquierda"}.get(side, "Mano")
    up = sum(fingers_up(landmarks))
    name = gesture(landmarks)
    parts = [who, f"{up} dedo{'s' if up != 1 else ''}"]
    if GESTURES_ES.get(name):
        parts.append(GESTURES_ES[name])
    if name == "point":
        dx = landmarks[8][0] - landmarks[5][0]
        dy = landmarks[8][1] - landmarks[5][1]
        if mirror:
            dx = -dx
        arrows = "→↘↓↙←↖↑↗"
        angle = math.degrees(math.atan2(dy, dx)) % 360
        parts[-1] += " " + arrows[int((angle + 22.5) // 45) % 8]
    return " · ".join(parts)


# -- face ------------------------------------------------------------------------------
def iris_distance_cm(points: Sequence[Sequence[float]], frame_width: int) -> float | None:
    """How far the face is from the camera, from the iris size."""
    if len(points) < 478 or frame_width <= 0:
        return None
    # Iris rings: 469-472 (one eye) and 474-477 (the other).
    sizes = []
    for a, b in ((469, 471), (474, 476)):
        dx = (points[a][0] - points[b][0]) * frame_width
        dy = (points[a][1] - points[b][1]) * frame_width
        sizes.append(math.hypot(dx, dy))
    iris_px = max(sizes)
    if iris_px < 2:
        return None
    return IRIS_MM * FOCAL * frame_width / iris_px / 10


def gaze(blend: dict[str, float]) -> str:
    """Where the eyes look, from the blendshapes."""
    g = blend.get
    right = (g("eyeLookOutRight", 0) + g("eyeLookInLeft", 0)) / 2
    left = (g("eyeLookOutLeft", 0) + g("eyeLookInRight", 0)) / 2
    down = (g("eyeLookDownLeft", 0) + g("eyeLookDownRight", 0)) / 2
    up = (g("eyeLookUpLeft", 0) + g("eyeLookUpRight", 0)) / 2
    best = max((right, "a un lado"), (left, "al otro lado"), (down, "abajo"), (up, "arriba"))
    return best[1] if best[0] > 0.45 else "a la pantalla"


@dataclass
class FaceStats:
    """Blinks and tiredness over the last minute."""

    window: float = 60.0
    closed_at: float | None = None
    blinks: deque = field(default_factory=deque)  # times of blinks
    samples: deque = field(default_factory=deque)  # (time, eyes closed?)
    last: dict[str, Any] = field(default_factory=dict)

    def feed(self, blend: dict[str, float], now: float, head_yaw: float = 0.0, head_pitch: float = 0.0) -> None:
        shut = (blend.get("eyeBlinkLeft", 0) + blend.get("eyeBlinkRight", 0)) / 2 > 0.55
        if shut and self.closed_at is None:
            self.closed_at = now
        elif not shut and self.closed_at is not None:
            if now - self.closed_at < 0.5:  # longer is not a blink, it is a doze
                self.blinks.append(now)
            self.closed_at = None
        self.samples.append((now, shut))
        while self.blinks and now - self.blinks[0] > self.window:
            self.blinks.popleft()
        while self.samples and now - self.samples[0][0] > self.window:
            self.samples.popleft()
        span = max(1.0, min(self.window, now - self.samples[0][0])) if self.samples else 1.0
        # PERCLOS: the share of TIME the eyes were closed (time-weighted).
        items = list(self.samples)
        closed = sum(b[0] - a[0] for a, b in zip(items, items[1:]) if a[1])
        total = (items[-1][0] - items[0][0]) if len(items) > 1 else 0.0
        perclos = closed / total if total > 0 else 0.0
        mouth = blend.get("jawOpen", 0)
        looking = gaze(blend)
        if abs(head_yaw) > 30:
            looking = "a otro lado (cabeza girada)"
        elif head_pitch < -25:
            looking = "abajo (cabeza)"
        self.last = {
            "blinks_per_min": round(len(self.blinks) * 60 / span),
            "perclos": round(perclos, 2),
            "tired": perclos > 0.25 or (self.closed_at is not None and now - self.closed_at > 1.5),
            "looking": looking,
            "talking": mouth > 0.25,
        }

    def summary(self) -> str:
        d = self.last
        if not d:
            return ""
        parts = [f"mira {d['looking']}", f"{d['blinks_per_min']} parpadeos/min"]
        if d["tired"]:
            parts.append("ojos cansados")
        if d["talking"]:
            parts.append("hablando")
        return " · ".join(parts)


# -- body -----------------------------------------------------------------------------------
NOSE, L_EAR, R_EAR, L_SH, R_SH = 0, 7, 8, 11, 12
L_WRIST, R_WRIST, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 15, 16, 23, 24, 25, 26, 27, 28


def _angle(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    """Angle ABC in degrees."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n = math.hypot(*v1) * math.hypot(*v2)
    if n == 0:
        return 180.0
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))
    return math.degrees(math.acos(cos))


def _visible(lm: Sequence[Sequence[float]], *idx: int) -> bool:
    return all(len(lm[i]) < 4 or lm[i][3] > 0.5 for i in idx)


@dataclass
class Posture:
    """Posture against your own upright baseline, and squats counted."""

    baseline: float | None = None  # nose height above shoulders / shoulder width
    squats: int = 0
    down: bool = False
    last: dict[str, Any] = field(default_factory=dict)

    def feed(self, lm: Sequence[Sequence[float]]) -> None:
        out: dict[str, Any] = {}
        if _visible(lm, NOSE, L_SH, R_SH):
            sw = math.dist(lm[L_SH][:2], lm[R_SH][:2])
            if sw > 0.02:
                mid_y = (lm[L_SH][1] + lm[R_SH][1]) / 2
                lift = (mid_y - lm[NOSE][1]) / sw  # head above the shoulders
                if self.baseline is None or lift > self.baseline:
                    # The best (most upright) seen becomes the reference,
                    # slowly forgotten so a new chair or camera re-learns it.
                    self.baseline = lift
                else:
                    self.baseline = 0.999 * self.baseline + 0.001 * lift
                out["slouch"] = lift < 0.78 * self.baseline
                tilt = math.degrees(math.atan2(lm[R_SH][1] - lm[L_SH][1], lm[R_SH][0] - lm[L_SH][0]))
                tilt = (tilt + 180) % 360 - 180
                tilt = tilt - 180 if tilt > 90 else (tilt + 180 if tilt < -90 else tilt)
                out["shoulders_tilt"] = round(tilt)
        if _visible(lm, L_WRIST, R_WRIST, NOSE):
            out["arms_up"] = lm[L_WRIST][1] < lm[NOSE][1] and lm[R_WRIST][1] < lm[NOSE][1]
        if _visible(lm, L_HIP, L_KNEE, L_ANKLE) or _visible(lm, R_HIP, R_KNEE, R_ANKLE):
            left = _angle(lm[L_HIP], lm[L_KNEE], lm[L_ANKLE])
            right = _angle(lm[R_HIP], lm[R_KNEE], lm[R_ANKLE])
            knee = min(left, right)
            out["knee_angle"] = round(knee)
            if knee < 110 and not self.down:
                self.down = True
            elif knee > 155 and self.down:
                self.down = False
                self.squats += 1
        out["squats"] = self.squats
        self.last = out

    def summary(self) -> str:
        d = self.last
        parts = []
        if "slouch" in d:
            parts.append("encorvado: endereza la espalda" if d["slouch"] else "postura recta")
        if abs(d.get("shoulders_tilt", 0)) >= 8:
            parts.append(f"hombros inclinados {abs(d['shoulders_tilt'])}°")
        if d.get("arms_up"):
            parts.append("brazos arriba")
        if self.squats:
            parts.append(f"{self.squats} sentadillas")
        return " · ".join(parts)


class PoseFinder:
    """Frame -> 33 body points (MediaPipe Pose Landmarker lite)."""

    def __init__(self) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        from sergio_escritorio.vision import MODEL_URLS, ensure_model

        MODEL_URLS.setdefault("pose_landmarker_lite.task", POSE_URL)
        self._mp = mp
        self._last = 0
        self._landmarker = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(ensure_model("pose_landmarker_lite.task"))),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
            )
        )

    def find(self, frame: Any) -> list[tuple[float, float, float, float]]:
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        stamp = max(self._last + 1, int(time.monotonic() * 1000))
        self._last = stamp
        result = self._landmarker.detect_for_video(image, stamp)
        if not result.pose_landmarks:
            return []
        return [(m.x, m.y, m.z, getattr(m, "visibility", 1.0) or 0.0) for m in result.pose_landmarks[0]]


# Skeleton lines to draw (MediaPipe Pose indices).
POSE_BONES = (
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24),
    (23, 24), (23, 25), (25, 27), (24, 26), (26, 28),
)  # fmt: skip

__all__ = [
    "FaceStats",
    "POSE_BONES",
    "PoseFinder",
    "Posture",
    "gaze",
    "hand_summary",
    "iris_distance_cm",
]

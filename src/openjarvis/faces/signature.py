"""A face's geometric signature: 175 measurements from 478 3D landmarks.

Sergio's identity check uses a deep embedding (SFace, 128 numbers learnt
from millions of faces). This adds what a forensic anthropologist would
measure: distances between the classic craniofacial points (Farkas) —
eye corners, pupils, nasion, nose tip and wings, lip points, cheekbones,
jaw angles, chin, brows, forehead — plus the standard indices (facial,
nasal, intercanthal, mouth/face, jaw/face...) and angles.

* 153 distances between 18 bony / stable points (every pair),
* 10 anthropometric indices, 12 angles = 175 patterns per face.

Everything is measured in 3D (MediaPipe's face mesh) and divided by the
distance between the pupils, so it does not change with distance to the
camera or head rotation. Bone proportions change little in adult life and
are partly inherited, which is why they help with old photos of adults and
with family resemblance. They are a hint, not a proof: for identity the
deep embedding decides; for kinship only DNA is proof.
"""

from __future__ import annotations

import math
from itertools import combinations
from pathlib import Path
from typing import Any, Sequence

# MediaPipe face mesh indices of the anthropometric points used.
POINTS: dict[str, int] = {
    "tr": 10,  # top of the forehead (trichion area)
    "g": 151,  # glabella area
    "n": 168,  # nasion: root of the nose between the eyes
    "en_d": 133,  # endocanthion: inner eye corner, right
    "en_i": 362,  # inner eye corner, left
    "ex_d": 33,  # exocanthion: outer eye corner, right
    "ex_i": 263,  # outer eye corner, left
    "p_d": 468,  # pupil (iris centre), right
    "p_i": 473,  # pupil, left
    "prn": 1,  # pronasale: nose tip
    "sn": 2,  # subnasale
    "al_d": 64,  # alare: nose wing, right
    "al_i": 294,  # nose wing, left
    "zy_d": 234,  # zygion: cheekbone width, right
    "zy_i": 454,  # cheekbone, left
    "go_d": 172,  # gonion: jaw angle, right
    "go_i": 397,  # jaw angle, left
    "gn": 152,  # gnathion: chin
    # Soft tissue that moves with expression (used in indices, not pairs):
    "ch_d": 61,  # mouth corner, right
    "ch_i": 291,  # mouth corner, left
    "ls": 0,  # upper lip
    "li": 17,  # lower lip
    "sto": 13,  # between the lips
    "sci_d": 105,  # eyebrow, right
    "sci_i": 334,  # eyebrow, left
    "ps_d": 159,  # upper eyelid, right
    "pi_d": 145,  # lower eyelid, right
}
STABLE = (
    "tr", "g", "n", "en_d", "en_i", "ex_d", "ex_i", "p_d", "p_i",
    "prn", "sn", "al_d", "al_i", "zy_d", "zy_i", "go_d", "go_i", "gn",
)  # fmt: skip
INDICES = (
    ("índice facial", ("n", "gn"), ("zy_d", "zy_i")),
    ("índice facial superior", ("n", "sto"), ("zy_d", "zy_i")),
    ("índice nasal", ("al_d", "al_i"), ("n", "sn")),
    ("índice intercantal", ("en_d", "en_i"), ("ex_d", "ex_i")),
    ("boca / cara", ("ch_d", "ch_i"), ("zy_d", "zy_i")),
    ("mandíbula / cara", ("go_d", "go_i"), ("zy_d", "zy_i")),
    ("filtrum / nariz", ("sn", "ls"), ("n", "sn")),
    ("mentón / cara", ("li", "gn"), ("n", "gn")),
    ("frente / cara", ("tr", "n"), ("n", "gn")),
    ("ceja / ojo", ("sci_d", "ps_d"), ("ex_d", "en_d")),
)
ANGLES = (
    ("n", "prn", "sn"),  # nose tip angle
    ("prn", "sn", "ls"),  # nasolabial
    ("go_d", "gn", "go_i"),  # chin / jaw opening
    ("zy_d", "n", "zy_i"),
    ("ex_d", "n", "ex_i"),
    ("al_d", "prn", "al_i"),
    ("en_d", "prn", "en_i"),
    ("zy_d", "gn", "zy_i"),
    ("tr", "n", "prn"),  # forehead-nose profile
    ("n", "sn", "gn"),
    ("go_d", "zy_d", "ex_d"),
    ("go_i", "zy_i", "ex_i"),
)
PAIRS = tuple(combinations(STABLE, 2))
SIZE = len(PAIRS) + len(INDICES) + len(ANGLES)  # 175
NAMES = (
    [f"{a}–{b}" for a, b in PAIRS]
    + [name for name, _num, _den in INDICES]
    + [f"ángulo {a}-{b}-{c}" for a, b, c in ANGLES]
)
# Which entries reflect bone (identity, kinship) rather than expression.
_BONY = (
    [True] * len(PAIRS)
    + [all(p in STABLE for p in (*num, *den)) for _n, num, den in INDICES]
    + [all(p in STABLE for p in tri) for tri in ANGLES]
)


def measure(points: dict[str, tuple[float, float, float]]) -> list[float]:
    """The 175 patterns from 3D points (any units: they are normalised)."""

    def dist(a: str, b: str) -> float:
        (x1, y1, z1), (x2, y2, z2) = points[a], points[b]
        return math.dist((x1, y1, z1), (x2, y2, z2))

    iod = dist("p_d", "p_i") or 1e-6  # interpupillary distance: the unit
    out = [math.log(max(dist(a, b), 1e-6) / iod) for a, b in PAIRS]
    out += [
        math.log(max(dist(*num), 1e-6) / max(dist(*den), 1e-6))
        for _n, num, den in INDICES
    ]
    for a, b, c in ANGLES:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points[a], points[b], points[c]
        u = (ax - bx, ay - by, az - bz)
        v = (cx - bx, cy - by, cz - bz)
        nu, nv = math.hypot(*u), math.hypot(*v)
        cos = sum(p * q for p, q in zip(u, v)) / max(nu * nv, 1e-9)
        out.append(math.acos(max(-1.0, min(1.0, cos))))
    return out


def from_points(payload: dict[str, Sequence[float]]) -> list[float] | None:
    """The companion's measured points ({"n": [x, y, z], ...}) -> signature."""
    try:
        pts = {k: tuple(float(v) for v in payload[k][:3]) for k in POINTS}
    except (KeyError, TypeError, ValueError):
        return None
    if any(len(v) != 3 for v in pts.values()):
        return None
    return measure(pts)  # type: ignore[arg-type]


def match_points(
    box: Sequence[float], faces: Sequence[dict[str, Any]]
) -> dict[str, Any] | None:
    """The companion's face (by box overlap) for a box the server found."""
    x, y, w, h = (float(v) for v in box)
    best, best_iou = None, 0.3
    for face in faces or []:
        try:
            fx, fy, fw, fh = (float(v) for v in face["box"])
        except (KeyError, TypeError, ValueError):
            continue
        ix = max(0.0, min(x + w, fx + fw) - max(x, fx))
        iy = max(0.0, min(y + h, fy + fh) - max(y, fy))
        inter = ix * iy
        union = w * h + fw * fh - inter
        overlap = inter / union if union > 0 else 0.0
        if overlap > best_iou:
            best, best_iou = face, overlap
    return best


def from_landmarks(landmarks: Any, width: int, height: int) -> list[float]:
    """MediaPipe landmarks (normalised x, y, z) -> the signature."""
    pts = {}
    for name, index in POINTS.items():
        lm = landmarks[index]
        pts[name] = (lm.x * width, lm.y * height, lm.z * width)
    return measure(pts)


def distance(a: list[float], b: list[float], bony_only: bool = True) -> float:
    """Root-mean-square difference of the patterns (0 = identical)."""
    pairs = [(x, y) for x, y, keep in zip(a, b, _BONY) if keep or not bony_only]
    if not pairs:
        return 1.0
    return math.sqrt(sum((x - y) ** 2 for x, y in pairs) / len(pairs))


def similarity(a: list[float], b: list[float]) -> float:
    """0..1 geometric likeness (1 = the same proportions)."""
    return max(0.0, 1.0 - distance(a, b) / GEO_SCALE)


# Calibrated on real faces: the same face under pose, light, blur and
# "old photo" changes stays below ~0.05; different adults spread 0.06-0.15.
GEO_SCALE = 0.16

LANDMARKER = (
    "face_landmarker.task",
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task",
)


class Measurer:
    """MediaPipe face mesh on the server (optional: without it, no geometry)."""

    def __init__(self, models_dir: Path) -> None:
        self.models_dir = Path(models_dir)
        self._mesh: Any = None
        self.error = ""

    def _load(self) -> Any:
        if self._mesh is None:
            import urllib.request

            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions, vision

            path = self.models_dir / LANDMARKER[0]
            if not path.exists():
                self.models_dir.mkdir(parents=True, exist_ok=True)
                part = path.with_suffix(".part")
                urllib.request.urlretrieve(LANDMARKER[1], part)  # noqa: S310 — fixed URL
                part.replace(path)
            options = vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(path)),
                num_faces=1,
                min_face_detection_confidence=0.3,
            )
            self._mesh = (mp, vision.FaceLandmarker.create_from_options(options))
        return self._mesh

    def signature(
        self, image_bgr: Any, box: tuple[int, int, int, int]
    ) -> list[float] | None:
        """The signature of the face in *box* (x, y, w, h), or None."""
        try:
            mp, mesh = self._load()
        except Exception as exc:  # noqa: BLE001 — geometry is a bonus
            self.error = str(exc)
            return None
        import cv2

        x, y, w, h = box
        pad = int(max(w, h) * 0.45)
        H, W = image_bgr.shape[:2]
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
        crop = image_bgr[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        side = max(crop.shape[:2])
        if side < 256:  # tiny faces: upscale so the mesh can find the points
            scale = 256 / side
            crop = cv2.resize(
                crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        found = mesh.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb.copy()))
        if not found.face_landmarks:
            return None
        h2, w2 = crop.shape[:2]
        return from_landmarks(found.face_landmarks[0], w2, h2)


__all__ = [
    "ANGLES",
    "GEO_SCALE",
    "INDICES",
    "Measurer",
    "NAMES",
    "PAIRS",
    "POINTS",
    "SIZE",
    "distance",
    "from_landmarks",
    "from_points",
    "match_points",
    "measure",
    "similarity",
]

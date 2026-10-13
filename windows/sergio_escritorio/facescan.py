"""Face ID-style face scan: turn your head in a circle, Sergio learns it.

While you turn your head slowly, a ring of 36 marks around your face lights
up in the direction you are looking (like setting up Face ID). Meanwhile:

* frames go to Sergio's server, which keeps the sharpest photo of each head
  angle (front, sides, up, down) for the face recogniser, and
* the 478 points of MediaPipe's face mesh, in 3D, are aligned frame by frame
  and averaged into a 3D map of the face in millimetres (the iris, ~11.7 mm
  across in every adult, gives the scale).

A webcam has no depth sensor, so this does not make Sergio a security lock
like Face ID's infrared dots; it makes him recognise you from any angle.
Pure logic (numpy) plus a few QPainter drawings.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

SECTORS = 36
MIN_TILT = 9.0  # degrees off the centre to light a mark
DONE_FRACTION = 0.72  # this much of the ring lit: done
MIN_SECONDS = 3.0
MAX_SECONDS = 16.0
IRIS_MM = 11.7  # adult iris diameter (very constant between people)
# MediaPipe iris points: 468 centre + 469..472 edge (right), 473 + 474..477 (left).
RIGHT_IRIS = (469, 470, 471, 472)
LEFT_IRIS = (474, 475, 476, 477)
# Points that move little with expressions (forehead, nose, cheekbones, jaw
# corners): the 3D alignment uses them so a smile does not tilt the map.
RIGID = (10, 151, 9, 8, 168, 6, 197, 195, 5, 4, 1, 2, 234, 454, 93, 323, 127, 356,
         33, 133, 362, 263, 172, 397, 152, 199)  # fmt: skip
MEASURES = {  # name -> (point a, point b): distances worth telling (mm)
    "entre pupilas": (468, 473),
    "ancho de la cara": (234, 454),
    "alto de la cara": (10, 152),
    "largo de la nariz": (168, 2),
    "ancho de la boca": (61, 291),
}


@dataclass
class ScanRing:
    """Which of the 36 directions your face has pointed at."""

    lit: list[bool] = field(default_factory=lambda: [False] * SECTORS)
    started: float = field(default_factory=time.monotonic)
    last: int | None = None

    def feed(self, yaw: float, pitch: float) -> int | None:
        """Head angles (degrees; yaw + = to your left on screen, pitch + =
        up) -> the mark it lit now (None if near the centre)."""
        if not math.isfinite(yaw) or not math.isfinite(pitch):
            return None
        if math.hypot(yaw, pitch) < MIN_TILT:
            self.last = None
            return None
        sector = int(((math.degrees(math.atan2(pitch, yaw)) + 360.0) % 360.0) / (360.0 / SECTORS))
        sector %= SECTORS
        self.lit[sector] = True
        if self.last is not None:
            # The head swept from the last mark to this one between two
            # frames: the marks in between were passed too (short arcs only).
            step = (sector - self.last) % SECTORS
            if step > SECTORS // 2:
                step -= SECTORS
            if 1 < abs(step) <= 5:
                direction = 1 if step > 0 else -1
                for k in range(1, abs(step)):
                    self.lit[(self.last + direction * k) % SECTORS] = True
        self.last = sector
        return sector

    @property
    def fraction(self) -> float:
        return sum(self.lit) / SECTORS

    def done(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        age = now - self.started
        if age < MIN_SECONDS:
            return False
        return self.fraction >= DONE_FRACTION or age >= MAX_SECONDS

    def angles(self) -> int:
        """How many of the eight compass directions were covered."""
        per = SECTORS // 8
        return sum(any(self.lit[i * per : (i + 1) * per]) for i in range(8))


def to_pixels(points3: Sequence[Sequence[float]], width: int, height: int) -> Any:
    """MediaPipe's normalised (x, y, z) -> pixels (z uses the x scale)."""
    import numpy as np

    p = np.asarray(points3, dtype=np.float64)
    return np.stack([p[:, 0] * width, p[:, 1] * height, p[:, 2] * width], axis=1)


def iris_pixels(px: Any) -> float:
    """Mean iris diameter in pixels (both eyes, both directions)."""
    import numpy as np

    sizes = []
    for a, b, c, d in (RIGHT_IRIS, LEFT_IRIS):
        sizes.append(np.linalg.norm(px[a, :2] - px[c, :2]))
        sizes.append(np.linalg.norm(px[b, :2] - px[d, :2]))
    return float(np.mean(sizes))


def _kabsch(moving: Any, fixed: Any) -> Any:
    """Rotation that best turns *moving* onto *fixed* (both centred)."""
    import numpy as np

    u, _s, vt = np.linalg.svd(moving.T @ fixed)
    d = np.sign(np.linalg.det(u @ vt))
    fix = np.diag([1.0, 1.0, d])
    return u @ fix @ vt


def canonical_mesh(samples: Sequence[tuple[Sequence[Sequence[float]], int, int]]) -> dict[str, Any] | None:
    """Frames of the face mesh (points, image width, height) -> one 3D map in
    millimetres: each frame scaled by its iris, turned onto the first front
    frame (rigid points only) and averaged."""
    import numpy as np

    shapes = []
    for points, width, height in samples:
        if len(points) < 478:
            continue
        px = to_pixels(points, width, height)
        iris = iris_pixels(px)
        if iris < 3.0:
            continue
        mm = px * (IRIS_MM / iris)
        mm[:, 1] *= -1.0  # y up
        mm[:, 2] *= -1.0  # z towards the camera
        shapes.append(mm - mm[list(RIGID)].mean(axis=0))
    if len(shapes) < 2:
        return None
    reference = shapes[0]
    aligned = []
    rigid = list(RIGID)
    for shape in shapes:
        rot = _kabsch(shape[rigid], reference[rigid])
        aligned.append(shape @ rot)
    mean = np.mean(aligned, axis=0)
    spread = float(np.mean(np.linalg.norm(np.asarray(aligned) - mean, axis=2)))
    points = [[round(float(v), 1) for v in row] for row in mean]
    return {
        "points": points,
        "unit": "mm",
        "frames": len(shapes),
        "spread_mm": round(spread, 2),
        "measures": measures(points),
    }


def measures(points: Sequence[Sequence[float]]) -> dict[str, float]:
    """A few distances of the 3D map, in millimetres."""
    out = {}
    for name, (a, b) in MEASURES.items():
        if max(a, b) < len(points):
            pa, pb = points[a], points[b]
            out[name] = round(math.dist(pa, pb), 1)
    return out


def measures_text(found: dict[str, float]) -> str:
    """'62 mm entre pupilas · cara 137 × 176 mm · nariz 50 mm' (approximate)."""
    parts = []
    if "entre pupilas" in found:
        parts.append(f"{found['entre pupilas']:.0f} mm entre pupilas")
    if "ancho de la cara" in found and "alto de la cara" in found:
        parts.append(f"cara {found['ancho de la cara']:.0f} × {found['alto de la cara']:.0f} mm")
    if "largo de la nariz" in found:
        parts.append(f"nariz {found['largo de la nariz']:.0f} mm")
    return " · ".join(parts)


class Scanner:
    """Runs one scan: watches the face mesh, fills the ring, keeps frames.

    *frame*: the latest camera frame (BGR numpy); *faces*: the latest face
    mesh results (vision.FaceInfo). ``run()`` blocks for up to MAX_SECONDS.
    """

    def __init__(
        self,
        frame: Any,
        faces: Any,
        *,
        every: float = 0.12,
        keep: int = 60,
        clock: Any = time.monotonic,
        sleep: Any = time.sleep,
    ) -> None:
        self.frame = frame
        self.faces = faces
        self.every = every
        self.keep = keep
        self.clock = clock
        self.sleep = sleep
        self.ring = ScanRing(started=clock())
        self.jpegs: list[bytes] = []
        self.samples: list[tuple[Any, int, int]] = []
        self.active = False
        self.box: tuple[float, float, float, float] | None = None  # the face, 0..1
        self.message = "Gire la cabeza despacio, en círculo"
        self.result: dict[str, Any] | None = None  # the 3D map when done
        self.finished_at = 0.0

    def run(self) -> tuple[list[bytes], dict[str, Any] | None]:
        import cv2

        self.active = True
        self.ring = ScanRing(started=self.clock())
        last_keep = -1e9
        try:
            while not self.ring.done(self.clock()):
                frame, faces = self.frame(), list(self.faces() or [])
                if frame is None:
                    self.message = "La cámara no responde"
                elif not faces:
                    self.message = "No veo su cara: póngase frente a la cámara"
                elif len(faces) > 1:
                    self.message = "Solo una persona frente a la cámara, por favor"
                else:
                    face = faces[0]
                    self.box = face.box
                    lit_before = sum(self.ring.lit)
                    self.ring.feed(face.yaw, face.pitch)
                    fresh = sum(self.ring.lit) > lit_before
                    self.message = (
                        "Siga girando despacio…" if self.ring.fraction < 0.5 else "Ya casi: complete el círculo"
                    )
                    now = self.clock()
                    if len(self.jpegs) < self.keep and (fresh or now - last_keep > 0.4):
                        h, w = frame.shape[:2]
                        scale = min(1.0, 640 / max(1, w))
                        small = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1 else frame
                        ok, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 90])
                        if ok:
                            self.jpegs.append(jpeg.tobytes())
                            last_keep = now
                    if getattr(face, "points3", None):
                        h, w = frame.shape[:2]
                        self.samples.append((face.points3, w, h))
                self.sleep(self.every)
        finally:
            self.active = False
        mesh = canonical_mesh(self.samples[::2] if len(self.samples) > 40 else self.samples)
        if self.ring.fraction < DONE_FRACTION:
            if self.message.startswith(("Siga girando", "Ya casi")):
                self.message = "Escaneo incompleto: vuelva a intentarlo con una sola cara bien iluminada."
            self.jpegs = []
            mesh = None
        self.result = mesh
        self.finished_at = self.clock()
        return self.jpegs, mesh


# -- drawing -------------------------------------------------------------------------
def draw_ring(p: Any, centre: Any, radius: float, ring: ScanRing, now: float, mirror: bool = True) -> None:
    """The Face ID ring: 36 marks, lit (green) where your face has pointed."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPen

    pulse = 0.5 + 0.5 * math.sin(now * 5.0)
    for i in range(SECTORS):
        angle = math.radians((i + 0.5) * 360.0 / SECTORS)
        dx, dy = math.cos(angle), -math.sin(angle)  # screen y grows down
        if mirror:
            dx = -dx
        inner = QPointF(centre.x() + dx * radius, centre.y() + dy * radius)
        length = 13.0 if ring.lit[i] else 8.0
        outer = QPointF(centre.x() + dx * (radius + length), centre.y() + dy * (radius + length))
        if ring.lit[i]:
            colour = QColor(48, 209, 88, 245)
        else:
            colour = QColor(255, 255, 255, int(70 + 60 * pulse))
        p.setPen(QPen(colour, 3.2))
        p.drawLine(inner, outer)


def draw_head(p: Any, rect: Any, points: Sequence[Sequence[float]], turn: float, edges: Sequence[tuple[int, int]] = ()) -> None:
    """The 3D map of the face, turning (a point cloud, nearer = brighter)."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPen

    if not points:
        return
    cos_t, sin_t = math.cos(turn), math.sin(turn)
    turned = [(x * cos_t + z * sin_t, y, -x * sin_t + z * cos_t) for x, y, z in points]
    xs = [pt[0] for pt in turned]
    ys = [pt[1] for pt in turned]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    scale = 0.9 * min(rect.width(), rect.height()) / span
    mid_x, mid_y = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    cx, cy = rect.center().x(), rect.center().y()
    projected = [
        (QPointF(cx + (x - mid_x) * scale, cy - (y - mid_y) * scale), z) for x, y, z in turned
    ]
    if edges:
        p.setPen(QPen(QColor(100, 210, 255, 50), 0.8))
        for a, b in edges:
            if a < len(projected) and b < len(projected):
                p.drawLine(projected[a][0], projected[b][0])
    depth = [z for _pt, z in projected]
    lo, hi = min(depth), max(depth)
    p.setPen(QPen(QColor(0, 0, 0, 0)))
    for spot, z in projected:
        k = (z - lo) / max(hi - lo, 1e-6)
        p.setBrush(QColor(int(80 + 120 * k), int(190 + 50 * k), 255, int(90 + 160 * k)))
        p.drawEllipse(spot, 1.3 + 0.9 * k, 1.3 + 0.9 * k)


def mesh_edges() -> list[tuple[int, int]]:
    """MediaPipe's face tessellation (2556 edges), if MediaPipe has it."""
    try:
        from mediapipe.tasks.python.vision import FaceLandmarksConnections

        return [(c.start, c.end) for c in FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION]
    except Exception:  # noqa: BLE001 — the point cloud alone still works
        return []


__all__ = [
    "DONE_FRACTION",
    "IRIS_MM",
    "ScanRing",
    "Scanner",
    "canonical_mesh",
    "draw_head",
    "draw_ring",
    "iris_pixels",
    "measures",
    "measures_text",
    "mesh_edges",
    "to_pixels",
]

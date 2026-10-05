"""Holograms you shape with your hands, Iron Man style (Sergio ve).

3D objects float in the camera view. With your bare hands:

* **Grab** — pinch (thumb + index) on a hologram: it follows your fingers,
  turns exactly as your wrist turns, and comes closer or goes away as you
  move your hand towards or away from the camera.
* **Throw / spin** — let go while moving and it keeps flying and spinning;
  sweep an open hand across one to spin it like a globe.
* **Two hands** — pinch with both: pull apart to scale, twist to rotate.
* **Sculpt** — in sculpt mode, pinch its surface and pull: the clay
  follows with a soft falloff.
* **Draw in the air** — in draw mode, pinch in empty space and draw: the
  stroke becomes a tube (a 3D pen), a turned vase (lathe) or an extruded
  shape.
* By voice: "crea un cubo / una esfera / un cilindro / un cono / un toroide /
  una pirámide / un jarrón / un diamante", colours, "más grande", "gíralo",
  "duplícalo", "bórralo", "suavízalo", "gravedad", "pásalo a Blender".

Everything here is numpy maths (tested without a camera). ``to_bpy`` turns
the scene into a Blender script that rebuilds it and saves the .blend.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

CAM_Z = 3.0  # the viewer sits here, looking down -z
HALF_W = 1.6  # half the view width at z = 0, in metres
FLOOR = -0.85
GRAVITY = 3.2
PINCH_ON, PINCH_OFF = 0.40, 0.55  # thumb-index distance / palm size (forgiving)
DEPTH_GAIN = 1.6

COLORS = {
    "cian": (0.30, 0.85, 1.00),
    "azul": (0.25, 0.50, 1.00),
    "rojo": (1.00, 0.30, 0.28),
    "verde": (0.30, 1.00, 0.55),
    "amarillo": (1.00, 0.86, 0.30),
    "naranja": (1.00, 0.62, 0.25),
    "morado": (0.70, 0.45, 1.00),
    "rosa": (1.00, 0.50, 0.80),
    "blanco": (0.92, 0.95, 1.00),
    "dorado": (1.00, 0.80, 0.35),
    "plateado": (0.80, 0.84, 0.90),
    "negro": (0.25, 0.27, 0.32),
}
HOLO = COLORS["cian"]
SHAPE_WORDS = {
    "cubo": "cubo", "caja": "cubo", "cuadrado": "cubo",
    "esfera": "esfera", "bola": "esfera", "pelota": "esfera", "planeta": "esfera",
    "cilindro": "cilindro", "tubo": "cilindro", "lata": "cilindro",
    "cono": "cono",
    "toroide": "toroide", "dona": "toroide", "anillo": "toroide", "rosquilla": "toroide",
    "piramide": "piramide",
    "jarron": "jarron", "florero": "jarron", "vaso": "jarron", "copa": "jarron",
    "diamante": "diamante", "gema": "diamante", "cristal": "diamante",
}  # fmt: skip
NUMBERS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
           "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}  # fmt: skip


# -- meshes --------------------------------------------------------------------
@dataclass
class Mesh:
    vertices: np.ndarray  # (n, 3) local coordinates, metres
    faces: list[tuple[int, ...]]  # vertex indices, counter-clockwise outside
    smooth: bool = False  # shade smooth in Blender

    def copy(self) -> Mesh:
        return Mesh(self.vertices.copy(), list(self.faces), self.smooth)

    def size(self) -> float:
        span = self.vertices.max(axis=0) - self.vertices.min(axis=0)
        return float(span.max()) if len(self.vertices) else 0.0


def cube(size: float = 0.5) -> Mesh:
    h = size / 2
    v = np.array([[x, y, z] for x in (-h, h) for y in (-h, h) for z in (-h, h)], float)
    faces = [
        (0, 1, 3, 2),
        (4, 6, 7, 5),
        (0, 4, 5, 1),
        (2, 3, 7, 6),
        (0, 2, 6, 4),
        (1, 5, 7, 3),
    ]
    return Mesh(v, faces)


def revolve(
    profile: Sequence[tuple[float, float]], segments: int = 20, cap: bool = True
) -> Mesh:
    """Turn a (radius, height) profile around the vertical axis (a lathe)."""
    rings = []
    verts: list[list[float]] = []
    for r, y in profile:
        ring = []
        for k in range(segments):
            a = 2 * math.pi * k / segments
            ring.append(len(verts))
            verts.append([max(r, 0.0) * math.cos(a), y, max(r, 0.0) * math.sin(a)])
        rings.append(ring)
    faces: list[tuple[int, ...]] = []
    for lo, hi in zip(rings, rings[1:]):
        for k in range(segments):
            k2 = (k + 1) % segments
            faces.append((lo[k], hi[k], hi[k2], lo[k2]))
    if cap and profile[0][0] > 1e-6:
        faces.append(tuple(rings[0]))
    if cap and profile[-1][0] > 1e-6:
        faces.append(tuple(reversed(rings[-1])))
    return Mesh(np.array(verts, float), faces, smooth=True)


def sphere(radius: float = 0.3, rings: int = 12, segments: int = 18) -> Mesh:
    profile = [
        (
            radius * math.sin(math.pi * i / rings),
            -radius * math.cos(math.pi * i / rings),
        )
        for i in range(rings + 1)
    ]
    return revolve(profile, segments, cap=False)


def cylinder(radius: float = 0.22, height: float = 0.55, segments: int = 20) -> Mesh:
    mesh = revolve([(radius, -height / 2), (radius, height / 2)], segments)
    mesh.smooth = False
    return mesh


def cone(radius: float = 0.28, height: float = 0.55, segments: int = 20) -> Mesh:
    mesh = revolve([(radius, -height / 2), (0.0, height / 2)], segments)
    mesh.smooth = False
    return mesh


def torus(
    major: float = 0.28, minor: float = 0.1, rings: int = 18, segments: int = 12
) -> Mesh:
    verts, faces = [], []
    for i in range(rings):
        a = 2 * math.pi * i / rings
        for j in range(segments):
            b = 2 * math.pi * j / segments
            r = major + minor * math.cos(b)
            verts.append([r * math.cos(a), minor * math.sin(b), r * math.sin(a)])
    for i in range(rings):
        for j in range(segments):
            i2, j2 = (i + 1) % rings, (j + 1) % segments
            faces.append(
                (
                    i * segments + j,
                    i * segments + j2,
                    i2 * segments + j2,
                    i2 * segments + j,
                )
            )
    return Mesh(np.array(verts, float), faces, smooth=True)


def pyramid(size: float = 0.55) -> Mesh:
    h = size / 2
    v = np.array([[-h, -h, -h], [h, -h, -h], [h, -h, h], [-h, -h, h], [0, h, 0]], float)
    faces = [(0, 1, 2, 3), (0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0)]
    return Mesh(v, faces)


def vase(height: float = 0.6) -> Mesh:
    shape = [
        (0.12, 0),
        (0.2, 0.12),
        (0.24, 0.3),
        (0.18, 0.55),
        (0.1, 0.72),
        (0.12, 0.85),
        (0.16, 1.0),
    ]
    return revolve([(r * height, (y - 0.5) * height) for r, y in shape], 24)


def diamond(size: float = 0.5) -> Mesh:
    mesh = revolve(
        [
            (0.0, -0.5 * size),
            (0.5 * size, 0.12 * size),
            (0.32 * size, 0.3 * size),
            (0.0, 0.3 * size),
        ],
        10,
    )
    mesh.smooth = False
    return mesh


def tube(
    path: Sequence[Sequence[float]], radius: float = 0.035, segments: int = 8
) -> Mesh:
    """A tube along a drawn 3D path (the 3D pen)."""
    pts = np.asarray(path, float)
    if len(pts) < 2:
        raise ValueError("A stroke needs at least two points.")
    verts, faces = [], []
    up = np.array([0.0, 0.0, 1.0])
    for i, p in enumerate(pts):
        t = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
        t = t / (np.linalg.norm(t) + 1e-9)
        if abs(float(np.dot(t, up))) > 0.95:
            up = np.array([1.0, 0.0, 0.0])
        n = np.cross(t, up)
        n /= np.linalg.norm(n) + 1e-9
        b = np.cross(t, n)
        for k in range(segments):
            a = 2 * math.pi * k / segments
            verts.append(p + radius * (math.cos(a) * n + math.sin(a) * b))
    for i in range(len(pts) - 1):
        for k in range(segments):
            k2 = (k + 1) % segments
            a, b2 = i * segments, (i + 1) * segments
            faces.append((a + k, a + k2, b2 + k2, b2 + k))
    faces.append(tuple(range(segments - 1, -1, -1)))
    last = (len(pts) - 1) * segments
    faces.append(tuple(last + k for k in range(segments)))
    return Mesh(np.array(verts, float), faces, smooth=True)


def lathe_from_stroke(path: Sequence[Sequence[float]]) -> Mesh:
    """A drawn outline (one side of a vase) turned into a solid of revolution."""
    pts = np.asarray(path, float)
    axis_x = float(pts[:, 0].min())
    profile = sorted(
        ((float(abs(x - axis_x)), float(y)) for x, y, _z in pts), key=lambda p: p[1]
    )
    keep = [profile[0]]
    for r, y in profile[1:]:
        if y - keep[-1][1] > 0.01:
            keep.append((r, y))
    if len(keep) < 2:
        raise ValueError("Draw the outline from bottom to top.")
    cy = (keep[0][1] + keep[-1][1]) / 2
    return revolve([(r, y - cy) for r, y in keep], 24)


def extrude_stroke(path: Sequence[Sequence[float]], depth: float = 0.2) -> Mesh:
    """A drawn closed shape pushed into a solid (like a cookie cutter)."""
    pts = np.asarray(path, float)[:, :2]
    centre = pts.mean(axis=0)
    pts = pts - centre
    n = len(pts)
    if n < 3:
        raise ValueError("Draw a closed shape.")
    area = 0.5 * float(
        np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])
    )
    if area < 0:
        pts = pts[::-1]
    front = [[x, y, depth / 2] for x, y in pts]
    back = [[x, y, -depth / 2] for x, y in pts]
    faces: list[tuple[int, ...]] = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, n + i, n + j, j))
    return Mesh(np.array(front + back, float), faces)


MAKERS = {
    "cubo": cube,
    "esfera": sphere,
    "cilindro": cylinder,
    "cono": cone,
    "toroide": torus,
    "piramide": pyramid,
    "jarron": vase,
    "diamante": diamond,
}
NAMES_ES = {"cubo": "Cubo", "esfera": "Esfera", "cilindro": "Cilindro", "cono": "Cono",
            "toroide": "Toroide", "piramide": "Pirámide", "jarron": "Jarrón",
            "diamante": "Diamante", "tubo": "Trazo", "torno": "Torneado",
            "extrusion": "Extrusión"}  # fmt: skip


# -- rotations -------------------------------------------------------------------
def rot_axis(axis: Sequence[float], angle: float) -> np.ndarray:
    a = np.asarray(axis, float)
    a = a / (np.linalg.norm(a) + 1e-12)
    x, y, z = a
    c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    return np.array(
        [
            [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
        ]
    )


def orthonormal(m: np.ndarray) -> np.ndarray:
    u, _s, vt = np.linalg.svd(m)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return r


def axis_angle(r: np.ndarray) -> tuple[np.ndarray, float]:
    angle = math.acos(max(-1.0, min(1.0, (np.trace(r) - 1) / 2)))
    if angle < 1e-6:
        return np.array([0.0, 1.0, 0.0]), 0.0
    axis = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])
    return axis / (np.linalg.norm(axis) + 1e-12), angle


# -- objects and projection ----------------------------------------------------------
@dataclass
class Holo:
    id: int
    kind: str
    mesh: Mesh
    pos: np.ndarray = field(default_factory=lambda: np.zeros(3))
    rot: np.ndarray = field(default_factory=lambda: np.eye(3))
    scale: float = 1.0
    color: tuple[float, float, float] = HOLO
    vel: np.ndarray = field(default_factory=lambda: np.zeros(3))
    spin: np.ndarray = field(default_factory=lambda: np.zeros(3))  # axis * rad/s
    held: bool = False

    @property
    def name(self) -> str:
        return f"{NAMES_ES.get(self.kind, self.kind.title())} {self.id}"

    def world(self) -> np.ndarray:
        return (self.mesh.vertices * self.scale) @ self.rot.T + self.pos

    def radius(self) -> float:
        return float(np.linalg.norm(self.mesh.vertices, axis=1).max()) * self.scale

    def size_cm(self) -> int:
        return round(self.mesh.size() * self.scale * 100)


def project(
    points: np.ndarray, width: float, height: float
) -> tuple[np.ndarray, np.ndarray]:
    """World points -> view pixels (and their distance from the viewer)."""
    depth = np.maximum(CAM_Z - points[:, 2], 0.05)
    k = CAM_Z / depth * (width / 2) / HALF_W
    sx = width / 2 + points[:, 0] * k
    sy = height / 2 - points[:, 1] * k
    return np.stack([sx, sy], axis=1), depth


def unproject(u: float, v: float, z: float, width: float, height: float) -> np.ndarray:
    """View pixel (u, v) at world depth z -> world point."""
    k = CAM_Z / max(CAM_Z - z, 0.05) * (width / 2) / HALF_W
    return np.array([(u - width / 2) / k, (height / 2 - v) / k, z])


# -- hands ---------------------------------------------------------------------------
def hand_points(
    landmarks: Sequence[Sequence[float]],
    width: float,
    height: float,
    mirror: bool,
    frame_box: tuple[float, float, float, float] | None = None,
) -> np.ndarray:
    """21 MediaPipe landmarks -> view pixels + depth (x right, y down, z towards you).

    *frame_box* (left, top, width, height): where the camera picture is drawn
    in the view (it may be cropped to fill it); default: the whole view.
    """
    left, top, fw, fh = frame_box or (0.0, 0.0, width, height)
    pts = np.asarray(landmarks, float)[:, :3]
    x = (1 - pts[:, 0]) if mirror else pts[:, 0]
    # Landmark z is relative depth in units of the frame width (negative =
    # closer); flip it so +z points at the viewer like the world.
    return np.stack([left + x * fw, top + pts[:, 1] * fh, -pts[:, 2] * fw], axis=1)


def palm(points: np.ndarray) -> float:
    return float(np.linalg.norm(points[9, :2] - points[0, :2])) or 1.0


def pinch_amount(points: np.ndarray) -> float:
    return float(np.linalg.norm(points[4, :2] - points[8, :2])) / palm(points)


def hand_frame(points: np.ndarray) -> np.ndarray:
    """The hand's orientation as a rotation matrix (world axes, y up)."""
    p = points * np.array([1.0, -1.0, 1.0])  # y up
    a = p[9] - p[0]  # wrist -> middle knuckle
    b = p[17] - p[5]  # across the knuckles
    n = np.cross(b, a)
    a /= np.linalg.norm(a) + 1e-9
    n /= np.linalg.norm(n) + 1e-9
    c = np.cross(a, n)
    return orthonormal(np.stack([c, a, n], axis=1))


def open_palm(points: np.ndarray) -> bool:
    tips, pips = (8, 12, 16, 20), (6, 10, 14, 18)
    up = sum(
        np.linalg.norm(points[t, :2] - points[0, :2])
        > np.linalg.norm(points[p, :2] - points[0, :2]) * 1.1
        for t, p in zip(tips, pips)
    )
    return up >= 4 and pinch_amount(points) > PINCH_OFF


@dataclass
class Grip:
    """One hand holding something."""

    target: int  # object id (or -1 drawing, -2 empty pinch)
    start: np.ndarray  # pinch point in view pixels
    palm0: float
    hand0: np.ndarray
    rot0: np.ndarray
    pos0: np.ndarray
    scale0: float = 1.0
    vertex: int = -1  # sculpting: the vertex pulled
    verts0: np.ndarray | None = None
    trail: list[tuple[float, np.ndarray, np.ndarray]] = field(default_factory=list)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


class HoloScene:
    """The holograms in Sergio ve and how your hands move them."""

    MODES = ("mover", "esculpir", "dibujar")
    PEN = ("tubo", "torno", "extrusion")

    def __init__(self) -> None:
        self.objects: list[Holo] = []
        self.mode = "mover"
        self.pen = "tubo"
        self.gravity = False
        self.brush = 0.12  # sculpt radius, metres
        self.view = (480.0, 270.0)
        self.grips: dict[int, Grip] = {}  # hand index -> grip
        self.pinching: dict[int, bool] = {}
        self.stroke: list[np.ndarray] = []
        self.stroke_hand = -1
        self.last_hands: list[np.ndarray] = []
        self.selected = -1
        self._next = 1
        self._prev_palm_x: dict[int, tuple[float, float]] = {}

    # -- objects ------------------------------------------------------------------
    def add(self, kind: str, mesh: Mesh | None = None, color: tuple[float, float, float] | None = None,
            pos: Sequence[float] | None = None) -> Holo:  # fmt: skip
        if mesh is None:
            mesh = MAKERS[kind]()
        if pos is None:
            n = len(self.objects)
            pos = (((n % 5) - 2) * 0.55, 0.1 + 0.15 * ((n // 5) % 2), -0.2)
        obj = Holo(self._next, kind, mesh, np.array(pos, float), rot_axis((1, 1, 0), 0.45),
                   color=color or HOLO)  # fmt: skip
        obj.spin = np.array([0.0, 0.35, 0.0])  # a slow showroom turn
        self._next += 1
        self.objects.append(obj)
        self.selected = obj.id
        return obj

    def get(self, oid: int) -> Holo | None:
        return next((o for o in self.objects if o.id == oid), None)

    def current(self) -> Holo | None:
        return self.get(self.selected) or (self.objects[-1] if self.objects else None)

    def pick(self, u: float, v: float) -> Holo | None:
        """The hologram under the view pixel (u, v), nearest first."""
        w, h = self.view
        best, best_d = None, 1e9
        for obj in self.objects:
            ((cx, cy),) = project(obj.pos[None], w, h)[0]
            k = CAM_Z / max(CAM_Z - obj.pos[2], 0.05) * (w / 2) / HALF_W
            reach = max(obj.radius() * k * 1.8, 40.0)
            d = math.hypot(u - cx, v - cy)
            if d < reach and CAM_Z - obj.pos[2] < best_d:
                best, best_d = obj, CAM_Z - obj.pos[2]
        if best is None and self.objects:
            # Magnetic grab: a pinch near (not exactly on) a hologram takes it.
            def gap(obj: Holo) -> float:
                ((cx, cy),) = project(obj.pos[None], w, h)[0]
                return math.hypot(u - cx, v - cy)

            near = min(self.objects, key=gap)
            if gap(near) < max(w, h) * 0.22:
                best = near
        return best

    def nudge(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        """Move the current hologram (voice and mouse)."""
        obj = self.current()
        if obj is not None:
            obj.pos = obj.pos + np.array([dx, dy, dz])
            obj.vel = np.zeros(3)

    def turn(self, yaw: float = 0.0, pitch: float = 0.0) -> None:
        """Turn the current hologram by degrees (voice and mouse)."""
        obj = self.current()
        if obj is None:
            return
        a, b = math.radians(yaw), math.radians(pitch)
        ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
        rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
        obj.rot = orthonormal(ry @ rx @ obj.rot)
        obj.spin = np.zeros(3)

    # -- voice ----------------------------------------------------------------------
    def command(self, order: str) -> str:
        t = _plain(order)
        colour, said_colour = None, ""
        for c in COLORS:
            found = re.search(
                rf"\b{c[:-1] if c[-1] in 'oa' else c}(o|a|os|as|es|s)?\b", t
            )
            if found:
                colour, said_colour = c, found.group(0)
                break
        obj = self.current()
        if re.search(
            r"\b(borra|quita|elimina)\b.*\b(todo|todos|todas|hologramas|objetos)\b", t
        ):
            self.objects.clear()
            return "Hologramas borrados."
        if re.search(r"\b(borra|borralo|borrala|quita|elimina)", t) and obj is not None:
            self.objects.remove(obj)
            return f"Borré {obj.name}."
        if re.search(r"\b(esculp|modela)", t):
            self.mode = "esculpir"
            return "Modo esculpir: pellizca la superficie y tira para darle forma."
        if re.search(r"\b(dibuj|traza|pinta en el aire)", t):
            self.mode = "dibujar"
            if "torno" in t or "jarron" in t or "revol" in t:
                self.pen = "torno"
            elif "extru" in t or "silueta" in t:
                self.pen = "extrusion"
            else:
                self.pen = "tubo"
            return {
                "tubo": "Modo dibujar: pellizca y dibuja en el aire; al soltar se vuelve un tubo 3D.",
                "torno": "Dibuja el perfil de un lado, de abajo arriba: lo giro como en un torno.",
                "extrusion": "Dibuja una silueta cerrada: la convierto en un sólido.",
            }[self.pen]
        if re.search(r"\b(mover|modo normal|agarrar|manipular)\b", t):
            self.mode = "mover"
            return "Modo mover: pellizca un holograma para agarrarlo."
        if "gravedad" in t or "fisica" in t:
            self.gravity = not re.search(r"\b(sin|quita|apaga|cero)\b", t)
            return (
                "Gravedad activada: caen, rebotan y se lanzan."
                if self.gravity
                else "Sin gravedad: flotan."
            )
        if re.search(r"\b(suaviz|alisa|pule)", t) and obj is not None:
            smooth(obj.mesh, 2)
            obj.mesh.smooth = True
            return f"Suavicé {obj.name}."
        if re.search(r"\b(duplic|copia|clona)", t) and obj is not None:
            twin = self.add(
                obj.kind,
                obj.mesh.copy(),
                obj.color,
                obj.pos + np.array([0.4, 0.0, 0.0]),
            )
            twin.rot, twin.scale = obj.rot.copy(), obj.scale
            return f"Dupliqué {obj.name}."
        if re.search(r"\b(mas grande|agranda|aumenta|crece)\b", t) and obj is not None:
            obj.scale *= 1.3
            return f"{obj.name} más grande ({obj.size_cm()} cm)."
        if re.search(r"\b(mas pequen|achica|reduce|encoge)", t) and obj is not None:
            obj.scale /= 1.3
            return f"{obj.name} más pequeño ({obj.size_cm()} cm)."
        step = 0.35
        moves = (
            (r"\b(izquierda)\b", (-step, 0, 0), "a la izquierda"),
            (r"\b(derecha)\b", (step, 0, 0), "a la derecha"),
            (r"\b(arriba|sube|subelo)\b", (0, step, 0), "arriba"),
            (r"\b(abajo|baja|bajalo)\b", (0, -step, 0), "abajo"),
            (r"\b(acercalo|acerca|hacia mi|mas cerca)\b", (0, 0, step * 1.5), "más cerca"),
            (r"\b(alejalo|aleja|mas lejos)\b", (0, 0, -step * 1.5), "más lejos"),
        )
        if obj is not None and re.search(r"\b(muev|mueve|ponlo|llevalo|lleva|desplaza|acerca|aleja|sube|baja|subelo|bajalo)", t):
            for pattern, (dx, dy, dz), said in moves:
                if re.search(pattern, t):
                    self.nudge(dx, dy, dz)
                    return f"{obj.name} {said}."
        m = re.search(r"\b(gira|giralo|rota|rotalo|voltea|voltealo)\b.*?(\d+)\s*grados", t)
        if m and obj is not None:
            deg = float(m.group(2))
            pitch = "arriba" in t or "abajo" in t or "adelante" in t
            self.turn(0 if pitch else (-deg if "izquierda" in t else deg), deg if pitch else 0)
            return f"Giré {obj.name} {int(deg)} grados."
        if re.search(r"\b(voltea|voltealo|dale la vuelta)\b", t) and obj is not None:
            self.turn(180)
            return f"Volteé {obj.name}."
        if re.search(r"\b(gira|rota|da vueltas)", t) and obj is not None:
            obj.spin = np.array([0.0, 2.5, 0.0])
            return f"Girando {obj.name}."
        if re.search(r"\b(centra|centralo|al centro|traelo)\b", t) and obj is not None:
            obj.pos = np.array([0.0, 0.1, 0.0])
            obj.vel = np.zeros(3)
            return f"{obj.name} al centro."
        m = re.search(r"\b(selecciona|elige|agarra|toma)\b.*\b(\d+)\b", t)
        if m and self.get(int(m.group(2))) is not None:
            self.selected = int(m.group(2))
            return f"Seleccioné {self.get(self.selected).name}."
        if re.search(r"\b(para|deten|quieto|frena)\b", t):
            for o in self.objects:
                o.spin = np.zeros(3)
                o.vel = np.zeros(3)
            return "Quietos."
        shape = next((SHAPE_WORDS[w] for w in t.split() if w in SHAPE_WORDS), None)
        if shape is None:
            shape = next(
                (v for k, v in SHAPE_WORDS.items() if re.search(rf"\b{k}e?s\b", t)),
                None,
            )
        if shape is not None:
            count = 1
            m = re.search(r"\b(\d+|" + "|".join(NUMBERS) + r")\b", t)
            if m:
                count = int(m.group(1)) if m.group(1).isdigit() else NUMBERS[m.group(1)]
            count = max(1, min(count, 12))
            for _ in range(count):
                self.add(shape, color=COLORS.get(colour) if colour else None)
            what = NAMES_ES[shape].lower()
            return (
                f"Creé {count} {what}{'s' if count > 1 else ''}"
                + (f" {said_colour}" if colour else "")
                + "."
            )
        if colour and obj is not None:
            obj.color = COLORS[colour]
            return f"{obj.name} ahora es {colour}."
        return "No entendí qué hacer con los hologramas."

    # -- hands ------------------------------------------------------------------------
    def update_hands(
        self,
        hands: Sequence[Any],
        dt: float,
        mirror: bool,
        now: float,
        frame_box: tuple[float, float, float, float] | None = None,
    ) -> None:
        """One camera frame of hands (MediaPipe landmarks) -> grab, sculpt, draw."""
        w, h = self.view
        pts = [
            hand_points(getattr(x, "landmarks", x), w, h, mirror, frame_box)
            for x in hands[:2]
        ]
        self.last_hands = pts
        for i in range(2):
            if i >= len(pts):
                self._release(i, now)
                self.pinching[i] = False
                continue
            p = pts[i]
            amount = pinch_amount(p)
            was = self.pinching.get(i, False)
            on = amount < (PINCH_OFF if was else PINCH_ON)
            self.pinching[i] = on
            point = (p[4] + p[8]) / 2
            if on and not was:
                self._grab(i, p, point, now)
            elif on:
                self._drag(i, p, point, now)
            elif was:
                self._release(i, now)
            elif open_palm(p):
                self._sweep(i, p, now)
        self._two_hands(pts)

    def _grab(self, i: int, p: np.ndarray, point: np.ndarray, now: float) -> None:
        obj = self.pick(point[0], point[1])
        frame = hand_frame(p)
        if obj is None:
            if self.mode == "dibujar":
                self.stroke = []
                self.stroke_hand = i
                self.grips[i] = Grip(
                    -1, point.copy(), palm(p), frame, np.eye(3), np.zeros(3)
                )
                self._draw_point(i, p, point)
            else:
                self.grips[i] = Grip(
                    -2, point.copy(), palm(p), frame, np.eye(3), np.zeros(3)
                )
            return
        obj.held, obj.vel, obj.spin = True, np.zeros(3), np.zeros(3)
        self.selected = obj.id
        grip = Grip(
            obj.id,
            point.copy(),
            palm(p),
            frame,
            obj.rot.copy(),
            obj.pos.copy(),
            obj.scale,
        )
        if self.mode == "esculpir":
            grip.vertex = self._nearest_vertex(obj, point)
            grip.verts0 = obj.mesh.vertices.copy()
        self.grips[i] = grip

    def _target_point(
        self, grip: Grip, p: np.ndarray, point: np.ndarray, z0: float
    ) -> np.ndarray:
        w, h = self.view
        z = z0 + DEPTH_GAIN * math.log(palm(p) / grip.palm0) * 0.5
        z = min(1.6, max(-2.5, z))
        return unproject(point[0], point[1], z, w, h)

    def _drag(self, i: int, p: np.ndarray, point: np.ndarray, now: float) -> None:
        grip = self.grips.get(i)
        if grip is None:
            return
        if grip.target == -1:
            self._draw_point(i, p, point)
            return
        obj = self.get(grip.target)
        if obj is None:
            return
        other = [g for k, g in self.grips.items() if k != i and g.target == obj.id]
        if other:
            return  # two hands on it: _two_hands drives it
        w, h = self.view
        start = unproject(grip.start[0], grip.start[1], grip.pos0[2], w, h)
        now_pt = self._target_point(grip, p, point, grip.pos0[2])
        if self.mode == "esculpir" and grip.verts0 is not None and grip.vertex >= 0:
            delta_world = now_pt - start
            local = (delta_world @ obj.rot) / max(obj.scale, 1e-6)
            centre = grip.verts0[grip.vertex]
            d = np.linalg.norm(grip.verts0 - centre, axis=1)
            weight = np.exp(-((d / (self.brush / max(obj.scale, 1e-6))) ** 2))
            obj.mesh.vertices = grip.verts0 + weight[:, None] * local[None, :]
            obj.mesh.smooth = True
            return
        obj.pos = grip.pos0 + (now_pt - start)
        turn = hand_frame(p) @ grip.hand0.T
        obj.rot = orthonormal(turn @ grip.rot0)
        grip.trail.append((now, obj.pos.copy(), obj.rot.copy()))
        grip.trail = [t for t in grip.trail if now - t[0] < 0.15]

    def _release(self, i: int, now: float) -> None:
        grip = self.grips.pop(i, None)
        if grip is None:
            return
        if grip.target == -1:
            self._finish_stroke()
            return
        obj = self.get(grip.target)
        if obj is None:
            return
        obj.held = any(g.target == obj.id for g in self.grips.values())
        if len(grip.trail) >= 2 and self.mode == "mover":
            (t0, p0, r0), (t1, p1, r1) = grip.trail[0], grip.trail[-1]
            span = max(t1 - t0, 1e-3)
            obj.vel = (p1 - p0) / span
            axis, angle = axis_angle(r1 @ r0.T)
            obj.spin = axis * angle / span

    def _sweep(self, i: int, p: np.ndarray, now: float) -> None:
        """An open hand brushing past a hologram spins it."""
        cx = float(p[9, 0])
        last = self._prev_palm_x.get(i)
        self._prev_palm_x[i] = (now, cx)
        if last is None or now - last[0] > 0.2:
            return
        speed = (cx - last[1]) / max(now - last[0], 1e-3)  # pixels / s
        if abs(speed) < 250:
            return
        obj = self.pick(float(p[9, 0]), float(p[9, 1]))
        if obj is not None and not obj.held:
            obj.spin = np.array([0.0, speed / 180.0, 0.0])

    def _two_hands(self, pts: list[np.ndarray]) -> None:
        if len(pts) < 2 or not (self.pinching.get(0) and self.pinching.get(1)):
            return
        g0, g1 = self.grips.get(0), self.grips.get(1)
        if g0 is None or g1 is None:
            return
        target = g0.target if g0.target >= 0 else g1.target
        obj = self.get(target)
        if obj is None:
            return
        a0, a1 = (pts[0][4] + pts[0][8]) / 2, (pts[1][4] + pts[1][8]) / 2
        d0 = float(np.linalg.norm(g0.start[:2] - g1.start[:2])) or 1.0
        d1 = float(np.linalg.norm(a0[:2] - a1[:2]))
        base = g0 if g0.target == target else g1
        obj.scale = min(8.0, max(0.1, base.scale0 * d1 / d0))
        ang0 = math.atan2(g1.start[1] - g0.start[1], g1.start[0] - g0.start[0])
        ang1 = math.atan2(a1[1] - a0[1], a1[0] - a0[0])
        obj.rot = orthonormal(rot_axis((0, 0, 1), -(ang1 - ang0)) @ base.rot0)

    def _draw_point(self, i: int, p: np.ndarray, point: np.ndarray) -> None:
        grip = self.grips[i]
        world = self._target_point(grip, p, point, 0.0)
        if not self.stroke or np.linalg.norm(world - self.stroke[-1]) > 0.015:
            self.stroke.append(world)

    def _finish_stroke(self) -> None:
        stroke, self.stroke = self.stroke, []
        if len(stroke) < 5:
            return
        pts = np.array(stroke)
        centre = pts.mean(axis=0)
        try:
            if self.pen == "torno":
                mesh, kind = lathe_from_stroke(pts), "torno"
            elif self.pen == "extrusion":
                mesh, kind = extrude_stroke(pts), "extrusion"
            else:
                mesh, kind = tube(pts - centre), "tubo"
        except ValueError:
            return
        obj = self.add(
            kind, mesh, pos=centre if kind == "tubo" else (centre[0], centre[1], -0.2)
        )
        obj.rot = np.eye(3)
        obj.spin = np.zeros(3)

    def _nearest_vertex(self, obj: Holo, point: np.ndarray) -> int:
        w, h = self.view
        screen, depth = project(obj.world(), w, h)
        d = np.linalg.norm(screen - point[:2], axis=1) + depth * 2.0  # front first
        return int(np.argmin(d))

    # -- time ---------------------------------------------------------------------------
    def step(self, dt: float) -> None:
        dt = min(dt, 0.05)
        for obj in self.objects:
            if obj.held:
                continue
            if np.any(obj.spin):
                axis = obj.spin
                obj.rot = orthonormal(
                    rot_axis(axis, float(np.linalg.norm(axis)) * dt) @ obj.rot
                )
                obj.spin = (
                    obj.spin * math.exp(-0.25 * dt)
                    if np.linalg.norm(obj.spin) > 0.36
                    else obj.spin
                )
            if self.gravity:
                obj.vel[1] -= GRAVITY * dt
            obj.pos = obj.pos + obj.vel * dt
            obj.vel = obj.vel * math.exp(-(0.4 if self.gravity else 1.6) * dt)
            r = obj.radius()
            if self.gravity and obj.pos[1] - r < FLOOR:
                obj.pos[1] = FLOOR + r
                obj.vel[1] = -obj.vel[1] * 0.45
                obj.vel[0] *= 0.85
            reach = HALF_W * (CAM_Z - obj.pos[2]) / CAM_Z
            for axis, lim in ((0, reach - r), (1, reach * 0.6 - r)):
                if abs(obj.pos[axis]) > lim > 0:
                    obj.pos[axis] = math.copysign(lim, obj.pos[axis])
                    obj.vel[axis] = -obj.vel[axis] * 0.5

    # -- drawing data ----------------------------------------------------------------------
    def render(self, width: float, height: float) -> list[dict]:
        """Faces to paint, far to near: points (view px), shade 0..1, colour."""
        self.view = (width, height)
        light = np.array([-0.4, 0.7, 0.6])
        light /= np.linalg.norm(light)
        out = []
        for obj in self.objects:
            world = obj.world()
            screen, depth = project(world, width, height)
            for face in obj.mesh.faces:
                idx = list(face)
                a, b, c = world[idx[0]], world[idx[1]], world[idx[2]]
                n = np.cross(b - a, c - a)
                norm = float(np.linalg.norm(n))
                if norm < 1e-12:
                    continue
                n /= norm
                centre = world[idx].mean(axis=0)
                view_dir = np.array([0.0, 0.0, CAM_Z]) - centre
                facing = float(np.dot(n, view_dir))
                shade = 0.35 + 0.65 * max(0.0, float(np.dot(n, light)))
                out.append(
                    {
                        "id": obj.id,
                        "points": screen[idx],
                        "depth": float(depth[idx].mean()),
                        "shade": shade,
                        "front": facing > 0,
                        "color": obj.color,
                        "held": obj.held or obj.id == self.selected,
                    }
                )
        out.sort(key=lambda f: -f["depth"])
        return out

    def stroke_points(self, width: float, height: float) -> np.ndarray:
        if not self.stroke:
            return np.zeros((0, 2))
        return project(np.array(self.stroke), width, height)[0]

    # -- Blender ----------------------------------------------------------------------------
    def describe(self) -> str:
        if not self.objects:
            return "No hay hologramas."
        parts = [f"{o.name} ({o.size_cm()} cm)" for o in self.objects]
        return (
            f"{len(parts)} holograma{'s' if len(parts) > 1 else ''}: "
            + ", ".join(parts)
            + "."
        )


def smooth(mesh: Mesh, rounds: int = 1, amount: float = 0.5) -> None:
    """Laplacian smoothing: every vertex moves towards its neighbours."""
    n = len(mesh.vertices)
    neighbours: list[set[int]] = [set() for _ in range(n)]
    for face in mesh.faces:
        for k, a in enumerate(face):
            neighbours[a].add(face[k - 1])
            neighbours[a].add(face[(k + 1) % len(face)])
    v = mesh.vertices
    for _ in range(rounds):
        avg = np.array(
            [
                v[list(nb)].mean(axis=0) if nb else v[i]
                for i, nb in enumerate(neighbours)
            ]
        )
        v = v + amount * (avg - v)
    mesh.vertices = v


def to_obj(objects: Sequence[Holo]) -> str:
    """Wavefront OBJ of the scene (world positions baked in, y up)."""
    lines = ["# Sergio: hologramas"]
    base = 1
    for obj in objects:
        lines.append(f"o {obj.name.replace(' ', '_')}")
        for x, y, z in obj.world():
            lines.append(f"v {x:.5f} {y:.5f} {z:.5f}")
        for face in obj.mesh.faces:
            lines.append("f " + " ".join(str(base + i) for i in face))
        base += len(obj.mesh.vertices)
    return "\n".join(lines) + "\n"


def to_bpy(objects: Sequence[Holo], save_path: str) -> str:
    """A Blender script that rebuilds the holograms and saves the .blend.

    Blender's z is up: (x, y, z) here -> (x, -z, y) there.
    """
    data = []
    for obj in objects:
        verts = [
            [round(float(x), 5), round(float(-z), 5), round(float(y), 5)]
            for x, y, z in obj.world()
        ]
        data.append(
            {
                "name": obj.name,
                "verts": verts,
                "faces": [list(f) for f in obj.mesh.faces],
                "color": [round(c, 3) for c in obj.color],
                "smooth": obj.mesh.smooth,
            }
        )
    import json

    payload = json.dumps(data)
    return f'''import bpy, json
from mathutils import Vector

DATA = json.loads(r"""{payload}""")
SAVE = r"""{save_path}"""

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
made = []
for item in DATA:
    mesh = bpy.data.meshes.new(item["name"])
    mesh.from_pydata([Vector(v) for v in item["verts"]], [], [tuple(f) for f in item["faces"]])
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(item["name"], mesh)
    scene.collection.objects.link(obj)
    mat = bpy.data.materials.new(item["name"] + " material")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*item["color"], 1.0)
        bsdf.inputs["Roughness"].default_value = 0.35
    mesh.materials.append(mat)
    if item["smooth"]:
        for poly in mesh.polygons:
            poly.use_smooth = True
        mod = obj.modifiers.new("Suave", "SUBSURF")
        mod.levels = 1
        mod.render_levels = 2
    obj.location = mesh.vertices[0].co * 0  # geometry already placed
    made.append(obj)
# Origin of each object at its centre, so it turns around itself in Blender.
for obj in made:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
light = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", "SUN"))
light.data.energy = 3.0
light.rotation_euler = (0.8, 0.2, 0.6)
scene.collection.objects.link(light)
cam = bpy.data.objects.new("Cámara", bpy.data.cameras.new("Cámara"))
cam.location = (0.0, -4.5, 1.2)
cam.rotation_euler = (1.35, 0.0, 0.0)
scene.collection.objects.link(cam)
scene.camera = cam
import os
os.makedirs(os.path.dirname(SAVE), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=SAVE)
print("SERGIO_SAVED", SAVE, len(made))
'''


__all__ = [
    "COLORS",
    "Holo",
    "HoloScene",
    "MAKERS",
    "Mesh",
    "cone",
    "cube",
    "cylinder",
    "diamond",
    "extrude_stroke",
    "hand_frame",
    "hand_points",
    "lathe_from_stroke",
    "pinch_amount",
    "project",
    "pyramid",
    "revolve",
    "rot_axis",
    "smooth",
    "sphere",
    "to_bpy",
    "to_obj",
    "torus",
    "tube",
    "unproject",
    "vase",
]

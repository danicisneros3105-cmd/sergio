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
  una pirámide / un jarrón / un diamante / una estrella / un corazón / un
  prisma / un icosaedro / una cápsula / un disco / una flecha / una luna",
  colours, "más grande", "gíralo", "duplícalo", "bórralo", "suavízalo",
  "gravedad", "estilo cristal" / "estilo holograma", "pásalo a Blender".
  Anything else ("un teléfono", "una silla") is designed part by part.

They look like frosted glass by default (the camera behind them blurred,
iridescent edges); "estilo holograma" brings back the JARVIS blue light.
Grabbing is forgiving: whatever your fingers are over glows before you
pinch, a pinch that flickers for a frame does not drop it, and the wrist
must turn a few degrees before the object turns (no jitter).

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
OPEN_HAND = 0.80  # fingers clearly apart: let go at once
GRACE = 0.15  # s a half-open pinch or a lost hand keeps holding
TURN_DEADZONE = math.radians(4)  # wrist jitter below this does not turn it
DEPTH_GAIN = 1.6
STYLES = ("cristal", "holograma")

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
    "diamante": "diamante", "gema": "diamante",
    "estrella": "estrella", "corazon": "corazon",
    "prisma": "prisma", "hexagono": "prisma",
    "icosaedro": "icosaedro", "dado20": "icosaedro", "poliedro": "icosaedro",
    "capsula": "capsula", "pastilla": "capsula",
    "disco": "disco", "moneda": "disco",
    "flecha": "flecha",
    "luna": "luna", "medialuna": "luna",
}  # fmt: skip
NUMBERS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
           "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}  # fmt: skip


# -- meshes --------------------------------------------------------------------
@dataclass
class Mesh:
    vertices: np.ndarray  # (n, 3) local coordinates, metres
    faces: list[tuple[int, ...]]  # vertex indices, counter-clockwise outside
    smooth: bool = False  # shade smooth in Blender
    colors: list[tuple[float, float, float]] | None = None  # per face (models)

    def copy(self) -> Mesh:
        return Mesh(self.vertices.copy(), list(self.faces), self.smooth,
                    list(self.colors) if self.colors else None)

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


def extrude_outline(
    outline: Sequence[tuple[float, float]],
    depth: float = 0.16,
    bevel: float = 0.25,
    centre: tuple[float, float] = (0.0, 0.0),
) -> Mesh:
    """A flat outline made solid with chamfered edges (they catch the light).

    The caps are fans around *centre*, so the outline only has to be visible
    from it (a star, a heart, an arrow), not convex. *bevel* is how far the
    caps shrink toward *centre* (0 = square edges).
    """
    pts = np.asarray(outline, float)
    c = np.asarray(centre, float)
    area = 0.5 * float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1]))
    if area < 0:
        pts = pts[::-1]
    n = len(pts)
    inset = c + (pts - c) * (1 - bevel)
    b = depth * 0.3 if bevel else 0.0
    layers = [(inset, depth / 2), (pts, depth / 2 - b), (pts, -depth / 2 + b), (inset, -depth / 2)]
    verts = [[x, y, z] for ring, z in layers for x, y in ring]
    faces: list[tuple[int, ...]] = []
    for k in range(len(layers) - 1):
        a0, a1 = k * n, (k + 1) * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((a0 + j, a0 + i, a1 + i, a1 + j))
    front = len(verts)
    verts.append([c[0], c[1], depth / 2])
    back = len(verts)
    verts.append([c[0], c[1], -depth / 2])
    last = (len(layers) - 1) * n
    for i in range(n):
        j = (i + 1) % n
        faces.append((front, i, j))
        faces.append((back, last + j, last + i))
    return Mesh(np.array(verts, float), faces)


def _outward(mesh: Mesh) -> Mesh:
    """Flip any face whose normal points to the centre (convex solids only)."""
    v = mesh.vertices
    centre = (v.max(axis=0) + v.min(axis=0)) / 2
    fixed = []
    for face in mesh.faces:
        a, b, c = v[face[0]], v[face[1]], v[face[2]]
        normal = np.cross(b - a, c - a)
        mid = v[list(face)].mean(axis=0)
        fixed.append(tuple(reversed(face)) if float(np.dot(normal, mid - centre)) < 0 else face)
    mesh.faces = fixed
    return mesh


def star(points: int = 5, outer: float = 0.32, inner: float = 0.14, depth: float = 0.14) -> Mesh:
    outline = [
        ((outer if k % 2 == 0 else inner) * math.cos(math.pi / 2 + math.pi * k / points),
         (outer if k % 2 == 0 else inner) * math.sin(math.pi / 2 + math.pi * k / points))
        for k in range(2 * points)
    ]  # fmt: skip
    return extrude_outline(outline, depth, 0.18)


def heart(size: float = 0.55, depth: float = 0.16) -> Mesh:
    outline = []
    for k in range(48):
        t = 2 * math.pi * k / 48
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        outline.append((x * size / 34, (y + 2.5) * size / 34))
    mesh = extrude_outline(outline, depth, 0.16)
    mesh.smooth = True
    return mesh


def arrow(length: float = 0.6, depth: float = 0.12) -> Mesh:
    h = length / 2
    outline = [(-h, -0.06), (0.1, -0.06), (0.1, -0.16), (h, 0.0), (0.1, 0.16), (0.1, 0.06), (-h, 0.06)]
    return extrude_outline(outline, depth, 0.12, centre=(0.08, 0.0))


def crescent(radius: float = 0.3, depth: float = 0.14, steps: int = 20) -> Mesh:
    """A crescent moon: a strip between two arcs, chamfered."""
    a0, a1 = math.radians(-125), math.radians(125)
    outer = [(radius * math.cos(a0 + (a1 - a0) * i / steps), radius * math.sin(a0 + (a1 - a0) * i / steps))
             for i in range(steps + 1)]  # fmt: skip
    tip0, tip1 = np.array(outer[0]), np.array(outer[-1])
    # inner arc: the bite, a circle shifted left through both tips whose
    # right edge stays inside the outer one
    shift = -0.475 * radius
    centre = np.array([shift, 0.0])
    r2 = float(np.linalg.norm(tip0 - centre))
    b0 = math.atan2(tip0[1], tip0[0] - shift)
    b1 = math.atan2(tip1[1], tip1[0] - shift)
    if b1 < b0:
        b1 += 2 * math.pi
    inner = [(shift + r2 * math.cos(b0 + (b1 - b0) * i / steps), r2 * math.sin(b0 + (b1 - b0) * i / steps))
             for i in range(steps + 1)]  # fmt: skip
    verts, faces = [], []
    for z in (depth / 2, -depth / 2):
        for (ox, oy), (ix, iy) in zip(outer, inner):
            verts.append([ox, oy, z])
            verts.append([ix, iy, z])
    m = 2 * (steps + 1)
    for i in range(steps):
        o0, i0, o1, i1 = 2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3
        faces.append((o0, o1, i1, i0))  # front
        faces.append((m + o0, m + i0, m + i1, m + o1))  # back
        faces.append((o0, m + o0, m + o1, o1))  # outer rim
        faces.append((i0, i1, m + i1, m + i0))  # inner rim
    mesh = Mesh(np.array(verts, float), faces)
    mesh.vertices[:, 0] -= (mesh.vertices[:, 0].max() + mesh.vertices[:, 0].min()) / 2
    return mesh


def prism(radius: float = 0.26, height: float = 0.5, sides: int = 6) -> Mesh:
    mesh = revolve([(radius, -height / 2), (radius, height / 2)], sides)
    mesh.smooth = False
    return mesh


def icosahedron(radius: float = 0.3) -> Mesh:
    g = (1 + math.sqrt(5)) / 2
    v = np.array([[-1, g, 0], [1, g, 0], [-1, -g, 0], [1, -g, 0],
                  [0, -1, g], [0, 1, g], [0, -1, -g], [0, 1, -g],
                  [g, 0, -1], [g, 0, 1], [-g, 0, -1], [-g, 0, 1]], float)  # fmt: skip
    v = v / np.linalg.norm(v[0]) * radius
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
             (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
             (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]  # fmt: skip
    return _outward(Mesh(v, faces))


def capsule(radius: float = 0.14, height: float = 0.56, steps: int = 6) -> Mesh:
    half = height / 2 - radius
    profile = [(radius * math.sin(math.pi / 2 * i / steps), -half - radius * math.cos(math.pi / 2 * i / steps))
               for i in range(steps + 1)]  # fmt: skip
    profile += [(radius * math.cos(math.pi / 2 * i / steps), half + radius * math.sin(math.pi / 2 * i / steps))
                for i in range(steps + 1)]  # fmt: skip
    return revolve(profile, 20, cap=False)


def disc(radius: float = 0.3, thick: float = 0.06) -> Mesh:
    mesh = revolve([(radius * 0.9, -thick / 2), (radius, -thick / 4), (radius, thick / 4), (radius * 0.9, thick / 2)], 32)
    mesh.smooth = True
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


# -- models of anything: parts designed by Gemini --------------------------------------
def superellipsoid(power: float = 0.25, rings: int = 8, segments: int = 16) -> Mesh:
    """A unit sphere pushed toward a box: power 1 = sphere, 0.2 = rounded box."""
    mesh = sphere(1.0, rings, segments)
    v = mesh.vertices
    mesh.vertices = np.sign(v) * np.abs(v) ** power
    return mesh


def wedge() -> Mesh:
    v = np.array([[-0.5, -0.5, -0.5], [0.5, -0.5, -0.5], [0.5, -0.5, 0.5], [-0.5, -0.5, 0.5],
                  [-0.5, 0.5, -0.5], [0.5, 0.5, -0.5]], float)  # fmt: skip
    faces = [(0, 3, 2, 1), (0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5)]
    return Mesh(v, faces)


def part_mesh(shape: str, size: Sequence[float], part: dict | None = None) -> Mesh:
    """One designed part, *size* in metres (see openjarvis.tools.holo_model).

    Free-form parts carry their own points: a "lathe" profile (cups, bottles,
    lampshades), an "extrude" outline (a phone body, a logo) or a "tube" path
    (handles, cables) — so round and curved things are no longer boxes."""
    part = part or {}
    try:
        if shape == "lathe" and part.get("profile"):
            return revolve([(float(r), float(y)) for r, y in part["profile"]], 32, cap=True)
        if shape == "extrude" and part.get("outline"):
            pts = np.asarray(part["outline"], float)
            depth = max(float(size[2]) if len(size) > 2 else 0.01, 1e-4)
            return extrude_outline(pts, depth, bevel=0.0, centre=tuple(pts.mean(axis=0)))
        if shape == "tube" and part.get("path"):
            return tube(part["path"], float(part.get("radius") or 0.005), 12)
    except (ValueError, IndexError, TypeError):
        pass  # bad points: the plain solid below
    w, h, d = (max(float(x), 1e-4) for x in size)
    if shape == "torus":
        outer, thick = max(w, d), min(h, max(w, d) / 2)
        mesh = torus((outer - thick) / 2, thick / 2, 16, 8)
        mesh.vertices = mesh.vertices * np.array([w / outer, 1.0, d / outer])
        return mesh
    unit = {
        "box": lambda: cube(1.0),
        "rounded_box": lambda: superellipsoid(0.22, 8, 16),
        "cylinder": lambda: cylinder(0.5, 1.0, 16),
        "cone": lambda: cone(0.5, 1.0, 16),
        "sphere": lambda: sphere(0.5, 8, 12),
        "capsule": lambda: superellipsoid(0.6, 8, 12),
        "wedge": wedge,
    }.get(shape, lambda: cube(1.0))()
    if shape in ("rounded_box", "capsule"):
        unit.vertices = unit.vertices * 0.5
    unit.vertices = unit.vertices * np.array([w, h, d])
    return unit


def euler(degrees: Sequence[float]) -> np.ndarray:
    """Rotation of x, then y, then z degrees."""
    ax, ay, az = (math.radians(float(a)) for a in degrees)
    rx = np.array([[1, 0, 0], [0, math.cos(ax), -math.sin(ax)], [0, math.sin(ax), math.cos(ax)]])
    ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
    rz = np.array([[math.cos(az), -math.sin(az), 0], [math.sin(az), math.cos(az), 0], [0, 0, 1]])
    return rz @ ry @ rx


def assemble(recipe: dict, fit: float = 1.0) -> tuple[Mesh, float]:
    """All the parts in one mesh (a colour per face), centred and scaled so
    the biggest side is *fit* metres on screen. Returns (mesh, base)."""
    verts: list[np.ndarray] = []
    faces: list[tuple[int, ...]] = []
    colors: list[tuple[float, float, float]] = []
    count = 0
    for part in recipe.get("parts") or []:
        mesh = part_mesh(str(part.get("shape")), part.get("size") or (0.05, 0.05, 0.05), part)
        world = mesh.vertices @ euler(part.get("rot") or (0, 0, 0)).T + np.array(part.get("pos") or (0, 0, 0), float)
        verts.append(world)
        colour = tuple(float(c) for c in (part.get("color") or (0.6, 0.6, 0.6))[:3])
        for face in mesh.faces:
            faces.append(tuple(count + i for i in face))
            colors.append(colour)  # type: ignore[arg-type]
        count += len(world)
    if not verts:
        raise ValueError("el modelo no tiene piezas")
    v = np.vstack(verts)
    v = v - (v.max(axis=0) + v.min(axis=0)) / 2
    real = float((v.max(axis=0) - v.min(axis=0)).max()) or 1.0
    base = fit / real
    return Mesh(v * base, faces, smooth=False, colors=colors), base


MAKERS = {
    "cubo": cube,
    "esfera": sphere,
    "cilindro": cylinder,
    "cono": cone,
    "toroide": torus,
    "piramide": pyramid,
    "jarron": vase,
    "diamante": diamond,
    "estrella": star,
    "corazon": heart,
    "prisma": prism,
    "icosaedro": icosahedron,
    "capsula": capsule,
    "disco": disc,
    "flecha": arrow,
    "luna": crescent,
}
NAMES_ES = {"cubo": "Cubo", "esfera": "Esfera", "cilindro": "Cilindro", "cono": "Cono",
            "toroide": "Toroide", "piramide": "Pirámide", "jarron": "Jarrón",
            "diamante": "Diamante", "tubo": "Trazo", "torno": "Torneado",
            "extrusion": "Extrusión", "estrella": "Estrella", "corazon": "Corazón",
            "prisma": "Prisma", "icosaedro": "Icosaedro", "capsula": "Cápsula",
            "disco": "Disco", "flecha": "Flecha", "luna": "Luna"}  # fmt: skip
PLURALS_ES = {"corazon": "corazones", "capsula": "cápsulas", "piramide": "pirámides",
              "jarron": "jarrones", "toroide": "toroides"}  # fmt: skip


# -- rotations -------------------------------------------------------------------
def spring(x: float, v: float, target: float, dt: float, response: float = 0.4, damping: float = 0.72) -> tuple[float, float]:
    """One step of a damped spring (period *response* s, damping ratio)."""
    omega = 2 * math.pi / response
    for _ in range(2):  # two half steps: stable at 20 fps too
        h = dt / 2
        v += (-omega * omega * (x - target) - 2 * damping * omega * v) * h
        x += v * h
    if abs(x - target) < 1e-4 and abs(v) < 1e-4:
        return target, 0.0
    return x, v


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
    base: float = 1.0  # display size / real size (a 15 cm phone is shown bigger)
    recipe: dict | None = None  # the designed parts (for Blender Pro)
    # Apple-style motion (springs, only for the look; Blender gets the real size):
    lift: float = 0.0  # 0 resting .. 1 held: it rises toward you, a little bigger
    lift_v: float = 0.0
    appear: float = 1.0  # 0 just created .. 1: it pops in with a soft overshoot
    appear_v: float = 0.0
    hover_k: float = 0.0  # the hover glow fades in and out instead of popping

    def display(self) -> float:
        """How much bigger it looks right now (lift and pop-in)."""
        return (1.0 + 0.06 * self.lift) * (0.55 + 0.45 * self.appear)

    @property
    def name(self) -> str:
        return f"{NAMES_ES.get(self.kind, self.kind[:1].upper() + self.kind[1:])} {self.id}"

    def world(self, display: bool = False) -> np.ndarray:
        scale = self.scale * (self.display() if display else 1.0)
        return (self.mesh.vertices * scale) @ self.rot.T + self.pos

    def radius(self) -> float:
        return float(np.linalg.norm(self.mesh.vertices, axis=1).max()) * self.scale

    def size_cm(self) -> int:
        """Real size: a model keeps its real centimetres however big it is shown."""
        return round(self.mesh.size() * self.scale / self.base * 100)


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
    turning: bool = False  # the wrist passed the dead zone
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
        self.style = "cristal"
        self.hover: dict[int, int] = {}  # hand -> the hologram a pinch would take
        self._next = 1
        self._prev_palm_x: dict[int, tuple[float, float]] = {}
        self._off_since: dict[int, float] = {}  # hand -> when the pinch let go

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
        obj.appear = 0.0  # pops in
        self._next += 1
        self.objects.append(obj)
        self.selected = obj.id
        return obj

    def add_model(self, recipe: dict) -> Holo:
        """A designed object (a phone, a chair...) as one hologram."""
        mesh, base = assemble(recipe)
        obj = self.add(str(recipe.get("name") or "modelo").lower(), mesh, (0.8, 0.8, 0.8), (0.0, 0.1, 0.0))
        obj.base, obj.recipe = base, recipe
        obj.rot = rot_axis((1, 0, 0), 0.25) @ rot_axis((0, 1, 0), -0.5)
        obj.spin = np.array([0.0, 0.3, 0.0])
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
        if re.search(r"\b(cristal|vidrio|glass|apple)\b", t) and not re.search(r"\b(crea|haz|pon)\b.*\b(de|en) (cristal|vidrio)\b", t):
            self.style = "cristal"
            return "Estilo cristal: vidrio esmerilado con reflejos de arcoíris."
        if re.search(r"\b(estilo|aspecto|modo) (de )?(holograma|jarvis|azul|iron man)\b", t):
            self.style = "holograma"
            return "Estilo holograma: luz azul, estilo JARVIS."
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
            if count > 1:
                what = PLURALS_ES.get(shape, what + "s")
            return (
                f"Creé {count} {what}"
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
                self.hover.pop(i, None)
                # A hand lost for a frame or two keeps what it holds.
                if self.pinching.get(i) and self._held_on(i, now):
                    continue
                self._release(i, now)
                self.pinching[i] = False
                self._off_since.pop(i, None)
                continue
            p = pts[i]
            amount = pinch_amount(p)
            was = self.pinching.get(i, False)
            on = amount < (PINCH_OFF if was else PINCH_ON)
            point = (p[4] + p[8]) / 2
            if was and not on and amount < OPEN_HAND and self._held_on(i, now):
                on = True  # half open for an instant: still holding
            elif on:
                self._off_since.pop(i, None)
            self.pinching[i] = on
            if on and not was:
                self._grab(i, p, point, now)
            elif on:
                self._drag(i, p, point, now)
            elif was:
                self._release(i, now)
                self._off_since.pop(i, None)
            elif open_palm(p):
                self._sweep(i, p, now)
            if on:
                self.hover.pop(i, None)
            else:
                near = self.pick(point[0], point[1]) if self.mode != "dibujar" else None
                if near is None:
                    self.hover.pop(i, None)
                else:
                    self.hover[i] = near.id
        self._two_hands(pts)

    def _held_on(self, i: int, now: float) -> bool:
        """Still within the grace time after the pinch (or the hand) went away."""
        since = self._off_since.setdefault(i, now)
        return now - since < GRACE

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
        if axis_angle(turn)[1] >= TURN_DEADZONE or grip.turning:
            grip.turning = True  # past the dead zone: follows the wrist exactly
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
        hovered = set(self.hover.values())
        for obj in self.objects:
            # Springs for the look: a soft overshoot like iOS / visionOS.
            obj.lift, obj.lift_v = spring(obj.lift, obj.lift_v, 1.0 if obj.held else 0.0, dt, 0.35, 0.7)
            obj.appear, obj.appear_v = spring(obj.appear, obj.appear_v, 1.0, dt, 0.5, 0.62)
            want = 1.0 if (obj.held or obj.id in hovered) else 0.0
            obj.hover_k += (want - obj.hover_k) * (1 - math.exp(-dt / 0.12))
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
        eye = np.array([0.0, 0.0, CAM_Z])
        for obj in self.objects:
            world = obj.world(display=True)
            if not obj.mesh.faces:
                continue
            screen, depth = project(world, width, height)
            tri = np.array([f[:3] for f in obj.mesh.faces])  # normals from 3 corners
            a, b, c = world[tri[:, 0]], world[tri[:, 1]], world[tri[:, 2]]
            n = np.cross(b - a, c - a)
            norm = np.linalg.norm(n, axis=1)
            ok = norm > 1e-12
            n[ok] /= norm[ok, None]
            centre = (a + b + c) / 3
            facing = np.einsum("ij,ij->i", n, eye - centre)
            shade = 0.35 + 0.65 * np.clip(n @ light, 0.0, None)
            mean_depth = depth[tri].mean(axis=1)
            colors = obj.mesh.colors
            held = obj.held or obj.id == self.selected
            for i, face in enumerate(obj.mesh.faces):
                if not ok[i]:
                    continue
                out.append(
                    {
                        "id": obj.id,
                        "points": screen[list(face)],
                        "depth": float(mean_depth[i]),
                        "shade": float(shade[i]),
                        "front": bool(facing[i] > 0),
                        "color": colors[i] if colors and i < len(colors) else obj.color,
                        "held": held,
                        "model": colors is not None,  # a designed object
                    }
                )
        out.sort(key=lambda f: -f["depth"])
        return out

    def glass(self, width: float, height: float) -> list[dict]:
        """What the glass look needs, one entry per hologram, far to near.

        * ``faces``: front faces (view px), their shade 0..1 and how much
          they turn away from you (``rim`` 0..1: the thin-film rainbow);
        * ``outline``: the silhouette as segments (where a front face meets
          a back face) — the rainbow edge is drawn along it;
        * ``edges`` / ``back_edges``: the sharp creases in front / seen
          through the glass (none on smooth shapes);
        * ``centre`` and ``radius`` in view px, for the shine and shadow.
        """
        self.view = (width, height)
        light = np.array([-0.4, 0.7, 0.6])
        light /= np.linalg.norm(light)
        eye = np.array([0.0, 0.0, CAM_Z])
        out = []
        for obj in sorted(self.objects, key=lambda o: o.pos[2]):  # far (low z) first
            if not obj.mesh.faces:
                continue
            world = obj.world(display=True)
            screen, depth = project(world, width, height)
            tri = np.array([f[:3] for f in obj.mesh.faces])
            a, b, c = world[tri[:, 0]], world[tri[:, 1]], world[tri[:, 2]]
            n = np.cross(b - a, c - a)
            norm = np.linalg.norm(n, axis=1)
            ok = norm > 1e-12
            n[ok] /= norm[ok, None]
            centre = (a + b + c) / 3
            to_eye = eye - centre
            to_eye /= np.linalg.norm(to_eye, axis=1)[:, None] + 1e-12
            facing = np.einsum("ij,ij->i", n, to_eye)
            front = (facing > 0) & ok
            shade = 0.35 + 0.65 * np.clip(n @ light, 0.0, None)
            order = np.argsort(-depth[tri].mean(axis=1))
            colors = obj.mesh.colors
            faces = [
                {
                    "points": screen[list(obj.mesh.faces[i])],
                    "shade": float(shade[i]),
                    "rim": float(1 - abs(facing[i])),
                    "color": colors[i] if colors and i < len(colors) else obj.color,
                }
                for i in order
                if front[i]
            ]
            pairs, lone = self._adjacency(obj.mesh)
            outline, edges, back = [], [], []
            if len(pairs):
                f1, f2 = pairs[:, 2], pairs[:, 3]
                sil = front[f1] != front[f2]
                crease = ~sil & (np.einsum("ij,ij->i", n[f1], n[f2]) < math.cos(math.radians(20)))
                if obj.mesh.smooth:
                    crease[:] = False
                for (va, vb, fa, _fb), is_sil, is_crease in zip(pairs, sil, crease):
                    seg = (screen[va], screen[vb])
                    if is_sil:
                        outline.append(seg)
                    elif is_crease:
                        (edges if front[fa] else back).append(seg)
            for va, vb, fa in lone:  # open borders (a drawn tube's ends are closed)
                if front[fa]:
                    outline.append((screen[va], screen[vb]))
            ((cx, cy),) = project(obj.pos[None], width, height)[0]
            k = CAM_Z / max(CAM_Z - obj.pos[2], 0.05) * (width / 2) / HALF_W
            out.append(
                {
                    "id": obj.id,
                    "name": obj.name,
                    "size_cm": obj.size_cm(),
                    "faces": faces,
                    "outline": outline,
                    "edges": edges,
                    "back_edges": back,
                    "centre": (float(cx), float(cy)),
                    "radius": float(obj.radius() * obj.display() * k),
                    "lift": float(obj.lift),
                    "appear": float(max(0.0, min(1.0, obj.appear))),
                    "hover_k": float(obj.hover_k),
                    "color": obj.color,
                    "model": colors is not None,
                    "held": obj.held,
                    "selected": obj.id == self.selected,
                    "hover": obj.id in self.hover.values(),
                }
            )
        return out

    def _adjacency(self, mesh: Mesh) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
        """Edges with their two faces (va, vb, face1, face2), and lone edges.

        Cached per mesh topology (sculpting moves vertices, not faces)."""
        cache = getattr(self, "_adj_cache", None)
        if cache is None:
            cache = self._adj_cache = {}
        key = id(mesh.faces)
        hit = cache.get(key)
        if hit is not None and hit[0] is mesh.faces:
            return hit[1], hit[2]
        # Coincident vertices (a sphere's poles, a crescent's tips) count as one.
        _uniq, ids = np.unique(np.round(mesh.vertices, 6), axis=0, return_inverse=True)
        ids = ids.reshape(-1)
        seen: dict[tuple[int, int], tuple[int, int, int]] = {}
        pairs = []
        for fi, face in enumerate(mesh.faces):
            for k in range(len(face)):
                va, vb = face[k], face[(k + 1) % len(face)]
                ka, kb = int(ids[va]), int(ids[vb])
                if ka == kb:
                    continue
                key2 = (min(ka, kb), max(ka, kb))
                first = seen.pop(key2, None)
                if first is None:
                    seen[key2] = (va, vb, fi)
                elif first[2] != fi:
                    pairs.append((first[0], first[1], first[2], fi))
        arr = np.array(pairs, int).reshape(-1, 4)
        lone = list(seen.values())
        if len(cache) > 64:
            cache.clear()
        cache[key] = (mesh.faces, arr, lone)
        return arr, lone

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


def recipe_request(obj: Holo) -> str:
    """What Blender Pro should build from a designed hologram."""
    recipe = obj.recipe or {}
    parts = "\n".join(
        f"- {p['name']}: {p['shape']} " + " x ".join(f"{v * 100:.1f}" for v in p["size"])
        + " cm at (" + ", ".join(f"{v * 100:.1f}" for v in p["pos"]) + f") cm, rot {p['rot']}"
        + _free_brief(p)
        for p in recipe.get("parts", [])
    )
    return (
        f"{recipe.get('name', obj.kind)}, ultra detallado y realista, calidad de producto "
        f"profesional. {recipe.get('description', '')} Medidas reales; esta es la "
        f"distribución de piezas del holograma (respétala y añade todo el detalle real: "
        f"biseles, chaflanes, materiales PBR, texto/logos si aplica):\n{parts}"
    )


def _free_brief(part: dict) -> str:
    """The points of a lathe / extrude / tube part, in cm (for Blender Pro)."""
    def cm(pts: Sequence[Sequence[float]]) -> str:
        return "[" + ", ".join("(" + ", ".join(f"{v * 100:.1f}" for v in p) + ")" for p in pts) + "]"

    if part.get("profile"):
        return f", lathe profile (radius, height) cm {cm(part['profile'])}"
    if part.get("outline"):
        return f", outline (x, y) cm {cm(part['outline'])}"
    if part.get("path"):
        return f", tube path cm {cm(part['path'])}, radius {float(part.get('radius', 0)) * 100:.1f} cm"
    return ""


# Hologram axes (x right, y up, z toward you) -> Blender's (x, -z, y), z up.
TO_BLENDER = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


def blender_name(obj: Holo) -> str:
    return f"Holo {obj.id}"


def blender_state(objects: Sequence[Holo]) -> dict:
    """Every hologram as Blender sees it: real-size local mesh, its 4x4
    matrix, materials per face. The Blender window applies it live."""
    c = TO_BLENDER
    out = {}
    for obj in objects:
        base = obj.base or 1.0
        rot = c @ obj.rot @ c.T
        loc = c @ obj.pos / base
        m = rot * obj.scale
        matrix = [[*map(float, m[i]), float(loc[i])] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]
        verts = (obj.mesh.vertices @ c.T) / base
        colors = obj.mesh.colors or [obj.color] * len(obj.mesh.faces)
        out[blender_name(obj)] = {
            "label": obj.name,
            "matrix": [[round(x, 6) for x in row] for row in matrix],
            "verts": [[round(float(x), 6) for x in v] for v in verts],
            "faces": [list(map(int, f)) for f in obj.mesh.faces],
            "colors": [[round(float(x), 3) for x in col] for col in colors],
            "smooth": bool(obj.mesh.smooth),
            "vh": f"{len(verts)}:{float(np.abs(verts).sum()):.6f}",
        }
    return {"objects": out}


BLENDER_SCRIPT = r'''import bpy, json, os
from mathutils import Matrix

SYNC = r"""__SYNC__"""
SAVE = r"""__SAVE__"""
FIRST = json.loads(r"""__STATE__""")
_seen = {"mtime": 0.0, "vh": {}}


def _material(rgb):
    name = "Holo %.3f %.3f %.3f" % tuple(rgb)
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.3
            bsdf.inputs["Metallic"].default_value = 0.2
    return mat


def _build(name, item):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in item["verts"]], [], [tuple(f) for f in item["faces"]])
    mesh.validate()
    slots = {}
    for i, rgb in enumerate(item["colors"]):
        key = tuple(rgb)
        if key not in slots:
            slots[key] = len(mesh.materials)
            mesh.materials.append(_material(key))
        if i < len(mesh.polygons):
            mesh.polygons[i].material_index = slots[key]
    if item.get("smooth"):
        for poly in mesh.polygons:
            poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    obj["sergio_label"] = item.get("label", name)
    bpy.context.scene.collection.objects.link(obj)
    if item.get("smooth"):
        mod = obj.modifiers.new("Suave", "SUBSURF")
        mod.levels, mod.render_levels = 1, 2
    _seen["vh"][name] = item.get("vh")
    return obj


def apply(state):
    names = set(state.get("objects", {}))
    for name, item in state.get("objects", {}).items():
        obj = bpy.data.objects.get(name)
        if obj is None or _seen["vh"].get(name) and len(obj.data.vertices) != len(item["verts"]):
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
            obj = _build(name, item)
        elif item.get("vh") != _seen["vh"].get(name):  # sculpted with the hands
            flat = [c for v in item["verts"] for c in v]
            obj.data.vertices.foreach_set("co", flat)
            obj.data.update()
            _seen["vh"][name] = item.get("vh")
        obj.matrix_world = Matrix(item["matrix"])
    for obj in list(bpy.data.objects):  # deleted in Sergio ve: gone here too
        if obj.name.startswith("Holo ") and obj.name not in names:
            bpy.data.objects.remove(obj, do_unlink=True)


def _sync():
    try:
        mtime = os.path.getmtime(SYNC)
    except OSError:
        return 0.5
    if mtime == _seen["mtime"]:
        return 0.25
    _seen["mtime"] = mtime
    try:
        with open(SYNC, encoding="utf-8") as fh:
            apply(json.load(fh))
    except Exception as exc:  # a file half written: next time
        print("SERGIO_SYNC_SKIP", exc)
    return 0.25


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
apply(FIRST)
sun = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (0.8, 0.2, 0.6)
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("Cámara", bpy.data.cameras.new("Cámara"))
cam.location = (0.0, -4.5, 1.2)
cam.rotation_euler = (1.35, 0.0, 0.0)
scene.collection.objects.link(cam)
scene.camera = cam
os.makedirs(os.path.dirname(SAVE), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=SAVE)
print("SERGIO_SAVED", SAVE, len(FIRST.get("objects", {})))
if SYNC and not bpy.app.background:
    # Live: what your hands do to the holograms happens here too.
    bpy.app.timers.register(_sync, first_interval=0.5, persistent=True)
'''


def to_bpy(objects: Sequence[Holo], save_path: str, sync_path: str = "") -> str:
    """A Blender script that rebuilds the holograms (real size, materials),
    saves the .blend and, with *sync_path*, keeps following your hands."""
    import json

    state = json.dumps(blender_state(objects))
    return (
        BLENDER_SCRIPT.replace("__SYNC__", sync_path)
        .replace("__SAVE__", save_path)
        .replace("__STATE__", state)
    )


__all__ = [
    "COLORS",
    "Holo",
    "HoloScene",
    "MAKERS",
    "Mesh",
    "assemble",
    "blender_state",
    "recipe_request",
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

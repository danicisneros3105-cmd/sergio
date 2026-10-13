"""Closed poles and continuous rounded surfaces in the actual glass renderer."""

from collections import Counter

import numpy as np
from sergio_escritorio.holo import HoloScene, sphere


def test_sphere_is_closed_and_has_no_zero_area_pole_faces():
    mesh = sphere()
    edges = Counter()
    for face in mesh.faces:
        a, b, c = mesh.vertices[list(face[:3])]
        assert np.linalg.norm(np.cross(b - a, c - a)) > 1e-10
        for i, vertex in enumerate(face):
            edges[tuple(sorted((vertex, face[(i + 1) % len(face)])))] += 1
    assert set(edges.values()) == {2}


def test_glass_reports_curvature_and_keeps_real_surface_materials():
    scene = HoloScene()
    scene.add("esfera")
    scene.add("cubo")
    rounded = next(
        shape for shape in scene.glass(800, 600) if shape["name"].startswith("Esfera")
    )
    assert rounded["smooth"] and not rounded["model"]
    assert rounded["faces"] and rounded["radius"] > 0

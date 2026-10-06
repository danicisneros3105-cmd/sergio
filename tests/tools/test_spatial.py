"""Depth, real distances between objects, and the size logic check."""

from __future__ import annotations

import math

from openjarvis.tools.spatial import describe_relations, focal_px, locate, relations, typical

W, H = 1280, 720


def box_for(x_m, y_m, z_m, size_m):
    """The box a pinhole camera (70° HFOV) sees for a thing at (x, y, z)."""
    f = focal_px(W)
    px = f * size_m / z_m
    cx, cy = W / 2 + x_m * f / z_m, H / 2 + y_m * f / z_m
    return [(cx - px / 2) / W, (cy - px / 2) / H, px / W, px / H]


def test_distances_come_out_right_from_known_sizes():
    items = [
        {"label": "taza", "box": box_for(-0.25, 0.0, 0.8, 0.10)},
        {"label": "celular", "box": box_for(0.20, 0.0, 0.8, 0.15)},
        {"label": "manzana", "box": box_for(0.45, 0.0, 1.0, 0.08)},
    ]
    placed = locate(items, W, H)
    assert [round(i["depth_m"], 2) for i in placed] == [0.8, 0.8, 1.0]
    pairs = {(p["a"], p["b"]): p["m"] for p in relations(placed)}
    assert math.isclose(pairs[("taza", "celular")], 0.45, abs_tol=0.01)
    assert math.isclose(pairs[("celular", "manzana")], math.dist((0.2, 0, 0.8), (0.45, 0, 1.0)), abs_tol=0.01)
    assert "taza a 45 cm de celular" in describe_relations(relations(placed))


def test_a_face_is_the_ruler_for_a_person():
    face = box_for(0.0, -0.3, 1.5, 0.15)
    person = {"label": "persona", "box": [0.3, 0.1, 0.4, 0.9], "face_box": face}
    assert math.isclose(locate([person], W, H)[0]["depth_m"], 1.5, abs_tol=0.02)


def test_names_that_do_not_fit_their_size_are_doubtful():
    items = [{"label": "silla", "box": box_for(0, 0, 0.8, 0.06), "size_cm": 6},
             {"label": "celular", "box": box_for(0.2, 0, 0.8, 0.15), "size_cm": 15}]
    placed = locate(items, W, H)
    assert "no mide 6 cm" in placed[0]["doubt"] and placed[1]["doubt"] == ""
    assert typical("taza azul") == typical("taza") and typical("cosa rara") is None

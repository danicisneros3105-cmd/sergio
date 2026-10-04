"""Face geometry (175 measurements), old photos and family resemblance."""

from __future__ import annotations

import math
import os
import random
from pathlib import Path

import numpy as np
import pytest

from openjarvis.faces import signature as sig
from openjarvis.faces.book import FaceBook, kin_score, kin_words, looks_old


def _face_points(
    seed: int = 0, scale: float = 1.0
) -> dict[str, tuple[float, float, float]]:
    rng = random.Random(seed)
    base = {
        "tr": (0, -90, 10), "g": (0, -55, 18), "n": (0, -40, 20),
        "en_d": (-16, -35, 8), "en_i": (16, -35, 8), "ex_d": (-45, -36, 0), "ex_i": (45, -36, 0),
        "p_d": (-31, -35, 6), "p_i": (31, -35, 6), "prn": (0, 5, 38), "sn": (0, 15, 25),
        "al_d": (-18, 10, 15), "al_i": (18, 10, 15), "zy_d": (-68, -20, -20), "zy_i": (68, -20, -20),
        "go_d": (-55, 45, -25), "go_i": (55, 45, -25), "gn": (0, 85, 12),
        "ch_d": (-25, 35, 12), "ch_i": (25, 35, 12), "ls": (0, 27, 20), "li": (0, 45, 18),
        "sto": (0, 35, 18), "sci_d": (-30, -55, 12), "sci_i": (30, -55, 12),
        "ps_d": (-31, -40, 8), "pi_d": (-31, -30, 8),
    }  # fmt: skip
    return {
        k: tuple(scale * (v + rng.uniform(-2, 2)) for v in xyz)
        for k, xyz in base.items()
    }


def _rotate(points, yaw, pitch):
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    out = {}
    for k, (x, y, z) in points.items():
        x, z = cy * x + sy * z, -sy * x + cy * z
        y, z = cp * y - sp * z, sp * y + cp * z
        out[k] = (x + 300, y + 200, z)
    return out


def test_at_least_133_named_patterns():
    assert sig.SIZE == 175 >= 133 and len(sig.NAMES) == sig.SIZE
    assert len(sig.measure(_face_points())) == sig.SIZE
    assert len(set(sig.POINTS.values())) == len(sig.POINTS)  # distinct mesh points


def test_signature_ignores_distance_and_head_turn():
    face = _face_points(1)
    near = sig.measure(face)
    far_turned = sig.measure(_rotate(_face_points(1, scale=0.4), yaw=0.5, pitch=-0.3))
    assert sig.distance(near, far_turned) < 1e-9
    assert sig.similarity(near, far_turned) == pytest.approx(1.0)


def test_different_proportions_are_measured_as_different():
    a, b = sig.measure(_face_points(1)), sig.measure(_face_points(2))
    wide = _face_points(1)
    wide.update({k: (v[0] * 1.25, v[1], v[2]) for k, v in wide.items()})
    c = sig.measure(wide)
    assert 0 < sig.distance(a, b) < sig.distance(a, c)
    assert sig.similarity(a, c) < sig.similarity(a, b) < 1.0


def test_family_resemblance_scale():
    assert kin_score(0.05, None) == 0.0 and kin_score(0.5, None) == 1.0
    assert 0.3 < kin_score(0.28, 0.7) < 0.8
    assert kin_words(0.7) == "parecido familiar alto"
    assert kin_words(0.1) == "sin parecido familiar claro"


def test_old_photo_detection():
    rng = np.random.default_rng(0)
    colourful = rng.integers(0, 255, (300, 300, 3), dtype=np.uint8)
    grey = np.repeat(rng.integers(80, 180, (300, 300, 1), dtype=np.uint8), 3, axis=2)
    assert looks_old(grey) and not looks_old(colourful)


# -- with the real models (set SERGIO_FACE_MODELS and SERGIO_FACE_IMAGES) ------
MODELS = os.environ.get("SERGIO_FACE_MODELS", "")
IMAGES = os.environ.get("SERGIO_FACE_IMAGES", "")
real = pytest.mark.skipif(
    not (MODELS and IMAGES and Path(MODELS).is_dir() and Path(IMAGES).is_dir()),
    reason="real face models/images not available",
)


def _old(image):
    import cv2

    g = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) * 0.55 + 60
    sepia = np.stack([g * 0.82, g * 0.95, g * 1.08], -1)
    sepia += np.random.default_rng(0).normal(0, 9, sepia.shape)
    out = cv2.GaussianBlur(np.clip(sepia, 0, 255).astype(np.uint8), (5, 5), 1.2)
    return cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 35])[1].tobytes()


@real
def test_real_old_photo_is_recognised_with_its_geometry(tmp_path):
    import shutil

    import cv2

    models = tmp_path / "models"
    shutil.copytree(MODELS, models)
    book = FaceBook(tmp_path / "faces", models_dir=models)
    portrait = (Path(IMAGES) / "portrait.jpg").read_bytes()
    assert book.enroll("Persona A", portrait, consent=True) == 1
    assert book.people()[0]["signatures"] == 1  # the 175 measurements were stored
    old = _old(cv2.imread(str(Path(IMAGES) / "portrait.jpg")))
    (match,) = book.identify_photo(old)
    assert (
        match.name == "Persona A"
        and match.geometry is not None
        and match.geometry > 0.5
    )
    family = book.kinship(old)[0]["people"][0]
    assert family["name"] == "Persona A" and family["same_person"]
    group = (Path(IMAGES) / "sample1.jpg").read_bytes()
    strangers = book.identify_photo(group)
    assert strangers and all(m.name == "" for m in strangers)
    assert all(m.candidates and m.candidates[0][0] == "Persona A" for m in strangers)


def test_companion_and_server_agree_on_the_points():
    import sys

    sys.path.insert(0, str(Path(__file__).parents[2] / "windows"))
    from sergio_escritorio.vision import SIGNATURE_POINTS

    assert SIGNATURE_POINTS == sig.POINTS


def test_signature_from_companion_points_and_box_matching():
    pts = {k: list(v) for k, v in _face_points(4).items()}
    assert sig.from_points(pts) == sig.measure(_face_points(4))
    assert sig.from_points({"n": [1, 2, 3]}) is None
    faces = [{"box": [0, 0, 50, 50], "points": pts}, {"box": [200, 0, 60, 60], "points": {}}]
    assert sig.match_points((5, 5, 50, 50), faces) is faces[0]
    assert sig.match_points((400, 400, 20, 20), faces) is None


@real
def test_real_points_measured_on_windows_side_are_used(tmp_path, monkeypatch):
    import shutil
    import sys

    import cv2

    sys.path.insert(0, str(Path(__file__).parents[2] / "windows"))
    from sergio_escritorio import vision

    monkeypatch.setattr(vision, "MODELS_DIR", Path(MODELS))
    monkeypatch.setattr(vision, "ensure_model", lambda name, folder=None: Path(MODELS) / name)
    models = tmp_path / "models"
    shutil.copytree(MODELS, models)
    (models / "face_landmarker.task").unlink()  # the server cannot measure itself
    book = FaceBook(tmp_path / "faces", models_dir=models)
    portrait = (Path(IMAGES) / "portrait.jpg").read_bytes()
    book._measurer = type("NoMesh", (), {"signature": lambda *a: None})()
    book.enroll("Persona A", portrait, consent=True, faces=vision.face_points(portrait))
    assert book.people()[0]["signatures"] == 1
    old = _old(cv2.imread(str(Path(IMAGES) / "portrait.jpg")))
    (match,) = book.identify_photo(old, vision.face_points(old))
    assert match.name == "Persona A" and match.geometry is not None and match.geometry > 0.5

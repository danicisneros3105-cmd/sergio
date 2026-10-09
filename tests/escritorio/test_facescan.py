"""Face ID-style scan: the ring, the 3D map in millimetres, the scanner."""

from __future__ import annotations

import math

import pytest

np = pytest.importorskip("numpy")

from sergio_escritorio import facescan  # noqa: E402
from sergio_escritorio.facescan import ScanRing, canonical_mesh  # noqa: E402


def test_the_ring_lights_where_the_head_points_and_fills_the_gaps():
    ring = ScanRing(started=0.0)
    assert ring.feed(2.0, 1.0) is None  # looking straight: nothing yet
    right = ring.feed(20.0, 0.0)
    up = ring.feed(0.0, 20.0)
    assert right == 0 and up == 9  # 0° = to one side, 90° = up
    assert ring.lit[9] and ring.lit[0]
    ring = ScanRing(started=0.0)
    ring.feed(20.0, 0.0)
    ring.feed(20 * math.cos(math.radians(45)), 20 * math.sin(math.radians(45)))
    # swept from 0° to 45° between two frames: the marks in between light too
    assert all(ring.lit[0:5])


def test_the_scan_ends_when_the_circle_is_done_or_time_is_up():
    ring = ScanRing(started=0.0)
    for deg in range(0, 360, 5):
        ring.feed(20 * math.cos(math.radians(deg)), 20 * math.sin(math.radians(deg)))
    assert ring.fraction == 1.0 and ring.angles() == 8
    assert not ring.done(1.0)  # too quick to be a real scan
    assert ring.done(4.0)
    lazy = ScanRing(started=0.0)
    lazy.feed(20.0, 0.0)
    assert not lazy.done(10.0) and lazy.done(facescan.MAX_SECONDS + 0.1)


def _face(rot_deg: float = 0.0, scale: float = 1.0, iris_px: float = 12.0):
    """A synthetic 478-point face, normalised like MediaPipe (x, y in 0..1)."""
    rng = np.random.default_rng(0)
    pts = rng.normal(0, 40, (478, 3))  # pixels around the centre
    pts[:, 2] *= 0.5
    # irises: centre + four edge points, *iris_px* across
    for centre, edge in ((468, (469, 470, 471, 472)), (473, (474, 475, 476, 477))):
        cx = -32.0 if centre == 468 else 32.0
        pts[centre] = (cx, 0.0, 0.0)
        r = iris_px / 2
        for k, (dx, dy) in zip(edge, ((r, 0), (0, r), (-r, 0), (0, -r))):
            pts[k] = (cx + dx, dy, 0.0)
    a = math.radians(rot_deg)
    rot = np.array(
        [[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]]
    )
    pts = (pts @ rot.T) * scale
    w, h = 1280, 720
    return [((x + 640) / w, (y + 360) / h, z / w) for x, y, z in pts], w, h


def test_the_3d_map_is_in_millimetres_and_frames_line_up():
    mesh = canonical_mesh([_face(0), _face(0, scale=1.2), _face(1.0)])
    assert mesh is not None and mesh["unit"] == "mm" and mesh["frames"] == 3
    assert len(mesh["points"]) == 478
    # pupils 64 px apart with a 12 px iris: 64 * 11.7 / 12 = 62.4 mm
    assert mesh["measures"]["entre pupilas"] == pytest.approx(62.4, abs=0.6)
    assert mesh["spread_mm"] < 1.0  # the same face, scaled and turned: one map
    assert canonical_mesh([_face(0)]) is None  # one frame is not a map


class _Info:
    def __init__(self, yaw, pitch):
        self.yaw, self.pitch = yaw, pitch
        self.box = (0.4, 0.3, 0.2, 0.3)
        self.points3 = _face(yaw / 4)[0]


def test_scanner_collects_frames_and_builds_the_map():
    pytest.importorskip("cv2")
    clock = [0.0]
    frame = np.zeros((720, 1280, 3), np.uint8)
    angles = iter(range(0, 3600, 12))

    def faces():
        deg = next(angles)
        return [
            _Info(20 * math.cos(math.radians(deg)), 20 * math.sin(math.radians(deg)))
        ]

    def sleep(s):
        clock[0] += s

    scan = facescan.Scanner(lambda: frame, faces, clock=lambda: clock[0], sleep=sleep)
    jpegs, mesh = scan.run()
    assert not scan.active and scan.ring.fraction >= facescan.DONE_FRACTION
    assert 3 <= len(jpegs) <= 60 and jpegs[0][:2] == b"\xff\xd8"
    assert mesh is not None and scan.result is mesh and len(mesh["points"]) == 478


def test_scanner_waits_for_one_face():
    clock = [0.0]
    scan = facescan.Scanner(
        lambda: np.zeros((10, 10, 3), np.uint8),
        lambda: [_Info(0, 0), _Info(0, 0)],
        clock=lambda: clock[0],
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
    )
    jpegs, mesh = scan.run()
    assert jpegs == [] and mesh is None
    assert "Solo una persona" in scan.message


def test_ring_and_head_draw():
    pytest.importorskip("PySide6")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    img = QImage(300, 300, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    ring = ScanRing(started=0.0)
    ring.feed(20.0, 0.0)
    facescan.draw_ring(p, QPointF(150, 150), 80, ring, 0.0)
    mesh = canonical_mesh([_face(0), _face(1.0)])
    facescan.draw_head(
        p, QRectF(50, 50, 200, 200), mesh["points"], 0.5, [(0, 1), (1, 2)]
    )
    p.end()
    lit = sum(
        1
        for x in range(300)
        for y in range(0, 300, 3)
        if img.pixelColor(x, y).green() > 150
    )
    assert lit > 50  # something green (the lit mark) and blue dots were drawn


@pytest.mark.parametrize(
    ("said", "name"),
    [
        ("Sergio, escanea mi cara", ""),
        ("escanéame", ""),
        ("aprende mi cara en 3D", ""),
        ("escanea mi cara, soy Daniel Cisneros", "Daniel Cisneros"),
        ("aprende la cara de María José como Face ID", "María José"),
        ("guarda mi cara de nuevo", ""),
    ],
)
def test_scan_orders(said, name):
    from sergio_escritorio.quick import parse_quick

    q = parse_quick(said)
    assert q is not None and q.kind == "face_scan" and q.arg == name


def test_not_scan_orders():
    from sergio_escritorio.quick import parse_quick

    for said in ("escanea el documento", "analiza mi cara"):
        q = parse_quick(said)
        assert q is None or q.kind != "face_scan"


def test_sergio_calls_the_owner_senor_with_dark_humour_limits():
    from sergio_escritorio.voice import VOICE_STYLE

    from openjarvis.speech.gemini_live import live_instructions

    live = live_instructions({}, owner="Daniel")
    assert "«señor»" in live and "humor negro" in live
    assert "nunca sobre grupos de personas" in live and "momento es serio" in live
    assert (
        "«señor»" in VOICE_STYLE
        and "dark-humour" in VOICE_STYLE
        and "never about groups" in VOICE_STYLE
    )

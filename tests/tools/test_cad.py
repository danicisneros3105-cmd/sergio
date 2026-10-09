"""CAD: images vectorised to DXF, Blender models drawn in three views."""

from __future__ import annotations

import io

import pytest

cv2 = pytest.importorskip("cv2")
ezdxf = pytest.importorskip("ezdxf")
np = pytest.importorskip("numpy")

from openjarvis.tools import cad  # noqa: E402


def _part_png() -> bytes:
    img = np.full((400, 600, 3), 255, np.uint8)
    cv2.rectangle(img, (50, 60), (550, 340), (0, 0, 0), -1)  # a plate 500 x 280 px
    cv2.circle(img, (150, 200), 50, (255, 255, 255), -1)  # two holes
    cv2.circle(img, (450, 200), 30, (255, 255, 255), -1)
    return cv2.imencode(".png", img)[1].tobytes()


def _dims(data: bytes) -> list[str]:
    doc = ezdxf.read(io.StringIO(data.decode()))
    return [
        doc.blocks.get(d.dxf.geometry).query("MTEXT")[0].plain_text()
        for d in doc.modelspace().query("DIMENSION")
    ]


def test_an_image_becomes_a_dxf_at_real_size_with_its_holes():
    dxf, info = cad.image_to_dxf(_part_png(), width_mm=200)
    assert info["shapes"] == 1 and info["holes"] == 2
    assert info["width_mm"] == 200.0 and info["height_mm"] == pytest.approx(112, abs=1)
    assert cad.check_dxf(dxf)["LWPOLYLINE"] == 3
    assert _dims(dxf) == ["200", "112"]  # millimetres, no stray scale factor


def test_dark_background_images_work_too():
    inverted = cv2.imencode(
        ".png", 255 - cv2.imdecode(np.frombuffer(_part_png(), np.uint8), 1)
    )[1].tobytes()
    _, info = cad.image_to_dxf(inverted, width_mm=100)
    assert info["shapes"] >= 1


def test_a_model_is_drawn_in_three_views_with_dimensions():
    # A 100 x 50 x 20 mm box: its 12 edges (metres).
    x, y, z = 0.1, 0.05, 0.02
    corners = [(a, b, c) for a in (0, x) for b in (0, y) for c in (0, z)]
    edges = [
        [*p, *q]
        for i, p in enumerate(corners)
        for q in corners[i + 1 :]
        if sum(abs(u - v) > 1e-9 for u, v in zip(p, q)) == 1
    ]
    dxf, info = cad.model_to_dxf({"Caja": edges}, "Caja")
    assert info["size_mm"] == [100.0, 50.0, 20.0] and info["views"] == 3
    assert sorted(_dims(dxf)) == sorted(["100", "20", "100", "50", "50", "20"])
    assert cad.check_dxf(dxf)["TEXT"] >= 7  # view names + title block
    assert cad.preview_png(dxf)[:8] == b"\x89PNG\r\n\x1a\n"


def test_edges_come_from_blender_logs():
    log = 'noise\nSERGIO_EDGES {"A": [[0,0,0,1,0,0]]}\n'
    assert cad.parse_edges(log) == {"A": [[0, 0, 0, 1, 0, 0]]}
    with pytest.raises(ValueError):
        cad.parse_edges("nothing")

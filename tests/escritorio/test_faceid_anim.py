"""Face ID's animation: scan, wink-and-check on success, a shake on failure."""

from __future__ import annotations

from sergio_escritorio import faceid_anim as f


def test_success_joins_winks_then_checks():
    assert f.join_fraction(0.0) == 0.0 and f.join_fraction(f.JOIN) == 1.0
    assert not f.winking(0.1) and f.winking(0.4) and not f.winking(0.7)
    assert f.check_fraction(f.CHECK[0]) == 0.0 and f.check_fraction(f.CHECK[1]) == 1.0
    peak = max(f.spring_scale(f.CHECK[0] + i / 100, f.CHECK[0]) for i in range(40))
    assert 1.04 < peak < 1.13  # a soft pop, not a jump
    assert abs(f.spring_scale(f.CHECK[0] + 2.0, f.CHECK[0]) - 1.0) < 0.002


def test_failure_shakes_and_settles():
    offsets = [f.shake_offset(i / 100) for i in range(70)]
    assert max(offsets) > 0.4 and min(offsets) < -0.3  # both ways
    assert f.shake_offset(f.SHAKE) == 0.0 and f.shake_offset(-1) == 0.0
    assert abs(f.shake_offset(0.5)) < abs(max(offsets))  # dies down


def test_glyph_phases_and_finish():
    now = [0.0]
    g = f.FaceIDGlyph(clock=lambda: now[0])
    g.start("scan")
    assert not g.finished()
    g.start("success")
    now[0] = 1.0
    assert not g.finished()
    now[0] = 1.5
    assert g.finished()
    g.start("nonsense")
    assert g.phase == "idle"
    assert all(-1.0 <= f.glance(t / 10) <= 1.0 for t in range(60))


def test_paints_every_phase(qtbot=None):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    for phase, t in (
        ("scan", 0.3),
        ("success", 0.4),
        ("success", 0.7),
        ("fail", 0.1),
        ("idle", 0.0),
    ):
        now = [0.0]
        g = f.FaceIDGlyph(clock=lambda: now[0])
        g.start(phase)
        now[0] = t
        img = QImage(120, 120, QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        g.paint(p, QRectF(10, 10, 100, 100))
        p.end()
        assert any(
            img.pixel(x, y) != 0 for x in range(0, 120, 3) for y in range(0, 120, 3)
        ), phase


def test_notch_grows_into_face_id_and_back():
    from PySide6.QtWidgets import QApplication
    from sergio_escritorio import notch as notch_mod

    QApplication.instance() or QApplication([])
    n = notch_mod.Notch(reduced_motion=True)
    n.faceid("scan")
    assert n.target_size() == notch_mod.FACEID
    n._tick()
    assert (round(n._w), round(n._h)) == tuple(map(round, notch_mod.FACEID))
    n.faceid("idle")
    assert n.target_size() == notch_mod.COMPACT
    path = notch_mod.notch_path(n.pill())
    assert path.boundingRect().width() > n.pill().width()  # the concave ears flare out

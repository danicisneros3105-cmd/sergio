"""The cursor companion renders (Qt offscreen) and the action captions."""

import os

import pytest
from sergio_escritorio.app import activity_caption


@pytest.mark.parametrize(
    "result,caption",
    [
        ("click at (930, 1020)", "Haciendo clic"),
        ("typed 12 characters", "Escribiendo"),
        ("opened Spotify", "Abriendo Spotify"),
        ("focused WhatsApp", "Cambiando a WhatsApp"),
        ("waited 1s", ""),
    ],
)
def test_activity_captions_in_spanish(result, caption):
    assert activity_caption(result) == caption


def test_companion_draws_every_state():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # Qt runtime libraries missing on this machine
        pytest.skip(str(exc))
    from sergio_escritorio.companion import STATE_COLORS, Companion

    app = QApplication.instance() or QApplication([])
    companion = Companion(follow=False)
    for state in STATE_COLORS:
        companion.set_state(state)
        companion.say("Listo, abrí Spotify y puse música tranquila.", 5)
        image = companion.grab().toImage()
        centre = companion.orb_centre().toPoint()
        assert image.pixelColor(centre.x() + 5, centre.y()).alpha() > 200  # orb drawn
        assert image.pixelColor(image.width() - 2, image.height() - 2).alpha() == 0
    companion.set_state("nonsense")
    assert companion.state == "idle"
    app.processEvents()


def _qt():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(str(exc))
    return QApplication.instance() or QApplication([])


def test_notch_grows_with_text_and_shrinks_back():
    _qt()
    from sergio_escritorio import notch as notch_mod

    clicks = []
    n = notch_mod.Notch(on_click=lambda: clicks.append(1))
    for _ in range(80):
        n._tick()
    assert (round(n._w), round(n._h)) == tuple(map(round, notch_mod.COMPACT))
    n.set_state("listening")
    for _ in range(80):
        n._tick()
    assert round(n._w) == round(notch_mod.MEDIUM[0])
    n.say(
        "Listo, abrí Spotify y puse una lista tranquila. ¿Quieres que suba el volumen?",
        30,
    )
    for _ in range(80):
        n._tick()
    assert round(n._w) == round(notch_mod.EXPANDED_W) and n._h > 58
    n.set_state("idle")
    n._caption_until = 0
    for _ in range(80):
        n._tick()
    assert round(n._w) == round(notch_mod.COMPACT[0])
    n.mousePressEvent(None)
    assert clicks == [1]


def test_notch_hides_over_fullscreen_apps_unless_active():
    _qt()
    from sergio_escritorio.notch import Notch

    fullscreen = [True]
    n = Notch(fullscreen_app=lambda: fullscreen[0])
    n._last_fs_check = -10
    n._respect_fullscreen()
    assert n.windowOpacity() == 0.0
    n.set_state("speaking")  # Sergio talks: show it even over a video
    n._last_fs_check = -10
    n._respect_fullscreen()
    assert n.windowOpacity() == 1.0


def test_character_draws_every_state():
    _qt()
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QImage, QPainter
    from sergio_escritorio.character import STATE_COLORS, draw_character

    for state in STATE_COLORS:
        img = QImage(80, 80, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        draw_character(p, QPointF(40, 40), 20, state, 1.0)
        p.end()
        assert img.pixelColor(40, 52).alpha() > 200  # body painted


def test_companion_flies_to_a_spot_and_comes_back():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(str(exc))
    from sergio_escritorio.companion import POINT_PAD, Companion

    app = QApplication.instance() or QApplication([])
    c = Companion(follow=False)
    c.point_at(500, 300, "Exportar", physical=False)
    assert c.pointing
    for _ in range(80):
        c._tick()
    assert abs(c.pos().x() - (500 - POINT_PAD)) <= 2
    assert abs(c.pos().y() - (300 - POINT_PAD)) <= 2
    out = os.environ.get("SERGIO_SHOT_DIR")
    image = c.grab()
    assert not image.isNull()
    if out:
        image.save(os.path.join(out, "companion-pointing.png"))
    c._target_until = 0
    c._tick()
    assert not c.pointing
    app.processEvents()

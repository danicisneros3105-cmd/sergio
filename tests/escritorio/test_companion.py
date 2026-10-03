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

"""Owner, 29 Oct 2026: «recuerda que es con la animación blur de abrir y
cerrar del iPhone Duo». Two programs side by side open with that fold too."""

import pytest
from sergio_escritorio.duo_veil import FRAMES, ease, glide, run_glide


def test_the_spring_starts_fast_overshoots_a_little_and_settles():
    assert ease(0) == 0 and ease(1) == 1
    assert ease(0.1) > 0.4  # quick out of the gate
    peak = max(ease(i / 100) for i in range(101))
    assert 1.0 < peak < 1.03  # a small overshoot, not a bounce


def test_windows_glide_to_their_halves_and_land_exactly():
    path = glide((100, 100, 800, 600), (960, 0, 960, 1040))
    assert len(path) == FRAMES and path[-1] == (960, 0, 960, 1040)
    xs = [r[0] for r in path]
    assert xs[0] > 100 and xs[0] < 960  # moving, not jumping


def test_both_windows_move_together_frame_by_frame():
    placed, slept = [], []
    run_glide(
        [(1, (0, 0, 10, 10), (0, 0, 50, 50)), (2, (90, 0, 10, 10), (50, 0, 50, 50))],
        lambda hwnd, r: placed.append((hwnd, r)),
        slept.append,
        frames=4,
    )
    assert [h for h, _ in placed] == [1, 2] * 4 and len(slept) == 4
    assert placed[-2] == (1, (0, 0, 50, 50)) and placed[-1] == (2, (50, 0, 50, 50))


def test_the_veil_blurs_the_screen_without_taking_clicks(qapp=None):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from sergio_escritorio.duo_veil import make_veil

    app = QApplication.instance() or QApplication([])
    veil = make_veil()
    assert veil.windowFlags() & Qt.WindowTransparentForInput
    veil.fold(0.1)
    assert veil.isVisible()
    app.processEvents()
    veil._done()
    assert not veil.isVisible()

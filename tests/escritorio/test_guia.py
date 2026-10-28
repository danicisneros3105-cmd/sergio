"""Drawings over the real screen: arrows, circles, a ghost cursor; gone on a click."""

import os

import pytest
from sergio_escritorio.control import Controller
from sergio_escritorio.guia import (
    CLICK_GRACE,
    FADE,
    STEP,
    Clock,
    Mark,
    arrow_tail,
    cursor_at,
    marks_from,
    understood,
)


def test_marks_are_cleaned_and_capped():
    marks = marks_from(
        [
            {"x": 100, "y": 200, "shape": "círculo", "text": "  Exportar  "},
            {"x": "nada", "y": 5},  # no place: dropped
            {"x": 10, "y": 20, "shape": "estrella"},  # unknown shape: an arrow
            {"x": 1, "y": 1, "shape": "box", "w": 99999, "depth": "2d"},
            *({"x": i, "y": i} for i in range(10)),
        ]
    )
    assert len(marks) == 6
    assert marks[0].shape == "circle" and marks[0].text == "Exportar"
    assert marks[1].shape == "arrow"
    assert marks[2].shape == "box" and marks[2].w == 4000 and not marks[2].depth


def test_a_click_ends_it_but_not_the_one_that_asked():
    clock = Clock(10.0)
    assert not clock.click(10.0 + CLICK_GRACE / 2)
    assert clock.alpha(11.0) == 1.0
    assert clock.click(11.0)
    assert 0 < clock.alpha(11.0 + FADE / 2) < 1
    assert clock.done(11.0 + FADE + 0.01)


def test_it_goes_by_itself_after_a_while():
    clock = Clock(0.0, seconds=5)
    assert clock.alpha(4.9) == 1.0
    assert clock.done(5.0 + FADE + 0.01)


@pytest.mark.parametrize(
    "said,ok",
    [
        ("entendido", True),
        ("Ok, gracias", True),
        ("ya lo vi", True),
        ("abre Spotify", False),
        ("entendido, ahora explícame cómo exportar el video en alta calidad", False),
    ],
)
def test_entendido_dismisses(said, ok):
    assert understood(said) is ok


def test_ghost_cursor_walks_the_route_and_presses_on_each_mark():
    points = [(100.0, 100.0), (400.0, 300.0)]
    start = (0.0, 0.0)
    assert cursor_at(points, start, 0.0)[:2] == (0.0, 0.0)
    x, y, press = cursor_at(points, start, STEP * 0.85)
    assert abs(x - 100) < 1 and abs(y - 100) < 1 and press > 0.9
    x, y, _ = cursor_at(points, start, STEP * 1.4)
    assert 100 < x < 400  # on its way to the second mark
    assert cursor_at(points, start, 99)[:2] == (400.0, 300.0)


def test_arrow_comes_from_the_roomy_side_and_stays_on_screen():
    tail = arrow_tail(Mark(1800, 60, 40, 20), 1920, 1080)  # top right corner
    assert tail[0] < 1800 and tail[1] > 60
    tail = arrow_tail(Mark(50, 1000), 1920, 1080)  # bottom left corner
    assert tail[0] > 50 and tail[1] < 1000


class _Backend:
    def ui(self):
        return {
            "window": "Editor",
            "windows": [],
            "elements": [
                {"name": "Exportar", "type": "Button", "rect": (100, 40, 180, 70)}
            ],
        }

    def find_elements(self, query):
        return [
            {"name": "Exportar", "type": "Button", "x": 140, "y": 55, "w": 80, "h": 30}
        ]


def test_guide_action_places_marks_with_the_element_size():
    drawn = []
    control = Controller(_Backend())
    control.on_guide = lambda marks, caption: drawn.append((marks, caption))
    control.ui()  # element 1 is known now
    result = control.act(
        {
            "action": "guide",
            "text": "Así se exporta",
            "marks": [
                {"element": 1, "shape": "circle", "text": "Exportar"},
                {"target": "exportar", "shape": "arrow"},
                {"x": 900, "y": 500, "shape": "box"},
            ],
        }
    )
    assert "3 marks" in result
    marks, caption = drawn[0]
    assert caption == "Así se exporta"
    assert marks[0] == {
        "x": 140,
        "y": 55,
        "w": 80,
        "h": 30,
        "shape": "circle",
        "text": "Exportar",
        "depth": True,
    }
    assert (marks[1]["x"], marks[1]["w"]) == (140, 80)
    assert marks[2]["shape"] == "box"


def test_overlay_draws_and_lets_clicks_through():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # Qt runtime libraries missing on this machine
        pytest.skip(str(exc))
    from sergio_escritorio.guia import make_overlay

    app = QApplication.instance() or QApplication([])
    overlay = make_overlay()
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    overlay.show_marks(
        [
            Mark(300, 200, 120, 40, "circle", "Paso uno"),
            Mark(600, 400, 0, 0, "arrow", "Aquí"),
            Mark(700, 500, 80, 30, "box"),
        ],
        "Así se hace",
    )
    overlay.clock.start -= 5  # everything drawn by now
    image = overlay.grab().toImage()
    assert image.pixelColor(300 + 72, 200).alpha() > 0  # the ring around the element
    assert overlay.showing
    overlay.clock.start -= 1
    overlay.clicked()
    assert not overlay.showing
    app.processEvents()

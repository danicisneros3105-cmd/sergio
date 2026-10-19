"""The notch's quick bar (Qt offscreen): small tasks typed in the notch."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qt():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(str(exc))
    return QApplication.instance() or QApplication([])


def make(qt, **kw):
    from sergio_escritorio.notch_bar import NotchBar

    sent: list[str] = []
    bar = NotchBar(on_submit=sent.append, reduced_motion=lambda: True, **kw)
    return bar, sent


def test_enter_sends_the_line_and_closes(qt):
    bar, sent = make(qt)
    bar.open_bar()
    assert bar.isVisible()
    bar.entry.setText("  abre la calculadora ")
    bar.submit()
    assert sent == ["abre la calculadora"]
    assert not bar.isVisible() and bar.entry.text() == ""


def test_empty_enter_only_closes(qt):
    bar, sent = make(qt)
    bar.open_bar()
    bar.submit()
    assert sent == [] and not bar.isVisible()


def test_chip_starts_the_line(qt):
    bar, _ = make(qt)
    bar.open_bar()
    bar.chips[0].click()
    assert bar.entry.text() == "Recuérdame " and bar.entry.cursorPosition() == len(
        "Recuérdame "
    )


def test_toggle_opens_and_closes(qt):
    bar, _ = make(qt)
    bar.toggle()
    assert bar.isVisible()
    bar.toggle()
    assert not bar.isVisible()


def test_talk_and_panel_chips_close_first(qt):
    calls: list[str] = []
    bar, _ = make(
        qt, on_talk=lambda: calls.append("talk"), on_panel=lambda: calls.append("panel")
    )
    for name, expected in (("Hablar", "talk"), ("Centro", "panel")):
        bar.open_bar()
        next(
            b for b in bar.findChildren(type(bar.chips[0])) if b.text() == name
        ).click()
        assert calls[-1] == expected and not bar.isVisible()


def test_animation_ends_with_controls_visible(qt):
    from sergio_escritorio.notch_bar import NotchBar

    bar = NotchBar(on_submit=lambda _t: None, reduced_motion=lambda: False)
    bar.open_bar()
    bar._anim.setCurrentTime(bar._anim.duration())
    bar._after_anim()
    assert bar._grow == pytest.approx(1.0) and not bar.entry.isHidden()

"""The notch's control center (Qt offscreen): tiles, typing, world, guides."""

import os

import httpx
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


def _server(request):
    if request.url.path == "/v1/world/summary":
        return httpx.Response(
            200, json={"earthquakes": ["M5.1 — Ambato"], "launches": ["Falcon 9"]}
        )
    if request.url.path == "/v1/world/goto":
        return httpx.Response(200, json={"label": "Quito", "url": "http://g/#q"})
    if request.url.path == "/v1/ecc/guides":
        return httpx.Response(
            200,
            json={
                "installed": True,
                "guides": [
                    {"name": "video-editing", "kind": "skill", "description": "Edit."}
                ],
            },
        )
    return httpx.Response(404)


def _panel(qt):
    from sergio_escritorio.panel import ControlCenter, PanelActions, Toggle

    state = {"wake": True}
    sent, opened, saved, talked = [], [], [], []
    actions = PanelActions(
        talk=lambda: talked.append(1),
        send=sent.append,
        toggles=[
            Toggle(
                "Escuchar",
                "wave",
                lambda: state["wake"],
                lambda v: state.__setitem__("wake", v),
            ),
        ],
        config={"theme": "Océano", "eyes": True, "cursor_size": 9.0, "voice": ""},
        save_config=lambda cfg: saved.append(dict(cfg)),
        open_url=opened.append,
        server_url="http://sergio.test",
        http=httpx.Client(transport=httpx.MockTransport(_server)),
        status=lambda: "Piensa con Gemini",
    )
    return ControlCenter(actions), state, sent, opened, saved, talked


def _wait(qt, condition):
    import time

    for _ in range(200):
        qt.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def test_tiles_typing_and_talk(qt):
    panel, state, sent, _, _, talked = _panel(qt)
    panel.open()
    assert panel.subtitle.text() == "Piensa con Gemini"
    panel.tiles[0].click()
    assert state["wake"] is False
    panel.entry.setText("  ¿qué hora es?  ")
    panel._send()
    assert sent == ["¿qué hora es?"] and panel.entry.text() == ""
    panel.show_answer("«eco»")  # what was heard is not an answer
    panel.show_answer("Son las tres.")
    assert panel.answer.text() == "Son las tres."
    panel._talk()
    assert talked == [1] and not panel.isVisible()


def test_personalise_saves_live(qt):
    from sergio_escritorio.character import SETTINGS

    panel, *_, saved, _ = _panel(qt)
    swatch = next(b for b in panel.swatch_group.buttons() if b.name == "Rosa")
    swatch.click()
    panel.eyes.click()
    assert saved[-1]["theme"] == "Rosa" and saved[-1]["eyes"] is False
    assert SETTINGS["theme"] == "Rosa"
    panel._save(theme="Océano", eyes=True)


def test_world_tab_loads_and_flies_the_globe(qt):
    panel, _, _, opened, _, _ = _panel(qt)
    panel.show_tab(2)
    _wait(qt, lambda: "USGS" in panel.world_note.text())
    texts = [
        panel.world_list.itemAt(i).widget().text()
        for i in range(panel.world_list.count())
        if panel.world_list.itemAt(i).widget()
    ]
    assert "M5.1 — Ambato" in texts and "Falcon 9" in texts
    panel.place.setText("Quito")
    panel._goto()
    _wait(qt, lambda: opened)
    assert opened == ["http://g/#q"] and "Quito" in panel.world_note.text()


def test_guides_tab_lists_and_uses_a_guide(qt):
    panel, *_ = _panel(qt)
    panel.show_tab(3)
    _wait(
        qt,
        lambda: panel.guide_list.count() and "video" in panel.guide_list.item(0).text(),
    )
    panel._use_guide(panel.guide_list.item(0))
    assert panel.pages.currentIndex() == 0
    assert panel.entry.text() == "Usa la guía video-editing para "

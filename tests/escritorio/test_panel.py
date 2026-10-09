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
    # Muse-style: character, body colour, accessory, name, personality, brain
    panel.style_seg.buttons["muse"].click()
    assert SETTINGS["style"] == "muse" and saved[-1]["mouth"] == "sonrisa"
    assert panel.colour_stack.currentIndex() == 1
    next(b for b in panel.body_group.buttons() if b.toolTip() == "Cielo").click()
    next(b for b in panel.chip_group.buttons() if b.key == "laurel").click()
    panel.persona.setCurrentText("Divertido")
    panel.brain.buttons["profundo"].click()
    last = saved[-1]
    assert last["body"] == "#a8d8ff" and last["accessory"] == "laurel"
    assert panel.title.text() == "Sergio"  # his name is fixed
    assert last["personality"] == "Divertido" and last["effort"] == "profundo"
    panel.set_level(0.9)
    assert panel.mic.level > 0
    panel._save(
        theme="Océano",
        eyes=True,
        style="orbe",
        mouth="ninguna",
        accessory="ninguno",
        name="Sergio",
    )


def test_world_tab_loads_and_flies_the_globe(qt):
    panel, _, _, opened, _, _ = _panel(qt)
    panel.show_tab(panel.WORLD)
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
    panel.show_tab(panel.GUIDES)
    _wait(
        qt,
        lambda: (
            panel.guide_list.count()
            and "video" in panel.guide_list.item(0).text().lower()
        ),
    )
    panel._use_guide(panel.guide_list.item(0))
    assert panel.pages.currentIndex() == 0
    assert panel.entry.text() == "Usa la guía video-editing para "


def test_every_part_of_sergio_is_one_tap_away_and_in_the_users_language(qt):
    from sergio_escritorio.panel import (
        SECTION_ICONS,
        ControlCenter,
        PanelActions,
        SectionTile,
    )

    opened = []
    panel = ControlCenter(
        PanelActions(
            config={"language": "en"},
            open_section=lambda k, a="": opened.append((k, a)),
        )
    )
    labels = [panel.tab_group.button(i).text() for i in range(len(panel.TABS))]
    assert labels == ["Home", "All", "Sergio", "World", "Guides", "Settings"]
    tiles = panel.pages.widget(1).widget().findChildren(SectionTile)
    assert [t.key for t in tiles] == list(SECTION_ICONS) and len(tiles) >= 18
    next(t for t in tiles if t.key == "organizer").click()
    assert opened == [("organizer", "")]
    next(
        t for t in tiles if t.key == "cams"
    ).click()  # needs a place: goes to the World tab
    assert panel.pages.currentIndex() == panel.WORLD and len(opened) == 1
    panel.cam_place.setText("London")
    panel._cams()
    assert opened[-1] == ("cams", "London")


def test_settings_change_language_and_country(qt):
    from sergio_escritorio.panel import ControlCenter, PanelActions

    saved = []
    panel = ControlCenter(
        PanelActions(
            config={"language": "es", "country": "EC"}, save_config=saved.append
        )
    )
    assert not hasattr(panel, "crisis_note")  # no emergency numbers on screen
    panel.country_box.setCurrentIndex(panel.country_box.findData("MX"))
    assert saved[-1]["country"] == "MX"
    panel.language_box.setCurrentIndex(panel.language_box.findData("pt"))
    assert saved[-1]["language"] == "pt"

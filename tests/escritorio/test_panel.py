"""The notch's control center (Qt offscreen): its six sections."""

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


COWORK_RUNS = [
    {
        "id": "r1",
        "goal": "Comparar portátiles",
        "title": "Portátiles para Blender",
        "status": "waiting",
        "progress": 0.5,
        "waiting": [1],
        "steps": [{"text": "Buscar"}, {"text": "Comprar el mejor"}],
    }
]
CALLS = []


def _server(request):
    CALLS.append((request.method, request.url.path, request.content))
    if request.url.path == "/v1/cowork":
        return httpx.Response(200, json={"runs": COWORK_RUNS, "id": "r1"})
    if request.url.path == "/v1/cowork/r1/decision":
        return httpx.Response(200, json={"ok": True})
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
        open_section=lambda key, arg="": opened.append(("section", key)),
        swarm=lambda: ["Buscar precios · 40%"],
        multitasking=lambda: state.get("multi", False),
        set_multitasking=lambda on: state.__setitem__("multi", on),
        hide_notch=lambda: state.__setitem__("hidden", True),
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
    panel.tiles[0].click()  # the switches live in Configuration now
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
    assert panel.title.text() == "SERGIO"  # his name is fixed (spaced capitals)
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


def test_only_the_six_sections_in_the_users_language(qt):
    from sergio_escritorio.panel import ControlCenter, PanelActions

    panel = ControlCenter(PanelActions(config={"language": "en"}))
    labels = [panel.tab_group.button(i).text() for i in range(len(panel.TABS))]
    assert labels == ["Chat", "Cowork", "Agent Swarm", "Health", "Profile", "Settings"]
    es = ControlCenter(PanelActions(config={"language": "es"}))
    labels = [es.tab_group.button(i).text() for i in range(len(es.TABS))]
    assert labels == ["Chat", "Cowork", "Enjambre", "Salud", "Perfil", "Configuración"]
    assert not hasattr(es, "world_list") and not hasattr(es, "guide_list")  # gone


def test_cowork_starts_and_approves(qt):
    panel, *_ = _panel(qt)
    CALLS.clear()
    panel.show_tab(panel.COWORK)
    _wait(qt, lambda: panel.run_list.count() == 1)
    assert "Comprar el mejor" in panel.waiting.text() and panel.approve.isVisibleTo(
        panel
    )
    panel.goal.setText("Ordena mis descargas")
    panel._start_cowork()
    _wait(qt, lambda: any(m == "POST" and path == "/v1/cowork" for m, path, _ in CALLS))
    assert b"Ordena mis descargas" in next(c for m, path, c in CALLS if m == "POST")
    panel._decide(True)
    _wait(qt, lambda: any(path.endswith("/decision") for _, path, _ in CALLS))
    body = next(c for _, path, c in CALLS if path.endswith("/decision"))
    assert b'"step":2' in body.replace(b" ", b"") and b"true" in body


def test_swarm_health_profile_and_notch(qt):
    panel, state, sent, opened, *_ = _panel(qt)
    panel.open()
    panel.show_tab(panel.SWARM)
    assert panel.swarm_list.item(0).text() == "Buscar precios · 40%"
    panel.swarm_entry.setText("busca el precio de 40 productos")
    panel._launch_swarm()
    assert sent[-1] == "en segundo plano, busca el precio de 40 productos"
    health = panel.pages.widget(panel.HEALTH)
    tiles = [
        w for w in health.findChildren(object) if type(w).__name__ == "SectionTile"
    ]
    assert [t.key for t in tiles] == list(panel.HEALTH_SECTIONS)
    tiles[0].click()
    assert opened[-1] == ("section", "health") and not panel.isVisible()
    panel.multi_switch.click()
    assert state["multi"] is True
    from PySide6.QtWidgets import QPushButton
    from sergio_escritorio import idioma

    label = idioma.t("hide_notch", panel.lang)
    hide = next(b for b in panel.findChildren(QPushButton) if b.text() == label)
    hide.click()
    assert state["hidden"] is True


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

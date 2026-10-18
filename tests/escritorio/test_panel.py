"""The notch's control center (Qt offscreen): its seven sections."""

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
NODES = [
    {
        "id": "n_000000000001",
        "name": "Ana",
        "status": "working",
        "doing": "Busca en la web: pisos",
        "approvals": [],
    },
    {
        "id": "n_000000000002",
        "name": "Leo",
        "status": "needs_you",
        "waiting": "Inicie sesión",
        "approvals": [],
    },
]
SWARMS = [
    {
        "id": "sw_1",
        "title": "Contratos",
        "status": "running",
        "counts": {"done": 3},
        "subtasks": [{}] * 10,
    }
]


def _server(request):
    CALLS.append((request.method, request.url.path, request.content))
    if request.url.path == "/v1/cowork":
        return httpx.Response(200, json={"runs": COWORK_RUNS, "id": "r1"})
    if request.url.path == "/v1/cowork/r1/decision":
        return httpx.Response(200, json={"ok": True})
    if request.url.path == "/v1/nodes":
        return httpx.Response(200, json={"nodes": NODES})
    if request.url.path == "/v1/nodes/n_000000000001/messages":
        return httpx.Response(200, json={"message": {"id": "m"}})
    if request.url.path == "/v1/swarm" and request.method == "POST":
        return httpx.Response(200, json={"id": "sw_1"})
    if request.url.path == "/v1/swarm":
        return httpx.Response(200, json={"runs": SWARMS})
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
    panel, state, sent, opened, _, talked = _panel(qt)
    panel.open()
    assert panel.subtitle.text() == "Piensa con Gemini"
    panel.open_app_button.click()
    assert opened[-1] == "http://sergio.test" and not panel.isVisible()
    panel.open()
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


def test_sergio_is_not_personalised_only_agents_are(qt):
    panel, *_, saved, _ = _panel(qt)
    # No look, colour, accessory or personality pickers any more (the voice
    # is still chosen in Settings: which voice reads, not who Sergio is).
    for gone in (
        "swatch_group",
        "style_seg",
        "body_group",
        "chip_group",
        "persona",
        "size_seg",
    ):
        assert not hasattr(panel, gone), gone
    assert panel.title.text() == "SERGIO"  # his name is fixed (spaced capitals)
    # The brain's effort is still chosen in the chat.
    panel.brain.buttons["profundo"].click()
    assert saved[-1]["effort"] == "profundo"
    panel.set_level(0.9)
    assert panel.mic.level > 0
    # Nodes are what you personalise (like OpenAI's Dots): «Nuevo Node».
    opened: list[str] = []
    panel.actions.open_url = opened.append
    panel._new_node()
    assert opened == [f"{panel.actions.server_url.rstrip('/')}/nodes?nuevo=1"]


def test_tabs_are_icons_that_answer_the_cursor(qt):
    from sergio_escritorio.panel import TabIcon

    panel, *_ = _panel(qt)
    icons = [panel.tab_group.button(i) for i in range(len(panel.TABS))]
    assert all(isinstance(b, TabIcon) for b in icons)
    assert [b.kind for b in icons] == [
        "bubble",
        "dots",
        "swarm",
        "briefcase",
        "heart",
        "person",
        "gear",
    ]
    tab = icons[2]
    tab._go(1.0)
    tab._anim.setCurrentTime(tab._anim.duration())
    assert tab.hover == 1.0  # risen, with its name showing
    tab.grab()  # paints without errors, hovered
    panel._tab_tip(tab, True)
    assert (
        panel.tab_tip.isVisibleTo(panel) and panel.tab_tip.text() == tab.label.upper()
    )
    panel._tab_tip(tab, False)
    tab._go(0.0)
    tab._anim.setCurrentTime(tab._anim.duration())
    assert tab.hover == 0.0
    tab.click()
    assert panel.pages.currentIndex() == 2


def test_only_the_six_sections_in_the_users_language(qt):
    from sergio_escritorio.panel import ControlCenter, PanelActions

    panel = ControlCenter(PanelActions(config={"language": "en"}))
    labels = [panel.tab_group.button(i).text() for i in range(len(panel.TABS))]
    assert labels == [
        "Chat",
        "Nodes",
        "Agent Swarm",
        "Cowork",
        "Health",
        "Profile",
        "Settings",
    ]
    es = ControlCenter(PanelActions(config={"language": "es"}))
    labels = [es.tab_group.button(i).text() for i in range(len(es.TABS))]
    assert labels == [
        "Chat",
        "Nodes",
        "Agent Swarm",
        "Cowork",
        "Salud",
        "Perfil",
        "Configuración",
    ]
    assert not hasattr(es, "world_list") and not hasattr(es, "guide_list")  # gone


def test_custom_voice_id_is_saved_and_survives_reopening(qt):
    from sergio_escritorio.panel import ControlCenter

    panel, _, _, _, saved, _ = _panel(qt)
    panel.custom_voice.setText("authorizedVoice123")
    panel._set_custom_voice()
    assert saved[-1]["voice"] == "elevenlabs:authorizedVoice123"
    reopened = ControlCenter(panel.actions)
    assert reopened.voice.currentData() == "elevenlabs:authorizedVoice123"
    reopened.custom_voice.setText("../../other")
    reopened._set_custom_voice()
    assert reopened.actions.config["voice"] == "elevenlabs:authorizedVoice123"


def test_cowork_and_swarm_show_observed_step_results(qt):
    panel, *_ = _panel(qt)
    panel._show_cowork(
        {
            "runs": [
                {
                    "id": "r1",
                    "goal": "Revisar",
                    "steps": [
                        {
                            "text": "Ejecutar tests",
                            "status": "done",
                            "result": "12 passed",
                        }
                    ],
                    "waiting": [],
                }
            ]
        }
    )
    assert "12 passed" in panel.cowork_output.toPlainText()
    cancelled = []
    panel.actions.swarm_details = lambda: [
        {
            "id": 7,
            "title": "Auditor",
            "state": "running",
            "progress": 0.5,
            "steps": [
                {
                    "text": "Tests",
                    "status": "done",
                    "where": "fondo",
                    "result": "14 passed",
                }
            ],
        }
    ]
    panel.actions.swarm_cancel = lambda tid: cancelled.append(tid) or True
    panel.open()
    panel.show_tab(panel.SWARM)
    assert "50%" in panel.swarm_list.item(0).text()
    assert "14 passed" in panel.swarm_output.toPlainText()
    panel._cancel_swarm()
    assert cancelled == [7]


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


def test_nodes_tab_lists_and_sends_errands(qt):
    panel, state, sent, opened, *_ = _panel(qt)
    panel.open()
    CALLS.clear()
    panel.show_tab(panel.NODES)
    _wait(qt, lambda: panel.node_list.count() == 2)
    assert panel.node_list.item(0).text() == "Ana\nBusca en la web: pisos"
    assert panel.node_list.item(1).text().startswith("Leo  ●\nInicie sesión")
    panel.node_list.setCurrentRow(0)
    panel.node_entry.setText("Resume mi correo")
    panel._send_node()
    _wait(qt, lambda: any(path.endswith("/messages") for _, path, _ in CALLS))
    assert b"Resume mi correo" in next(
        c for _, path, c in CALLS if path.endswith("/messages")
    )
    panel.node_list.setCurrentRow(0)
    panel._open_node()
    assert (
        opened[-1] == "http://sergio.test/nodes/n_000000000001"
        and not panel.isVisible()
    )


def test_swarm_health_profile_and_notch(qt):
    panel, state, sent, opened, *_ = _panel(qt)
    panel.open()
    CALLS.clear()
    panel.show_tab(panel.SWARM)
    _wait(qt, lambda: panel.swarm_list.count() == 2)
    from sergio_escritorio import idioma as _i

    assert (
        panel.swarm_list.item(0).text()
        == f"Contratos\n3/10 · {_i.t('swarm_running', panel.lang)}"
    )
    assert panel.swarm_list.item(1).text() == "Buscar precios · 40%"
    panel.swarm_entry.setText("busca el precio de 40 productos")
    panel._launch_swarm()
    _wait(qt, lambda: any(m == "POST" and path == "/v1/swarm" for m, path, _ in CALLS))
    assert b"busca+el+precio" in next(
        c for m, path, c in CALLS if m == "POST" and path == "/v1/swarm"
    )
    _wait(qt, lambda: "http://sergio.test/swarm/sw_1" in opened)
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

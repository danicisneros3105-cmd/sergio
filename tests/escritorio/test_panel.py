"""The notch's control center (Qt offscreen): quick buttons first, every page one step away."""

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


def test_home_shows_only_quick_buttons_and_whats_running(qt):
    # Owner, 26 Oct 2026: only Multitasking / Split Screen, undo Sergio's last
    # action, Usage, Model / Effort, Display (and skills), plus what is running.
    panel, state, *_ = _panel(qt)
    undone = []
    panel.actions.undo_label = lambda: "Abrí Spotify"
    panel.actions.undo = lambda: undone.append(1) or "Cerré Spotify"
    split = []
    panel.actions.split_screen = lambda on: split.append(on) or True
    panel.open()
    assert panel.pages.currentIndex() == panel.HOME
    assert not panel.back_bar.isVisibleTo(panel)
    # Owner, 29 Oct 2026: «más simple y con menos cosas»: four tiles; Usage
    # and Skills one step inside «Pantalla».
    assert [t.kind for t in panel.quick_tiles] == [
        "split",
        "undo",
        "sparkles",
        "monitor",
    ]
    assert panel.undo_tile.sub == "Abrí Spotify" and panel.undo_tile.isEnabled()
    panel.undo_tile.click()
    _wait(qt, lambda: undone == [1] and panel.undo_tile.sub == "Cerré Spotify")
    panel.multi_tile.click()  # the island and the open window split together
    _wait(qt, lambda: split == [True])
    assert state["multi"] is True
    for tile in panel.quick_tiles:
        tile.grab()  # paints without errors
    # What is running: the server's rows and this PC's tasks, each with a stop.
    panel._show_home(
        {
            "running": [
                {
                    "quien": "Rihno",
                    "que": "Investiga precios",
                    "detener": "/v1/nodes/n1/cancel",
                },
            ]
        }
    )
    texts = [
        panel.running_box.itemAt(i)
        .widget()
        .findChildren(type(panel.title))[-1]
        .toolTip()
        for i in range(panel.running_box.count())
    ]
    assert texts[0] == "Rihno · Investiga precios"
    assert any("Buscar precios" in t for t in texts)  # this PC's task line


def test_sheets_model_skills_display_and_back(qt):
    import json

    calls = []

    def server(request):
        calls.append((request.method, request.url.path, request.content))
        if request.url.path == "/v1/personal/modelos":
            return httpx.Response(
                200,
                json={
                    "modelos": [
                        {
                            "id": "gemini-3.6-flash",
                            "nombre": "Gemini 3.6 Flash",
                            "para": "Rápido",
                            "disponible": True,
                        },
                        {
                            "id": "gemini-2.5-pro",
                            "nombre": "Gemini 2.5 Pro",
                            "para": "",
                            "disponible": False,
                        },
                    ]
                },
            )
        if request.url.path.startswith("/v1/personal/habilidades"):
            on = b"true" in (request.content or b"true")
            return httpx.Response(
                200,
                json={
                    "habilidades": [
                        {
                            "clave": "imagenes",
                            "nombre": "Imágenes",
                            "hace": "",
                            "activa": on,
                        }
                    ]
                },
            )
        return httpx.Response(404)

    panel, *_, saved, _ = _panel(qt)
    panel.actions.http = httpx.Client(transport=httpx.MockTransport(server))
    panel.model_tile.click()
    assert panel.pages.currentIndex() == panel.MODEL_SHEET
    assert panel.back_bar.isVisibleTo(panel)
    _wait(qt, lambda: panel.model_list.count() == 3)
    unavailable = panel.model_list.item(2)
    from PySide6.QtCore import Qt

    assert not unavailable.flags() & Qt.ItemFlag.ItemIsEnabled
    panel._pick_model(panel.model_list.item(1))
    assert saved[-1]["model"] == "gemini-3.6-flash"
    assert panel.model_tile.sub.startswith("Gemini 3.6 Flash")
    panel.show_tab(panel.SKILLS_SHEET)
    _wait(qt, lambda: panel.skills_box.count() == 1)
    panel._switch_skill("imagenes", False)
    _wait(qt, lambda: any(m == "PUT" for m, *_ in calls))
    put = next(c for m, path, c in calls if m == "PUT")
    assert json.loads(put) == {"activa": False}
    panel.display_tile.click()
    assert panel.pages.currentIndex() == panel.DISPLAY_SHEET
    panel.back_bar.findChildren(type(panel.open_app_button))[0].click()
    assert panel.pages.currentIndex() == panel.HOME


def test_page_titles_in_the_users_language(qt):
    from sergio_escritorio.panel import ControlCenter, PanelActions

    panel = ControlCenter(PanelActions(config={"language": "en"}))
    names = [
        panel.page_name(i) for i in range(panel.DISPLAY_SHEET + 1) if i != panel.HOME
    ]
    assert names == [
        "Chat", "Nodes", "Agent Swarm", "Cowork", "Health", "Profile", "Settings",
        "Model", "Skills", "Display",
    ]  # fmt: skip
    es = ControlCenter(PanelActions(config={"language": "es"}))
    es.show_tab(es.HEALTH)
    assert es.page_title.text() == "Salud"
    assert es.multi_tile.title == "Multitarea" and es.undo_tile.title == "Deshacer"
    assert not hasattr(es, "tab_group")  # no tab bar any more
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
    panel.show_tab(panel.HOME)
    panel.multi_tile.click()
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


def test_every_page_is_reachable_and_settings_has_how_to_address_you(qt):
    panel, *_ = _panel(qt)
    for index in range(panel.DISPLAY_SHEET + 1):
        panel.show_tab(index)
        assert panel.pages.currentIndex() == index
    panel.settings_button.click()
    assert panel.pages.currentIndex() == panel.SETTINGS_TAB
    keys = [panel.address_box.itemData(i) for i in range(panel.address_box.count())]
    assert keys == ["señor", "señora", "nombre", "neutro", "tu"]

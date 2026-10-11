"""The laptop by voice, at once: windows, keys, brightness, theme, settings."""

import pytest
from sergio_escritorio.device import parse_device, run_device
from sergio_escritorio.quick import parse_quick


@pytest.mark.parametrize(
    ("said", "arg"),
    [
        ("maximiza la ventana", "win+up"),
        ("cierra esta ventana", "alt+f4"),
        ("cambia de ventana", "alt+tab"),
        ("copia eso", "ctrl+c"),
        ("guárdalo", "ctrl+s"),
        ("nueva pestaña", "ctrl+t"),
        ("pon el brillo al 70", "70"),
        ("Sergio, ¿puedes bajar el brillo?", "$c-20"),
        ("sube el brillo", "$c+20"),
        ("activa el modo oscuro", "0"),
        ("pon el volumen a la mitad", "50"),
        ("abre la configuración del wifi", "ms-settings:network-wifi"),
        ("abre la carpeta de descargas", "shell:Downloads"),
        ("escribe: Hola, ¿cómo estás?", "Hola, ¿cómo estás?"),
    ],
)
def test_device_orders(said, arg):
    q = parse_quick(said)
    assert q is not None and q.kind == "device" and q.arg == arg


def test_composing_goes_to_the_ai_and_apps_still_open():
    assert parse_quick("escribe un correo para mi jefe") is None
    assert parse_quick("cierra chrome").kind == "close_app"
    assert parse_quick("abre el bloc de notas").say == "Abriendo Bloc de notas."


def test_run_device_steps():
    done = []

    def act(a):
        done.append(a)
        if a["action"] == "terminal":
            return "exit code 0\noutput:\n70\nerrors:\n"
        return "ok"

    assert run_device(parse_device("pon el brillo al 70"), act) == "Brillo al 70%."
    assert "WmiSetBrightness" in done[-1]["command"]
    done.clear()
    run_device(parse_device("pon el volumen al 30"), act)
    assert [(a["keys"], a["repeat"]) for a in done] == [
        ("volumedown", 50),
        ("volumeup", 15),
    ]
    done.clear()
    run_device(parse_device("activa el modo oscuro"), act)
    assert "AppsUseLightTheme -Value 0" in done[-1]["command"]
    failing = lambda a: "exit code 1\noutput:\n\nerrors:\nnot supported"  # noqa: E731
    assert "no deja cambiar el brillo" in run_device(
        parse_device("sube el brillo"), failing
    )


def test_call_tool_runs_spoken_orders():
    from sergio_escritorio.call_tools import Abilities, call_tools

    said = []
    tools = {
        t.name: t
        for t in call_tools(Abilities(quick=lambda text: said.append(text) or "Hecho."))
    }
    assert tools["control_equipo"].run({"orden": "maximiza la ventana"}) == "Hecho."
    assert said == ["maximiza la ventana"]


def test_repeated_keys_are_one_quick_action(desktop):
    from sergio_escritorio.control import Controller

    slept = []
    c = Controller(desktop, sleep=slept.append, approve=lambda _: True)
    assert (
        c.act({"action": "key", "keys": "volumedown", "repeat": 50})
        == "pressed volumedown x50"
    )
    assert sum(1 for call in desktop.calls if call[0] == "hotkey") == 50
    assert slept == []  # no window check after each press


def test_described_videos_go_to_the_video_finder():
    from sergio_escritorio.call_tools import Abilities, call_tools

    q = parse_quick("Sergio, pon un video de MrBeast en el que salga con traje negro")
    assert q.kind == "video" and "traje negro" in q.arg
    asked = []
    tools = {
        t.name: t
        for t in call_tools(
            Abilities(video=lambda r: asked.append(r) or "Reproduciendo «X».")
        )
    }
    assert (
        tools["poner_video"].run({"peticion": "MrBeast con traje negro"})
        == "Reproduciendo «X»."
    )
    assert asked == ["MrBeast con traje negro"]


@pytest.mark.parametrize(
    "said,kind,arg",
    [
        ("haz clic en Suscribirse", "click", "left:Suscribirse"),
        ("Sergio, pulsa el botón Enviar", "click", "left:Enviar"),
        ("dale a Aceptar", "click", "left:Aceptar"),
        ("haz doble clic en Documentos", "click", "double:Documentos"),
        ("clic derecho en la papelera", "click", "right:papelera"),
        ("presiona enter", "key", "enter*1"),
        ("dale tab dos veces", "key", "tab*2"),
        ("flecha abajo 3 veces", None, None),
        ("pulsa la tecla escape", "key", "esc*1"),
        ("baja", "scroll", "-6"),
        ("sube un poco", "scroll", "6"),
        ("atrás", "key", "alt+left"),
        ("siguiente pestaña", "key", "ctrl+tab"),
        ("cambia a Chrome", "focus", "chrome"),
        ("trae spotify al frente", "focus", "spotify"),
        ("escribe hola mundo y dale enter", "type", "hola mundo\n"),
    ],
)
def test_instant_screen_orders(said, kind, arg):
    q = parse_quick(said)
    if kind is None:
        assert q is None or q.kind != "device" or q.step.kind != "click"
        return
    assert q is not None and q.kind == "device"
    assert (q.step.kind, q.step.arg) == (kind, arg)


def test_screen_orders_do_not_steal_other_commands():
    assert parse_quick("sube el volumen").kind == "volume"
    assert parse_quick("dale, abre spotify").kind == "open_app"
    assert parse_quick("selecciona todo").step.arg == "ctrl+a"
    assert parse_quick("abre youtube").kind == "open_url"


def test_click_by_name_finds_the_right_element():
    from sergio_escritorio.control import best_element

    els = [
        {"name": "Suscripciones", "type": "Hyperlink", "x": 2, "y": 2},
        {"name": "Suscribirse", "type": "Button", "x": 1, "y": 1},
        {
            "name": "Me gusta este video junto con 3 mil personas",
            "type": "Button",
            "x": 3,
            "y": 3,
        },
        {"name": "Enviar comentario", "type": "Button", "x": 5, "y": 5},
        {"name": "Enviar", "type": "Button", "x": 4, "y": 4},
    ]
    assert best_element("suscribirse", els)["x"] == 1
    assert best_element("subscribirse", els)["x"] == 1  # misheard spelling
    assert best_element("me gusta", els)["x"] == 3
    assert best_element("Enviar", els)["x"] == 4  # exact beats longer names
    assert best_element("configuración", els) is None


def test_click_name_action_and_no_fixed_waits():
    from sergio_escritorio.control import ActionError, Controller

    clicks, slept = [], []

    class B:
        def find_elements(self, query):
            return [{"name": "Aceptar", "type": "Button", "x": 40, "y": 50}]

        def click(self, x, y, button, n):
            clicks.append((x, y, button, n))

        def active_window(self):
            return "Diálogo"

    c = Controller(B(), sleep=slept.append, approve=lambda _: True)
    out = c.act({"action": "click_name", "target": "aceptar", "button": "double"})
    assert clicks == [(40, 50, "left", 2)] and "now in front: Diálogo" in out
    assert slept == []  # a click is checked at once, not after a fixed pause
    with pytest.raises(ActionError, match="No veo"):
        c.act({"action": "click_name", "target": "Cancelar"})


def test_fast_hands_glide_quickly_and_type_at_once():
    from sergio_escritorio.human import WindowsHands, fast_seconds

    assert fast_seconds(10) == 0.05 and fast_seconds(3000) == 0.16
    hands = WindowsHands(sleep=lambda s: None)
    sent = []
    hands._send_text = sent.append
    hands.type_text("hola, ¿qué tal? ñ 👍")
    assert sent == ["hola, ¿qué tal? ñ 👍"]  # one burst, not key by key

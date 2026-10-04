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
    assert [(a["keys"], a["repeat"]) for a in done] == [("volumedown", 50), ("volumeup", 15)]
    done.clear()
    run_device(parse_device("activa el modo oscuro"), act)
    assert "AppsUseLightTheme -Value 0" in done[-1]["command"]
    failing = lambda a: "exit code 1\noutput:\n\nerrors:\nnot supported"  # noqa: E731
    assert "no deja cambiar el brillo" in run_device(parse_device("sube el brillo"), failing)


def test_call_tool_runs_spoken_orders():
    from sergio_escritorio.call_tools import Abilities, call_tools

    said = []
    tools = {t.name: t for t in call_tools(Abilities(quick=lambda text: said.append(text) or "Hecho."))}
    assert tools["control_equipo"].run({"orden": "maximiza la ventana"}) == "Hecho."
    assert said == ["maximiza la ventana"]


def test_repeated_keys_are_one_quick_action(desktop):
    from sergio_escritorio.control import Controller

    slept = []
    c = Controller(desktop, sleep=slept.append)
    assert c.act({"action": "key", "keys": "volumedown", "repeat": 50}) == "pressed volumedown x50"
    assert sum(1 for call in desktop.calls if call[0] == "hotkey") == 50
    assert slept == []  # no window check after each press

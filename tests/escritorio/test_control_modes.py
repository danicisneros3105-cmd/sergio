"""Companion clicks, L99 must-finish mode and the owner checkpoint."""

from __future__ import annotations

from sergio_escritorio import voice
from sergio_escritorio.voice import important, l99_status, l99_task


def test_l99_is_recognised_and_removed():
    assert l99_task("usa L99 y organiza mis descargas") == "y organiza mis descargas"
    assert l99_task("organiza mis descargas, l-99") == "organiza mis descargas"
    assert l99_task("organiza mis descargas") is None
    assert l99_status("Hecho todo.\nTERMINADO: 40 archivos ordenados") == (
        "done",
        "40 archivos ordenados",
    )
    assert l99_status("FALTA: mover los PDF")[0] == "more"
    assert l99_status("NO POSIBLE: no hay internet")[0] == "impossible"
    assert l99_status("sin marca")[0] == "more"


def test_l99_keeps_working_until_done():
    client = voice.SergioClient.__new__(voice.SergioClient)
    replies = iter(
        ["Moví la mitad.\nFALTA: los PDF", "Listo.\nTERMINADO: todo ordenado"]
    )
    asked = []

    def ask(text, force_agent=False):
        asked.append((text, force_agent))
        return next(replies)

    client.ask = ask
    steps = []
    assert client.ask_until_done("ordena descargas", steps.append) == "todo ordenado"
    assert (
        len(asked) == 2
        and all(force for _t, force in asked)
        and "los PDF" in asked[1][0]
    )
    assert steps == ["los PDF"]


def test_important_requests():
    assert (
        important("borra la carpeta de fotos")
        and important("envía el correo")
        and important("instala Steam")
    )
    assert not important("qué hora es") and not important("abre spotify")


def test_controller_lets_the_companion_click_first():
    from sergio_escritorio.control import Controller

    order = []

    class Backend:
        def click(self, x, y, button, clicks):
            order.append(("click", x, y))

    c = Controller.__new__(Controller)
    c.enabled, c.backend = True, Backend()
    c.on_click = lambda x, y, kind: order.append(("companion", x, y))
    c._front = lambda: ""
    c.SETTLE = set()
    c._on_activity = lambda result: None
    c.act({"action": "click", "x": 10, "y": 20})
    assert order[:2] == [("companion", 10, 20), ("click", 10, 20)]

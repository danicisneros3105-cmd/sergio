"""«Deshacer lo último de Sergio» (deshacer.py, recorded by control.py)."""

from sergio_escritorio.deshacer import STALE_S, Journal


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_newest_first_and_said_in_words():
    done = []
    j = Journal(Clock())
    j.add("Abrí Spotify", lambda: done.append("spotify"), "Cerré Spotify.")
    j.add("Escribí un texto", lambda: done.append("ctrl+z"), "Borré lo que escribí.")
    assert j.undo_last() == "Borré lo que escribí."
    assert j.undo_last() == "Cerré Spotify."
    assert done == ["ctrl+z", "spotify"]
    assert j.undo_last() == "No hay nada reciente que deshacer."


def test_too_old_is_not_undone():
    clock = Clock()
    j = Journal(clock)
    j.add("Abrí Spotify", lambda: None, "Cerré Spotify.")
    clock.t += STALE_S + 1
    assert j.last() is None
    assert "nada reciente" in j.undo_last()


def test_a_failed_undo_is_said_not_hidden():
    def boom():
        raise RuntimeError("la ventana ya no existe")

    j = Journal(Clock())
    j.add("Abrí Spotify", boom, "Cerré Spotify.")
    assert j.undo_last() == "No pude deshacer «Abrí Spotify»: la ventana ya no existe"


def test_the_controller_records_what_it_can_take_back():
    from sergio_escritorio.control import Controller
    from sergio_escritorio.deshacer import journal

    class Backend:
        def __init__(self):
            self.calls = []

        def open_app(self, name):
            return f"opened {name}"

        def close_app(self, name):
            self.calls.append(("close", name))
            return [name]

        def hotkey(self, keys):
            self.calls.append(("keys", tuple(keys)))

        def type_text(self, text):
            self.calls.append(("type", text))

        def foreground(self):
            return ""

    b = Backend()
    c = Controller(b, strict_permissions=False)
    c._verify = lambda *_a: ""
    c.act({"action": "open_app", "target": "Spotify"})
    assert journal().last().what == "Abrí Spotify"
    assert journal().undo_last() == "Cerré Spotify."
    assert ("close", "Spotify") in b.calls

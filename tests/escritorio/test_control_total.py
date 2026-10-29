"""Owner, 29 Oct 2026: «le dije que entre a Amazon, inicie sesión y busque
unos productos y me dijo que es un modelo de lenguaje… necesitamos control
total y cualquier tarea; la conversación por voz a veces no se termina; no
puede hacer split screen»."""

import json
import time

from sergio_escritorio import launch
from sergio_escritorio.apps import Launcher, Window
from sergio_escritorio.call import QUIET_TURNS, is_goodbye
from sergio_escritorio.control import Controller, halves, risky, split_targets
from sergio_escritorio.quick import parse_quick

from tests.escritorio.test_call import FakeLine, _call, _wait

# -- split screen: two programs side by side --------------------------------------


def test_two_programs_go_side_by_side_by_voice():
    q = parse_quick("Sergio, pon Chrome y Word lado a lado")
    assert q.kind == "split_apps" and q.arg == "chrome | word"
    assert parse_quick("divide la pantalla entre excel y teams").arg == "excel | teams"
    assert (
        parse_quick("pon spotify con chrome en pantalla dividida").kind == "split_apps"
    )
    # without names it still splits Sergio's own window (and says so)
    alone = parse_quick("divide la pantalla")
    assert alone.kind == "multitask_on" and "pantalla" in alone.say


def test_split_targets_and_the_two_halves():
    assert split_targets("Chrome | Word") == ("Chrome", "Word")
    assert split_targets("chrome y word") == ("chrome", "word")
    assert split_targets("Excel") == ("Excel", "")
    assert split_targets("") == ("", "")
    left, right = halves((0, 0, 1921, 1040))
    assert left == (0, 0, 960, 1040) and right == (960, 0, 961, 1040)
    assert halves((1920, 0, 3840, 1080))[0][0] == 1920  # the second monitor


def test_split_is_an_ordinary_move_that_never_asks(desktop):
    placed = []
    desktop.side_by_side = lambda a, b: placed.append((a, b)) or [a, b]
    asked = []
    c = Controller(
        desktop, sleep=lambda s: None, approve=lambda p: asked.append(p) or True
    )
    assert not risky({"action": "split", "target": "Chrome | Word"})
    assert "split screen: Chrome | Word" in c.act(
        {"action": "split", "target": "Chrome | Word"}
    )
    assert placed == [("Chrome", "Word")] and asked == []


def test_the_launcher_finds_an_open_program_by_its_program_first():
    class Desk:
        def windows(self):
            return [
                Window(1, "cómo usar Word - Google Chrome", "chrome"),
                Window(2, "Documento1 - Word", "winword"),
                Window(3, "Sergio", "msedge"),
            ]

    launcher = Launcher(desktop=Desk(), rescan=lambda: None)
    launcher._scanned = True
    assert launcher.window("word").hwnd == 2
    assert launcher.window("chrome").hwnd == 1
    assert launcher.window("chrome", skip=1) is None
    assert launcher.window("sergio") is None  # never its own window


def test_splitting_with_no_sergio_window_open_opens_one_already_split():
    class No:
        status_code = 503

        def json(self):
            return {}

    opened = []
    assert launch.split_window(True, post=lambda *a, **k: No(), opener=opened.append)
    assert opened and opened[0].endswith("/?dividir=1")
    assert not launch.split_window(
        False, post=lambda *a, **k: No(), opener=opened.append
    )
    assert len(opened) == 1  # joining never opens a window


# -- the voice conversation ends --------------------------------------------------


def test_a_short_goodbye_is_a_goodbye_and_a_sentence_with_the_word_is_not():
    for bye in (
        "gracias, adiós",
        "cuelga",
        "eso es todo",
        "chao Sergio",
        "hasta mañana",
    ):
        assert is_goodbye(bye), bye
    for not_bye in (
        "",
        "busca la canción Adiós de Gustavo Cerati en Spotify y ponla bien alta",
        "abre Chrome",
    ):
        assert not is_goodbye(not_bye), not_bye


def test_saying_goodbye_hangs_up_even_if_the_model_does_not():
    ended = []
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    call = _call(line, on_end=ended.append, idle_hang_up=float("inf"))
    assert call.start()
    line.inbox.put(json.dumps({"type": "heard", "text": "gracias Sergio, adiós"}))
    line.inbox.put(json.dumps({"type": "said", "text": "A sus órdenes, señor."}))
    line.inbox.put(json.dumps({"type": "turn_complete"}))
    assert _wait(lambda: not call.active, 5)
    assert ended == ["te despediste"]


def test_an_always_on_call_ends_after_ten_minutes_without_a_real_exchange():
    now = [100.0]
    ended = []
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    call = _call(
        line, clock=lambda: now[0], idle_hang_up=float("inf"), on_end=ended.append
    )
    assert call.start()
    now[0] += QUIET_TURNS - 5
    time.sleep(0.3)
    assert call.active  # always-on: silence alone never ends it
    now[0] += 10
    assert _wait(lambda: not call.active)
    assert ended == ["sin conversación"]

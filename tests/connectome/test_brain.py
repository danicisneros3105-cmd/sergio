"""The mind's zones learn connections (connectome/brain.py)."""

from __future__ import annotations

from openjarvis.connectome.brain import Brain


class Clock:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


def test_a_past_conversation_comes_back_after_leaving_the_window(tmp_path):
    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    brain.observe(
        "Mi perra se llama Luna y es una golden retriever",
        "Encantado de conocer a Luna. Los golden necesitan mucho ejercicio.",
    )
    clock.t += 3600
    block, used = brain.context("¿qué raza es Luna mi perra?")
    assert "Luna" in block and used
    # The memory survives a restart (it lives on disk, outside any window).
    again = Brain(tmp_path, clock=clock)
    assert again.context("¿cómo se llama mi perra golden?")[0]


def test_using_a_memory_makes_the_next_recall_a_fast_path(tmp_path):
    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    brain.observe(
        "mi proyecto Atlas usa Python y FastAPI", "Entendido: Atlas, Python y FastAPI."
    )
    for _ in range(4):
        clock.t += 60
        q = "proyecto Atlas"
        brain.context(q)
        brain.observe(q, "Atlas va bien.")
    _, fast = brain.recall("proyecto Atlas")
    assert fast
    assert brain.stats()["fast_path"] > 0


def test_a_correction_weakens_what_fed_the_wrong_answer(tmp_path):
    brain = Brain(tmp_path, clock=Clock())
    brain.observe("la reunión es el martes", "Anotado: martes.")
    brain.context("¿cuándo es la reunión?")
    brain.observe("¿cuándo es la reunión?", "El martes.")
    before = sum(w for row in brain.syn.values() for w in row.values())
    brain.observe("no, eso no, es el jueves", "Corregido: jueves.")
    after = sum(w for row in brain.syn.values() for w in row.values())
    assert brain.stats()["corrections"] == 1
    assert after < before + 3  # the old links lost strength (new ones were added)


def test_secrets_never_become_memories(tmp_path):
    brain = Brain(tmp_path, clock=Clock())
    assert brain.observe("mi clave es sk-abcdefghijklmnop1234", "Guardada") is None
    assert brain.observe("contraseña: hunter2 para el correo", "Ok") is None
    assert brain.stats()["engrams"] == 0


def test_it_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("SERGIO_CEREBRO", "0")
    brain = Brain(tmp_path, clock=Clock())
    assert brain.observe("algo que recordar", "vale") is None
    assert brain.context("algo que recordar") == ("", [])


def _turn(brain, clock, text, answer, *, tools=(), skills=(), channel="chat"):
    clock.t += 60
    brain.context(text, channel)
    brain.note_skills(skills)
    for name, ok in tools:
        brain.note_tool(name, ok)
    return brain.observe(text, answer)


def test_tools_that_worked_become_a_learned_route(tmp_path):
    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    for _ in range(3):
        _turn(
            brain,
            clock,
            "precio del bitcoin hoy",
            "81.000 USD según Coinbase.",
            tools=[("web_search", True), ("http_request", False)],
        )
    block, _ = brain.context("¿a cuánto está el bitcoin?")
    assert "<cerebro_rutas>" in block and "web_search" in block
    assert "http_request" in block.split("Fallaron a menudo:")[1]
    zones = {z["key"]: z for z in brain.stats()["zones"]}
    assert zones["herramientas"]["connections"] > 0
    assert zones["herramientas"]["top"][0]["name"] == "web_search"


def test_skills_and_channels_get_real_connections(tmp_path):
    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    _turn(
        brain,
        clock,
        "escribe un correo formal al banco",
        "Listo.",
        skills=["Redactor formal"],
    )
    _turn(brain, clock, "pon música para estudiar", "Puesta.", channel="voz")
    zones = {z["key"]: z for z in brain.stats()["zones"]}
    assert [t["name"] for t in zones["habilidades"]["top"]] == ["Redactor formal"]
    assert {t["name"] for t in zones["sentidos"]["top"]} == {"chat", "voz"}


def test_the_thread_links_each_memory_to_the_next(tmp_path):
    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    first = _turn(brain, clock, "planeo un viaje a Cusco en julio", "Buena idea.")
    second = _turn(
        brain, clock, "reserva el hotel cerca de la plaza de armas", "Busco hoteles."
    )
    assert f"conversacion:{second}" in brain.assoc[f"memoria:{first}"]
    ids, _ = brain.recall("viaje a Cusco en julio")
    assert ids[:2] == [first, second]  # the thread comes back with it
    clock.t += 3 * 3600  # a long silence starts a new thread
    third = _turn(brain, clock, "receta de ceviche", "Limón y pescado.")
    assert f"conversacion:{third}" not in brain.assoc.get(f"memoria:{second}", {})


def test_tools_from_another_thread_or_outside_a_turn_are_ignored(tmp_path):
    import threading

    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    brain.note_tool("web_search", True)  # no turn on this thread
    brain.context("busca vuelos baratos")
    t = threading.Thread(target=brain.note_tool, args=("python_run", True))
    t.start()
    t.join()
    brain.note_tool("web_search", True)
    brain.observe("busca vuelos baratos", "Encontré tres.")
    learned = {
        i for row in brain.syn.values() for i in row if i.startswith("herramientas:")
    }
    assert learned == {"herramientas:web_search"}


def test_changes_are_saved_incrementally_and_survive_a_restart(tmp_path):
    import sqlite3

    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    eid = _turn(
        brain,
        clock,
        "mi color favorito es el azul",
        "Azul, anotado.",
        tools=[("think", True)],
    )
    again = Brain(tmp_path, clock=clock)
    assert again.engrams[eid]["user"].startswith("mi color favorito")
    assert again.syn == brain.syn and again.assoc == brain.assoc
    with sqlite3.connect(tmp_path / "cerebro.db") as db:
        assert db.execute("SELECT count(*) FROM engrams").fetchone()[0] == 1


def test_the_old_json_mind_is_migrated_once(tmp_path):
    import json

    (tmp_path / "cerebro.json").write_text(
        json.dumps(
            {
                "syn": {"5": {"memoria:abc": 0.4}},
                "assoc": {},
                "zone_w": {"memoria": 1.2},
                "engrams": {
                    "abc": {"t": 1, "cells": [5], "user": "hola Luna", "gist": "Hola"}
                },
                "stats": {"turns": 7},
                "decayed": 1_800_000_000.0,
            }
        ),
        encoding="utf-8",
    )
    brain = Brain(tmp_path, clock=Clock())
    assert (
        brain.engrams["abc"]["user"] == "hola Luna" and brain.zone_w["memoria"] == 1.2
    )
    assert not (tmp_path / "cerebro.json").exists()
    assert Brain(tmp_path, clock=Clock()).syn == {"5": {"memoria:abc": 0.4}}


def test_a_big_mind_still_answers_fast(tmp_path):
    import time as _time

    clock = Clock()
    brain = Brain(tmp_path, clock=clock)
    for i in range(1500):
        clock.t += 1
        brain.observe(
            f"nota {i} sobre el proyecto {i % 97} y el cliente {i % 53}", f"ok {i}"
        )
    start = _time.perf_counter()
    for i in range(50):
        clock.t += 1
        brain.context(f"proyecto {i % 97} cliente {i % 53}")
        brain.observe(f"proyecto {i % 97} cliente {i % 53}", "ok")
    per_turn = (_time.perf_counter() - start) / 50
    assert per_turn < 0.1, per_turn  # incremental writes keep a turn to milliseconds

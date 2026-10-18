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

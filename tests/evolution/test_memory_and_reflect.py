"""Long-term memory (chromadb + local embeddings) and the self-correction loop."""

from __future__ import annotations

import sys

import pytest

from openjarvis.evolution import memory as mem
from openjarvis.evolution.reflect import self_correct


@pytest.fixture()
def memory(tmp_path):
    return mem.LongTermMemory(tmp_path, use_gemini=False)


def test_it_remembers_and_recalls_the_closest_memory(memory):
    memory.remember("blender", "una tetera de cerámica: cuerpo facetado, se arregló con perfiles suaves")
    memory.remember("blender", "una mesa de roble: patas flotando por transform_apply")
    memory.remember("video", "short de viajes: 22 cortes de un segundo")
    top = memory.recall("haz una tetera de porcelana", 1)[0]
    assert "tetera" in top["text"] and top["kind"] == "blender"
    assert memory.recall("algo", 5, kinds=("video",))[0]["kind"] == "video"
    assert memory.stats()["memories"] == 3


def test_feedback_becomes_a_lesson_for_similar_jobs(memory):
    memory.feedback("el video quedó muy lento, quiero cortes más rápidos", -1, about="short de viajes")
    block = memory.lessons_for("edita un video de viajes con cortes", kinds=("feedback",))
    assert "NO LE GUSTÓ" in block and "cortes más rápidos" in block and "LESSONS FROM YOUR LONG-TERM MEMORY" in block
    assert memory.lessons_for("receta de cocina vegana", kinds=("feedback",)) == ""  # unrelated: nothing


def test_semantic_embeddings_are_used_when_given(tmp_path):
    def embed(texts):  # a fake "semantic" model: tea things close together
        return [[1.0, 0.0] if ("tetera" in t or "té" in t) else [0.0, 1.0] for t in texts]

    m = mem.LongTermMemory(tmp_path, semantic=embed)
    m.remember("blender", "una tetera de cerámica")
    m.remember("blender", "una mesa")
    hit = m.recall("servicio de té", 1)[0]
    assert hit["space"] == "semantic" and "tetera" in hit["text"]


def test_local_embeddings_ignore_filler_words():
    a, b = mem.hash_embed("una tetera de cerámica"), mem.hash_embed("una mesa de madera")
    assert sum(x * y for x, y in zip(a, b)) < 0.2


def test_the_loop_reflects_until_the_check_passes_and_stores_the_fix():
    notes_seen, lessons = [], []

    def generate(task, notes):
        notes_seen.append(list(notes))
        return len(notes_seen)

    out = self_correct("tarea", generate, lambda c: (c >= 3, f"intento {c} incompleto"), max_rounds=5,
                       remember=lessons.append, topic="prueba")
    assert out["ok"] and out["rounds"] == 3 and [h["ok"] for h in out["history"]] == [False, False, True]
    assert len(notes_seen[-1]) == 2 and "intento 2 incompleto" in notes_seen[-1][-1]
    assert lessons and "intento 2 incompleto" in lessons[0]


def test_the_loop_stops_at_the_round_limit_and_survives_a_crashing_check():
    def check(_c):
        raise ValueError("boom")

    out = self_correct("t", lambda task, notes: "x", check, max_rounds=2)
    assert not out["ok"] and out["rounds"] == 2 and "ValueError: boom" in out["history"][0]["report"]


def test_the_plain_loop_is_used_without_langgraph(monkeypatch):
    monkeypatch.setitem(sys.modules, "langgraph.graph", None)  # import fails
    out = self_correct("t", lambda task, notes: len(notes), lambda c: (c >= 1, "no"), max_rounds=3)
    assert out["engine"] == "loop" and out["ok"] and out["rounds"] == 2


def test_langgraph_is_the_engine_when_installed():
    pytest.importorskip("langgraph")
    out = self_correct("t", lambda task, notes: 1, lambda c: (True, ""), max_rounds=3)
    assert out["engine"] == "langgraph" and out["rounds"] == 1

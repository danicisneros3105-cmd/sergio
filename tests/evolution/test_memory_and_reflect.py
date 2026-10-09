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
    memory.remember(
        "blender",
        "una tetera de cerámica: cuerpo facetado, se arregló con perfiles suaves",
    )
    memory.remember("blender", "una mesa de roble: patas flotando por transform_apply")
    memory.remember("video", "short de viajes: 22 cortes de un segundo")
    top = memory.recall("haz una tetera de porcelana", 1)[0]
    assert "tetera" in top["text"] and top["kind"] == "blender"
    assert memory.recall("algo", 5, kinds=("video",))[0]["kind"] == "video"
    assert memory.stats()["memories"] == 3


def test_feedback_becomes_a_lesson_for_similar_jobs(memory):
    memory.feedback(
        "el video quedó muy lento, quiero cortes más rápidos",
        -1,
        about="short de viajes",
    )
    block = memory.lessons_for(
        "edita un video de viajes con cortes", kinds=("feedback",)
    )
    assert (
        "NO LE GUSTÓ" in block
        and "cortes más rápidos" in block
        and "LESSONS FROM YOUR LONG-TERM MEMORY" in block
    )
    assert (
        memory.lessons_for("receta de cocina vegana", kinds=("feedback",)) == ""
    )  # unrelated: nothing


def test_semantic_embeddings_are_used_when_given(tmp_path):
    def embed(texts):  # a fake "semantic" model: tea things close together
        return [
            [1.0, 0.0] if ("tetera" in t or "té" in t) else [0.0, 1.0] for t in texts
        ]

    m = mem.LongTermMemory(tmp_path, semantic=embed)
    m.remember("blender", "una tetera de cerámica")
    m.remember("blender", "una mesa")
    hit = m.recall("servicio de té", 1)[0]
    assert hit["space"] == "semantic" and "tetera" in hit["text"]


def test_local_embeddings_ignore_filler_words():
    a, b = (
        mem.hash_embed("una tetera de cerámica"),
        mem.hash_embed("una mesa de madera"),
    )
    assert sum(x * y for x, y in zip(a, b)) < 0.2


def test_the_loop_reflects_until_the_check_passes_and_stores_the_fix():
    notes_seen, lessons = [], []

    def generate(task, notes):
        notes_seen.append(list(notes))
        return len(notes_seen)

    out = self_correct(
        "tarea",
        generate,
        lambda c: (c >= 3, f"intento {c} incompleto"),
        max_rounds=5,
        remember=lessons.append,
        topic="prueba",
    )
    assert (
        out["ok"]
        and out["rounds"] == 3
        and [h["ok"] for h in out["history"]] == [False, False, True]
    )
    assert len(notes_seen[-1]) == 2 and "intento 2 incompleto" in notes_seen[-1][-1]
    assert lessons and "intento 2 incompleto" in lessons[0]


def test_the_loop_stops_at_the_round_limit_and_survives_a_crashing_check():
    def check(_c):
        raise ValueError("boom")

    out = self_correct("t", lambda task, notes: "x", check, max_rounds=2)
    assert (
        not out["ok"]
        and out["rounds"] == 2
        and "ValueError: boom" in out["history"][0]["report"]
    )


def test_the_plain_loop_is_used_without_langgraph(monkeypatch):
    monkeypatch.setitem(sys.modules, "langgraph.graph", None)  # import fails
    out = self_correct(
        "t", lambda task, notes: len(notes), lambda c: (c >= 1, "no"), max_rounds=3
    )
    assert out["engine"] == "loop" and out["ok"] and out["rounds"] == 2


def test_langgraph_is_the_engine_when_installed():
    pytest.importorskip("langgraph")
    out = self_correct("t", lambda task, notes: 1, lambda c: (True, ""), max_rounds=3)
    assert out["engine"] == "langgraph" and out["rounds"] == 1


def _tea_embed(fail_first: list[bool]):
    def embed(texts):
        if fail_first and fail_first.pop():
            raise RuntimeError("429 quota")
        return [
            [1.0, 0.0] if ("te" in t or "tetera" in t) else [0.0, 1.0] for t in texts
        ]

    return embed


def test_a_memory_saved_while_the_semantic_model_failed_is_still_recalled(tmp_path):
    m = mem.LongTermMemory(
        tmp_path, semantic=_tea_embed([True])
    )  # the first call hits the quota
    m.remember(
        "lesson", "el coche lleva cuatro ruedas"
    )  # semantic add fails -> cool-down
    m.remember("lesson", "la tetera necesita un pico curvo")  # cool-down: local only
    hits = m.recall("tetera", k=2)  # semantic store incomplete: local too
    assert "tetera" in hits[0]["text"] and hits[0]["space"] == "local"
    m._sem_retry_at = 0  # the cool-down is over
    hit = m.recall("tetera", k=1)[0]  # backfilled, now found semantically
    assert (
        m._sem.count() == 2 and hit["space"] == "semantic" and "tetera" in hit["text"]
    )
    # a restart opens the same semantic store
    again = mem.LongTermMemory(tmp_path, semantic=_tea_embed([]))
    assert again._sem is not None and again._sem.count() == 2


def test_a_failing_semantic_query_falls_back_to_local_recall(tmp_path):
    calls = {"n": 0}

    def embed(texts):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("offline")
        return [[1.0, 0.0] for _ in texts]

    m = mem.LongTermMemory(tmp_path, semantic=embed)
    m.remember("lesson", "la silla de oficina necesita ruedas")
    hit = m.recall("silla oficina ruedas", k=1)[0]
    assert hit["space"] == "local" and "silla" in hit["text"]


def test_a_new_semantic_model_with_other_dimensions_gets_its_own_store(tmp_path):
    m = mem.LongTermMemory(tmp_path, semantic=lambda ts: [[1.0, 0.0, 0.0] for _ in ts])
    m.remember("lesson", "uno")
    m2 = mem.LongTermMemory(tmp_path, semantic=lambda ts: [[1.0, 0.0] for _ in ts])
    m2.remember("lesson", "dos")
    assert {h["text"] for h in m2.recall("uno dos", k=5)} == {"uno", "dos"}


def test_gemini_embedder_marks_documents_and_queries(monkeypatch):
    seen = []

    class FakeModels:
        def embed_content(self, model, contents, config):
            seen.append(config["task_type"])
            return type(
                "R",
                (),
                {
                    "embeddings": [
                        type("E", (), {"values": [3.0, 4.0]})() for _ in contents
                    ]
                },
            )()

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    import sys
    import types

    genai = types.ModuleType("google.genai")
    genai.Client = FakeClient
    google = sys.modules.get("google") or types.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setattr(google, "genai", genai, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    embed = mem.gemini_embedder()
    assert embed(["a"])[0] == [0.6, 0.8]  # normalised (768-d Gemini vectors are not)
    embed(["q"], task="RETRIEVAL_QUERY")
    assert seen == ["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]


def test_without_chromadb_semantic_recall_still_works_and_old_memories_move_in(
    tmp_path, monkeypatch
):
    import json

    monkeypatch.setitem(sys.modules, "chromadb", None)  # as on a PC without chromadb
    (tmp_path / "memoria.jsonl").write_text(
        json.dumps(
            {
                "id": "old1",
                "text": "una tetera vieja",
                "meta": {"kind": "lesson"},
                "vec": [],
            }
        )
        + "\n"
    )
    m = mem.LongTermMemory(tmp_path, semantic=_tea_embed([]))
    assert m.engine == "json" and m.stats()["memories"] == 1
    m.remember("lesson", "un coche rojo")
    hit = m.recall("quiero té en la tetera", 1)[0]
    assert hit["space"] == "semantic" and "tetera" in hit["text"]
    assert m.stats()["semantic_memories"] == 2
    again = mem.LongTermMemory(tmp_path, semantic=_tea_embed([]))  # persisted on disk
    assert again.stats() == {
        "engine": "json",
        "memories": 2,
        "semantic": True,
        "semantic_memories": 2,
    }
    assert (tmp_path / "memoria.jsonl.migrated").exists()

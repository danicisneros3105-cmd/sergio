"""Terry: medium and complicated requests are understood first, in the background."""

from __future__ import annotations

import json

import pytest

from openjarvis.agents import terry

ANALYSIS = {
    "intent": "un plan de marketing para lanzar una cafetería",
    "deliverable": "plan de 30 días",
    "audience": "el dueño",
    "constraints": ["presupuesto bajo"],
    "hidden_needs": ["que se pueda hacer solo"],
    "format": "tabla por semanas",
    "tone": "directo",
    "language": "Spanish",
    "skills": ["marketing local", "copywriting"],
    "pitfalls": ["ideas genéricas"],
    "success": ["acciones con fecha y costo"],
}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("SERGIO_TERRY", "1")
    monkeypatch.setattr(terry, "learned", lambda text: 0.0)
    terry._last.clear()


def test_small_talk_skips_terry_and_real_work_goes_to_him():
    assert not terry.wanted("hola")
    assert not terry.wanted("gracias!")
    assert not terry.wanted("qué hora es")
    big = (
        "Hazme un plan de marketing para lanzar mi cafetería en Cuenca, con "
        "presupuesto bajo, ideas para Instagram, alianzas con negocios del barrio "
        "y un calendario de cuatro semanas; además analiza a la competencia."
    )
    assert terry.complexity(big) > terry.complexity("hazme un logo")
    assert terry.wanted(big)


def test_the_fly_brain_moves_the_bar(monkeypatch):
    medium = "escribe una propuesta corta para un cliente de diseño"
    base = terry.complexity(medium)
    monkeypatch.setattr(terry, "learned", lambda text: 0.15)
    helped = terry.wanted(medium, threshold=base + 0.1)
    monkeypatch.setattr(terry, "learned", lambda text: -0.15)
    corrected = terry.wanted(medium, threshold=base - 0.1)
    assert helped and not corrected


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("SERGIO_TERRY", "0")
    assert not terry.wanted("analiza y compara estas tres estrategias de negocio " * 4)


@pytest.mark.parametrize(
    "model,family,marker",
    [
        ("claude-sonnet", "claude", "<task>"),
        ("gpt-5", "gpt", "# Goal"),
        ("gemini-3.6-flash", "gemini", "Objetivo:"),
        ("qwen3:8b", "local", "Task:"),
    ],
)
def test_the_brief_is_written_the_way_each_model_reads_best(model, family, marker):
    assert terry.family(model) == family
    text = terry.brief(ANALYSIS, model)
    assert text.startswith("<encargo_preparado>") and marker in text
    assert "presupuesto bajo" in text and "Answer in: Spanish" in text


def test_prepare_asks_once_and_checks_the_answer():
    seen = []

    def ask(prompt, **kw):
        seen.append((prompt, kw))
        return json.dumps(ANALYSIS)

    brief, analysis = terry.prepare(
        "plan para mi café", "User: hola", "gemini", ask=ask
    )
    assert analysis["intent"] and "Objetivo" in brief
    assert (
        len(seen) == 1 and seen[0][1]["json_mode"] and "plan para mi café" in seen[0][0]
    )
    with pytest.raises(ValueError):
        terry.prepare("x", "", "gemini", ask=lambda p, **k: json.dumps({"intent": ""}))


def test_status_lines_start_with_terry_and_follow_the_language():
    es = terry.statuses("es", seed=1)
    en = terry.statuses("en", seed=1)
    assert (
        es[0] == "Entendiendo lo que necesitas…"
        and en[0] == "Understanding what you need…"
    )
    assert "Revisando los detalles…" in terry.FUN["es"]  # real steps, never jokes
    assert "Checking the details…" in terry.FUN["en"]
    assert terry.language("please write the plan for this launch") == "en"
    assert terry.language("hazme el plan para la tienda") == "es"


def test_the_owners_next_words_teach_the_fly_about_terry(monkeypatch):
    taught = []

    class Fly:
        def learn(self, text, action, reward):
            taught.append((text, action, reward))

    monkeypatch.setattr(terry, "_fly", lambda: Fly())
    assert terry.judge_previous("no, eso no") == 0.0  # nothing was prepared
    terry.prepared("plan de marketing")
    assert terry.judge_previous("no, eso no es lo que pedí") == -1.0
    terry.prepared("plan de ventas")
    assert terry.judge_previous("y para el mes siguiente?") == terry.NO_COMPLAINT
    assert [t[1] for t in taught] == ["terry", "terry"]
    assert taught[0][0] == "plan de marketing"

"""AdaptiveScrutiny: ten axes, autonomy levels, hard rules and learned trust."""

from __future__ import annotations

import pytest

from openjarvis.cowork.scrutiny import (
    AXES,
    AdaptiveScrutiny,
    TrustStore,
    normalize_autonomy,
    score_step,
)

GOAL = "Comparar los 3 mejores portátiles para Blender y hacer una tabla"


@pytest.fixture()
def trust(tmp_path):
    return TrustStore(tmp_path / "trust.json")


def test_ten_axes_scored_0_to_3():
    scores = score_step("Buscar portátiles", goal=GOAL, tools=["web_search"], check="x")
    assert set(scores) == set(AXES) and len(AXES) == 10
    assert all(0 <= v <= 3 for v in scores.values())


def test_search_runs_on_its_own(trust):
    v = AdaptiveScrutiny("normal", trust).review(
        "Buscar los mejores portátiles para Blender",
        goal=GOAL,
        tools=["web_search"],
        check="3 modelos",
    )
    assert v.decision == "allow"


@pytest.mark.parametrize(
    "text,tools",
    [
        ("Envía la tabla por WhatsApp a Juan", ["whatsapp_send"]),
        ("Envía un correo con la tabla a mi jefe", []),
        ("Publica la tabla en Twitter", []),
        ("Llama a mamá para avisarle", []),
    ],
)
def test_never_acts_through_other_people(trust, text, tools):
    v = AdaptiveScrutiny("autonomo", trust).review(
        text, goal=GOAL, tools=tools, check="x"
    )
    assert v.decision == "block"
    assert "nunca envía" in " ".join(v.reasons)


@pytest.mark.parametrize(
    "text",
    ["Compra el portátil más barato", "Inicia sesión con mi contraseña del banco"],
)
def test_money_and_credentials_always_ask(trust, text):
    v = AdaptiveScrutiny("autonomo", trust).review(text, goal=GOAL, check="x")
    assert v.decision == "ask"


def test_false_friends_do_not_trigger(trust):
    s = AdaptiveScrutiny("normal", trust)
    llama = score_step(
        "Descargar el modelo llama 3 para comparar", goal=GOAL, check="ok"
    )
    assert llama["external_actor"] == 0
    public = score_step("Leer la API pública de precios", goal=GOAL, check="ok")
    assert public["external_actor"] == 0
    traits = score_step("Tabla con características", goal=GOAL, check="ok")
    assert traits["privacy"] == 0
    assert (
        s.review("Tabla con características", goal=GOAL, check="ok").decision == "allow"
    )


def test_autonomy_levels(trust):
    text, tools = "Borra los duplicados de la tabla", ["file_write"]
    decisions = {
        level: AdaptiveScrutiny(level, trust)
        .review(text, goal=GOAL, tools=tools, check="x")
        .decision
        for level in ("cauteloso", "normal", "autonomo")
    }
    assert decisions["cauteloso"] == "ask"
    assert decisions["normal"] == "ask"  # destructive 3: over the normal limit
    write = "Guarda la tabla de portátiles en un archivo"
    assert (
        AdaptiveScrutiny("cauteloso", trust)
        .review(write, goal=GOAL, tools=["file_write"], check="x")
        .decision
        == "ask"
    )
    assert (
        AdaptiveScrutiny("normal", trust)
        .review(write, goal=GOAL, tools=["file_write"], check="x")
        .decision
        == "allow"
    )


def test_trust_is_learned_and_lost(trust):
    s = AdaptiveScrutiny("normal", trust)
    text, tools = "Descarga las fichas técnicas de los portátiles", ["http_request"]
    first = s.review(text, goal=GOAL, tools=tools, check="pdfs")
    assert first.decision == "ask"
    for _ in range(3):
        trust.record(first.signature, True)
    assert s.review(text, goal=GOAL, tools=tools, check="pdfs").decision == "allow"
    trust.record(first.signature, False)
    assert s.review(text, goal=GOAL, tools=tools, check="pdfs").decision == "ask"
    trust.record(first.signature, False)
    assert s.review(text, goal=GOAL, tools=tools, check="pdfs").decision == "block"


def test_failures_tighten_scrutiny(trust):
    s = AdaptiveScrutiny("autonomo", trust)
    s.note_outcome(False)
    s.note_outcome(False)
    assert s.level == "normal"
    s.note_outcome(True)
    assert s.level == "autonomo"


def test_scope_and_uncertainty():
    drift = score_step(
        "Reordenar el escritorio de Windows por colores", goal=GOAL, check=""
    )
    assert drift["scope"] == 1 and drift["uncertainty"] == 1
    invented = score_step(
        "Usar la herramienta mágica", goal=GOAL, check="x", invented=["magic"]
    )
    assert invented["uncertainty"] == 2


def test_autonomy_names():
    assert normalize_autonomy("Autónomo") == "autonomo"
    assert normalize_autonomy("cautious") == "cauteloso"
    assert normalize_autonomy("whatever") == "normal"

# ruff: noqa: E501
"""Sergio learns how the owner writes, on this computer, and talks like him."""

from __future__ import annotations

from openjarvis.connectome.estilo import Style
from openjarvis.persona import SERGIO_CHAT_PERSONA


def test_too_little_to_judge_says_nothing_and_the_writing_rules_are_always_on(tmp_path):
    s = Style(tmp_path / "e.json")
    s.observe("hola")
    assert s.block() == ""
    assert (
        "la respuesta primero" in SERGIO_CHAT_PERSONA
        and "«¡Claro!»" in SERGIO_CHAT_PERSONA
    )


def test_short_messages_and_tu_make_short_answers(tmp_path):
    s = Style(tmp_path / "e.json", clock=lambda: 1_760_000_000)
    for text in [
        "dime el clima",
        "hazme un video de ventas",
        "puedes resumir esto",
        "oye y el video",
        "dime las ventas",
        "ventas de hoy",
    ]:
        s.observe(text)
    p = s.profile()
    assert p["largo"] == "corto" and p["trato"] == "tú" and p["idioma"] == "español"
    assert "ventas" in p["temas"] and "video" in p["temas"]
    block = s.block()
    assert "responda corto" in block and "Sin emojis" in block


def test_asking_for_more_detail_moves_the_length(tmp_path):
    s = Style(tmp_path / "e.json")
    long = "Quisiera que usted me ayudara a preparar la estrategia completa del lanzamiento del producto nuevo para el mercado andino, considerando los canales, el presupuesto disponible y los riesgos principales que podríamos enfrentar durante los primeros seis meses de operación comercial en cada país."
    for _ in range(6):
        s.observe(long)
    s.observe("explícame más, con más detalle")
    s.observe("profundiza en los riesgos")
    p = s.profile()
    assert p["largo"] == "detallado" and p["trato"] == "usted"


def test_it_remembers_across_restarts_and_ignores_commands(tmp_path):
    path = tmp_path / "e.json"
    s = Style(path)
    for _ in range(5):
        s.observe("what is the weather today and can you help me")
    s.observe("/nuevo")
    assert Style(path).profile()["idioma"] == "inglés"
    assert Style(path).data["n"] == 5

"""Pro agents, agents the user creates, and their schedules."""

from __future__ import annotations

import datetime

from sergio_escritorio.agentes import PRO, Agents, describe, parse


def test_pro_agents_have_a_role_a_method_and_their_own_tools():
    from openjarvis.server.tasks_routes import NEVER, TOOLS

    assert len(PRO) >= 9
    for agent in PRO:
        assert agent["instrucciones"] and agent["herramientas"]
        assert all(t in TOOLS and t not in NEVER for t in agent["herramientas"]), agent["nombre"]


def test_created_agents_are_saved_found_and_scheduled(tmp_path):
    agents = Agents(tmp_path / "a.json")
    agents.add({"nombre": "Noticias IA", "rol": "Resume noticias de IA", "instrucciones": "…",
                "herramientas": ["web_search"], "horario": {"hora": "08:00", "dias": [0]}, "tarea": "resume las noticias"})
    again = Agents(tmp_path / "a.json")
    assert again.find("noticias ia")["tarea"] == "resume las noticias"
    assert again.find("investigadora")["nombre"] == "Investigador"  # pro, by a close name
    monday_7, monday_8 = datetime.datetime(2026, 10, 5, 7, 59), datetime.datetime(2026, 10, 5, 8, 1)
    assert again.due(monday_7) == [] and [a["nombre"] for a in again.due(monday_8)] == ["Noticias IA"]
    again.ran(again.due(monday_8)[0], monday_8)
    assert again.due(monday_8) == []  # once a day
    assert "lunes a las 08:00" in describe(again.find("Noticias IA"))
    assert not again.remove("Investigador") and again.remove("Noticias IA")


def test_voice_orders_for_agents(tmp_path):
    agents = Agents(tmp_path / "a.json")
    assert parse("crea un agente que cada lunes me resuma las noticias")[0] == "create"
    assert parse("Investigador, compara las RTX 5070 y 5080", agents) == ("use", "Investigador", "compara las RTX 5070 y 5080")
    assert parse("usa el agente viajes para planear Lima") == ("use", "viajes", "planear Lima")
    assert parse("mis agentes") == ("show", "", "")
    assert parse("Juan, pásame la sal", agents) is None


def test_agents_remember_what_they_did(tmp_path):
    agents = Agents(tmp_path / "a.json")
    agents.remember("Investigador", "Comparé RTX 5070 y 5080: la 5080 rinde 30 % más en Cycles.")
    again = Agents(tmp_path / "a.json")
    agent = again.with_memory(again.find("Investigador"))
    assert "rinde 30 % más" in agent["instrucciones"] and "no repitas" in agent["instrucciones"]
    assert {a["nombre"] for a in PRO} >= {"Resumen diario", "Correo"}
    correo = again.find("Correo")
    assert "NUNCA envía" in correo["instrucciones"]


def test_the_plan_is_shown_before_the_work():
    from sergio_escritorio.tareas import Step, Task, plan_line

    task = Task(1, "tabla de portátiles", title="Portátiles", steps=[Step("buscar los 3 mejores"), Step("abrir en Excel", "pantalla")])
    assert plan_line(task).startswith("Plan de «Portátiles»: 1) buscar los 3 mejores 2) abrir en Excel (pantalla)")
    assert "cancela la tarea" in plan_line(task)

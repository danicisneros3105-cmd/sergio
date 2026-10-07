"""Task plans are checked before anything runs (no invented tools)."""

from __future__ import annotations

from openjarvis.server.tasks_routes import plan_task, validate_plan


def test_invented_and_forbidden_tools_never_reach_the_desktop():
    plan = validate_plan(
        {"titulo": "Portátiles", "pasos": [
            {"paso": "Buscar los 3 mejores portátiles para Blender", "donde": "fondo",
             "herramientas": ["web_search", "super_scraper"]},
            {"paso": "Mandar la tabla por WhatsApp a Juan", "herramientas": ["whatsapp_send"]},
            {"paso": "Abrir la tabla en Excel", "donde": "fondo", "herramientas": ["desktop_action"]},
            {"paso": "Borra los archivos temporales", "donde": "fondo", "herramientas": ["terminal_run"]},
        ]},
        "portátiles",
    )
    steps = plan["pasos"]
    assert [s["herramientas"] for s in steps] == [["web_search"], ["desktop_action"], ["terminal_run"]]
    assert steps[0]["inventadas"] == ["super_scraper"]
    assert steps[1]["donde"] == "pantalla"  # a screen tool always needs the screen
    assert steps[2]["importante"] and not steps[0]["importante"]
    assert plan["descartados"] == ["Mandar la tabla por WhatsApp a Juan"]


def test_an_empty_plan_becomes_one_step():
    plan = validate_plan({}, "ordena mis descargas")
    assert plan["pasos"][0]["paso"] == "ordena mis descargas"


def test_the_planner_sees_the_real_tool_list():
    seen = []
    plan_task("haz una tabla", ask=lambda prompt, **kw: seen.append(prompt) or {"pasos": []})
    assert "python_run" in seen[0] and "whatsapp_send" not in seen[0]


def test_objects_are_named_by_a_vote_and_doubts_are_said():
    import json

    from openjarvis.server.vision_routes import name_by_vote

    def looks(*labels):
        it = iter(labels)
        return lambda img, prompt, models: json.dumps({"etiqueta": next(it), "seguridad": 0.6})

    sure = name_by_vote(b"x", ask=looks("labial", "Labial rojo"))
    assert sure["votes"] == "2/2" and not sure["unsure"] and sure["confidence"] >= 0.85
    tie = name_by_vote(b"x", ask=looks("silla", "labial", "labial"))  # the third look breaks the tie
    assert tie["label"] == "labial" and tie["votes"] == "2/3"
    doubt = name_by_vote(b"x", ask=looks("silla", "control remoto", "teléfono"))
    assert doubt["unsure"] and doubt["confidence"] <= 0.55


def test_formatting_text_is_not_formatting_a_disk():
    plan = validate_plan({"pasos": [{"paso": "Formatea los datos como CSV"}, {"paso": "Formatea el disco D"}]}, "x")
    assert [s["importante"] for s in plan["pasos"]] == [False, True]


def test_agent_specs_are_checked():
    from openjarvis.server.tasks_routes import validate_agent

    spec = validate_agent({"nombre": "Noticias", "herramientas": ["web_search", "whatsapp_send", "magic"],
                           "horario": {"hora": "25:00", "dias": [0]}}, "x")
    assert spec["herramientas"] == ["web_search"] and spec["horario"] == {"hora": "", "dias": []}


def test_an_agent_plans_only_with_its_toolbox():
    plan = plan_task("x", ask=lambda p, **k: {"pasos": [{"paso": "a", "herramientas": ["web_search", "terminal_run"]}]},
                     tools=["web_search"])
    assert plan["pasos"][0]["herramientas"] == ["web_search"] and plan["pasos"][0]["inventadas"] == ["terminal_run"]


def test_the_plan_is_a_graph_without_cycles():
    from openjarvis.server.tasks_routes import validate_plan

    plan = validate_plan({"pasos": [
        {"paso": "buscar A", "herramientas": ["web_search"], "depende_de": []},
        {"paso": "buscar B", "herramientas": ["web_search"], "depende_de": [2, 5]},
        {"paso": "tabla", "herramientas": ["file_write"], "depende_de": [1, 2, True]},
        {"paso": "abrir", "herramientas": ["desktop_action"]}]}, "x")
    assert [s.get("depende_de") for s in plan["pasos"]] == [[], [], [1, 2], None]


def test_a_step_for_each_element_and_the_skills_go_in_the_plan():
    seen = []

    def ask(prompt, **_k):
        seen.append(prompt)
        return {"pasos": [{"paso": "precio", "herramientas": ["web_search"], "para_cada": [f"p{n}" for n in range(400)] + ["p1"]},
                          {"paso": "render", "herramientas": ["blender_create"], "para_cada": ["solo uno"]}]}

    plan = plan_task("renderiza en Blender cada producto", ask=ask)
    assert len(plan["pasos"][0]["para_cada"]) == 300 and "para_cada" not in plan["pasos"][1]
    assert "Blender de producción" in plan["reglas"] and "Reglas obligatorias" in seen[0]


def test_a_plan_already_made_comes_back_at_once(monkeypatch):
    from openjarvis.coach import brain

    calls = []

    def fake(prompt, **_k):
        calls.append(prompt)
        return {"pasos": [{"paso": "buscar", "herramientas": ["web_search"]}]}

    monkeypatch.setattr(brain, "ask", fake)
    first = plan_task("Busca vuelos a Lima, por favor")
    again = plan_task("busca vuelos a lima por favor")
    assert len(calls) == 1 and again.get("cache") and not first.get("cache")

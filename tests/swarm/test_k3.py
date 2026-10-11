"""Agent Swarm, Kimi-K3 level: scout, shared budget, live tools, retries,
code-checked report, exports."""

from __future__ import annotations

import csv
import io
import time

from openjarvis.swarm.engine import NO_BUDGET, SwarmEngine
from openjarvis.swarm.report import (
    check_note,
    figures,
    markdown_blocks,
    number_values,
    tables_csv,
    tables_in,
    verify_report,
)

REPORT = """# Precios

| Producto | Precio | Tienda |
|---|---|---|
| Silla | 1.234,50 € | https://a.test/silla |
| Mesa \\| roble | 99 € | https://b.test/mesa |

Total: 1.333,50 €.
"""


def test_figures_are_read_in_both_notations_and_tiny_numbers_skipped():
    assert 1234.5 in number_values("1.234,50") and 1234.5 in number_values("1,234.50")
    assert figures(
        "1. Primero\n## 2. Título\nSon 3 sillas a 45 € y 1.200 ud, ver https://x.test/99"
    ) == ["45", "1.200"]


def test_tables_become_csv_and_workspace_blocks():
    tables = tables_in(REPORT)
    assert tables[0][0] == ["Producto", "Precio", "Tienda"]
    assert tables[0][2][0] == "Mesa | roble"  # an escaped pipe stays in its cell
    rows = list(csv.reader(io.StringIO(tables_csv(REPORT))))
    assert rows[1] == ["Silla", "1.234,50 €", "https://a.test/silla"]
    blocks = markdown_blocks(
        REPORT + "\n- uno\n1. dos\n> cita\n```py\nx = 1\n```\n---\n"
    )
    kinds = [b["type"] for b in blocks]
    assert kinds == [
        "h1",
        "table",
        "text",
        "bullet",
        "number",
        "quote",
        "code",
        "divider",
    ]
    table = blocks[1]["table"]
    assert [c["name"] for c in table["columns"]] == ["Producto", "Precio", "Tienda"]
    assert len(table["rows"]) == 2 and table["views"][0]["kind"] == "table"


def test_verify_flags_invented_links_figures_and_unread_documents():
    results = [
        "Silla 1234,50 € en https://a.test/silla",
        "Mesa 99 € https://b.test/mesa/",
    ]
    checks = verify_report(
        REPORT,
        results,
        ["https://a.test/silla"],
        documents=[
            {"name": "contrato-a.pdf", "status": "done"},
            {"name": "b.pdf", "status": "failed"},
        ],
    )
    assert checks["links_unverified"] == []  # trailing slash and case do not matter
    assert checks["figures_unbacked"] == ["1.333,50"]  # the total nobody computed
    assert checks["documents_unread"] == ["b.pdf"]
    assert checks["documents_unmentioned"] == ["contrato-a.pdf"]
    note = check_note(checks)
    assert "Comprobación automática" in note and "1.333,50" in note and "b.pdf" in note
    assert check_note({"ok": True}) == ""


def test_scout_maps_the_ground_and_each_agent_shows_its_tool_live(tmp_path):
    prompts: list[str] = []

    def ask(prompt: str, **_kw):
        prompts.append(prompt)
        if "orquestador" in prompt:
            return {
                "subtareas": [
                    {"instruccion": "precio de Silla"},
                    {"instruccion": "precio de Mesa"},
                ]
            }
        return {"informe": "# Informe\nSilla 45 € (https://s.test/1)."}

    tries = {"Mesa": 0}

    def runner(prompt, tools, budget, on_tool=None):
        if "explorador" in prompt:
            on_tool("web_search", {"query": "muebles"})
            return "Elementos: Silla, Mesa. Fuente: https://s.test/1", 1
        on_tool("web_search", {"query": "precio"})
        if "Mesa" in prompt:
            tries["Mesa"] += 1
            if tries["Mesa"] == 1:
                raise TimeoutError("lento")
            return "Mesa 80 € https://s.test/2", 2
        return "Silla 45 € https://s.test/1", 2

    engine = SwarmEngine(ask=ask, runner=runner, home=tmp_path, retry_delays=(0,))
    seen: list[dict] = []
    run = engine.start("precios de muebles", background=True)
    box = engine.listen(run.id)
    for _ in range(500):
        if run.status in ("done", "failed"):
            break
        time.sleep(0.01)
    while not box.empty():
        seen.append(box.get())
    assert run.status == "done", run.error
    assert "Elementos: Silla, Mesa" in next(p for p in prompts if "orquestador" in p)
    mesa = next(s for s in run.subtasks if "Mesa" in s.instruction)
    assert mesa.status == "done" and mesa.attempts == 2
    assert any(
        e["type"] == "tool" and e["text"] == "Busca en la web: precio" for e in seen
    )
    assert any(e["type"] == "retry" for e in seen)
    assert run.to_dict()["tool_calls"] == 1 + 2 + 2
    assert run.checks["ok"] and "Comprobación" not in run.report


def test_the_whole_swarm_shares_one_budget(tmp_path):
    def ask(prompt: str, **_kw):
        if "orquestador" in prompt:
            return {"subtareas": [{"instruccion": f"t{i}"} for i in range(5)]}
        return {"informe": "R"}

    budgets: list[int] = []

    def runner(prompt, tools, budget):
        budgets.append(budget)
        return "ok", budget  # spends all it is given

    engine = SwarmEngine(ask=ask, runner=runner, home=tmp_path, retry_delays=())
    run = engine.start("cinco", parallel=1, background=False, scout=False, budget=30)
    assert budgets == [12, 12, 6]
    assert run.used() == 30
    assert [s.result for s in run.subtasks[3:]] == [NO_BUDGET, NO_BUDGET]


def test_the_supervisor_corrects_what_code_could_not_back(tmp_path):
    asked: list[str] = []

    def ask(prompt: str, **_kw):
        asked.append(prompt)
        if "orquestador" in prompt:
            return {"subtareas": [{"instruccion": "precio"}]}
        if "comprobación por código" in prompt:
            return {"informe": "# Informe\nSilla 45 € (https://s.test/1)."}
        return {
            "informe": "# Informe\nSilla 45 € (https://s.test/1), mesa 990 € (https://inventada.test)."
        }

    engine = SwarmEngine(
        ask=ask,
        runner=lambda p, t, b: ("Silla 45 € https://s.test/1", 1),
        home=tmp_path,
    )
    run = engine.start("precio", background=False, scout=False)
    assert run.revised and run.checks["ok"]
    assert "inventada" not in run.report and "Comprobación" not in run.report
    assert "https://inventada.test" in asked[-1] and "990" in asked[-1]

    # When the correction does not help, the first report stays, flagged.
    stubborn = SwarmEngine(
        ask=lambda p, **k: (
            {"subtareas": [{"instruccion": "precio"}]}
            if "orquestador" in p
            else {"informe": "# Informe\nMesa 990 €."}
        ),
        runner=lambda p, t, b: ("Silla 45 €", 1),
        home=tmp_path / "b",
    )
    run = stubborn.start("precio", background=False, scout=False)
    assert not run.revised and run.checks["figures_unbacked"] == ["990"]
    assert run.report.rstrip().endswith("990")
    assert "## Comprobación automática" in run.report


def test_export_and_save_to_workspace(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server import swarm_routes

    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path / "home"))
    app = FastAPI()
    app.include_router(swarm_routes.router)
    engine = SwarmEngine(
        ask=lambda p, **k: (
            {"titulo": "Muebles", "subtareas": [{"instruccion": "a"}]}
            if "orquestador" in p
            else {"informe": REPORT}
        ),
        runner=lambda p, t, b: (
            "Silla 1.234,50 € https://a.test/silla; Mesa 99 € https://b.test/mesa; total 1.333,50",
            1,
        ),
        home=tmp_path,
    )
    app.state.swarm_engine = engine
    run = engine.start("muebles", background=False, scout=False)
    client = TestClient(app)
    md = client.get(f"/v1/swarm/{run.id}/export?format=md")
    assert (
        md.status_code == 200
        and "## Fuentes" in md.text
        and "https://a.test/silla" in md.text
    )
    assert "Muebles.md" in md.headers["content-disposition"]
    sheet = client.get(f"/v1/swarm/{run.id}/export?format=csv")
    assert sheet.status_code == 200 and sheet.text.startswith("﻿Producto,Precio,Tienda")
    assert client.get(f"/v1/swarm/{run.id}/export?format=json").json()["id"] == run.id
    assert client.get(f"/v1/swarm/{run.id}/export?format=exe").status_code == 400
    saved = client.post(f"/v1/swarm/{run.id}/workspace")
    assert saved.status_code == 200, saved.text
    from openjarvis.workspace.store import default_store

    page = default_store().get(saved.json()["page"])
    assert page["title"] == "Muebles" and any(
        b["type"] == "table" for b in page["blocks"]
    )

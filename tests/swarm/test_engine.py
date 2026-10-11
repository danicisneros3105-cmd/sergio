"""Agent Swarm: plan, parallel sub-agents, supervisor, dissolve."""

from __future__ import annotations

import threading
import time

from openjarvis.swarm.engine import (
    MAX_SUBTASKS,
    Document,
    SwarmEngine,
    allowed_tools,
    plan_subtasks,
    sources_in,
)


def test_plan_is_checked_and_documents_each_get_a_reader():
    data = {
        "titulo": "Contratos",
        "roles": [{"nombre": "Auditor", "especialidad": "riesgos"}],
        "por_documento": "Extrae partes, plazo y penalizaciones.",
        "subtareas": [
            {
                "titulo": "Comparar",
                "rol": "Auditor",
                "instruccion": "Compara las penalizaciones",
                "herramientas": ["shell_exec", "think"],
            },
            {"titulo": "vacía", "instruccion": ""},
            "basura",
        ],
    }
    docs = [Document("a.pdf", "/x/a.pdf"), Document("b.pdf", "/x/b.pdf")]
    title, roles, subs, synthesis = plan_subtasks("Revisa los contratos", data, docs)
    assert title == "Contratos"
    assert [s.document for s in subs] == ["a.pdf", "b.pdf", ""]
    assert subs[0].instruction == "Extrae partes, plazo y penalizaciones."
    assert subs[2].tools == ["think"]  # shell_exec is never handed out
    assert roles[0]["nombre"] == "Lector de documentos"
    assert synthesis


def test_plan_falls_back_to_one_generalist_and_is_bounded():
    _, _, subs, _ = plan_subtasks("algo", {}, [])
    assert len(subs) == 1 and subs[0].role == "Generalista"
    many = {"subtareas": [{"instruccion": f"busca {i}"} for i in range(300)]}
    _, _, subs, _ = plan_subtasks("x", many, [])
    assert len(subs) == MAX_SUBTASKS
    assert allowed_tools(["whatsapp_send"]) == ["web_search", "think"]
    assert sources_in("ver https://a.com/x. y https://a.com/x") == ["https://a.com/x"]


def test_a_swarm_runs_in_parallel_then_the_supervisor_reports(tmp_path):
    asked: list[str] = []

    def ask(prompt: str, **_kw):
        asked.append(prompt)
        if "orquestador" in prompt:
            return {
                "titulo": "Precios",
                "subtareas": [
                    {
                        "titulo": f"P{i}",
                        "rol": "Investigador",
                        "instruccion": f"precio {i}",
                    }
                    for i in range(6)
                ],
            }
        return {
            "informe": "# Informe\nTodo bien.",
            "contradicciones": ["P1 y P2 difieren"],
            "huecos": [],
        }

    running = {"now": 0, "max": 0}
    lock = threading.Lock()

    def runner(prompt: str, tools, budget):
        with lock:
            running["now"] += 1
            running["max"] = max(running["max"], running["now"])
        time.sleep(0.05)
        with lock:
            running["now"] -= 1
        if "precio 3" in prompt:
            raise RuntimeError("caído")
        return f"Hecho, ver https://tienda.test/{len(prompt)}", 2

    engine = SwarmEngine(ask=ask, runner=runner, home=tmp_path, retry_delays=(0, 0))
    run = engine.start("precios de 6 productos", parallel=3, background=False)
    assert run.status == "done"
    assert running["max"] == 3  # three at a time, as asked
    counts = run.counts()
    assert counts["done"] == 5 and counts["failed"] == 1
    assert run.report.startswith("# Informe")
    assert run.contradictions == ["P1 y P2 difieren"]
    data = run.to_dict()
    # 5 sub-agents × 2 calls, plus the scout's 2; the failing one tried 3 times.
    assert data["tool_calls"] == 12 and data["sources"]
    assert run.scout and [s.attempts for s in run.subtasks if s.status == "failed"] == [
        3
    ]
    # Dissolved: nothing left to cancel, and the report is kept on disk.
    assert engine.cancel(run.id) is False
    again = SwarmEngine(ask=ask, runner=runner, home=tmp_path)
    assert again.get(run.id).report.startswith("# Informe")


def test_cancel_stops_the_queue(tmp_path):
    gate = threading.Event()

    def ask(prompt: str, **_kw):
        return {"subtareas": [{"instruccion": f"t{i}"} for i in range(10)]}

    def runner(prompt, tools, budget):
        gate.wait(2)
        return "ok", 0

    engine = SwarmEngine(ask=ask, runner=runner, home=tmp_path)
    run = engine.start("diez cosas", parallel=1, scout=False)
    for _ in range(100):
        if run.status == "running":
            break
        time.sleep(0.01)
    assert engine.cancel(run.id)
    gate.set()
    for _ in range(300):
        if run.status in ("cancelled", "done"):
            break
        time.sleep(0.01)
    assert run.status == "cancelled"
    assert run.counts()["cancelled"] >= 8


def test_routes_start_and_read(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server import swarm_routes

    app = FastAPI()
    app.include_router(swarm_routes.router)
    app.state.swarm_engine = SwarmEngine(
        ask=lambda p, **k: (
            {"subtareas": [{"instruccion": "a"}]}
            if "orquestador" in p
            else {"informe": "R"}
        ),
        runner=lambda p, t, b: ("ok", 1),
        home=tmp_path,
    )
    client = TestClient(app)
    r = client.post(
        "/v1/swarm",
        data={"task": "algo", "parallel": "2"},
        files=[("files", ("c.txt", b"hola", "text/plain"))],
    )
    assert r.status_code == 200, r.text
    run_id = r.json()["id"]
    for _ in range(200):
        body = client.get(f"/v1/swarm/{run_id}").json()
        if body["status"] == "done":
            break
        time.sleep(0.01)
    assert body["status"] == "done" and body["report"].startswith("R\n")
    # Code noticed the report never names the document it was given.
    assert body["checks"]["documents_unmentioned"] == ["c.txt"]
    assert body["subtasks"][0]["document"] == "c.txt"
    assert client.get("/v1/swarm").json()["runs"][0]["id"] == run_id
    assert client.post("/v1/swarm", data={"task": " "}).status_code == 400
    bad = client.post(
        "/v1/swarm",
        data={"task": "x"},
        files=[("files", ("v.exe", b"MZ", "application/octet-stream"))],
    )
    assert bad.status_code == 400
    assert client.get("/v1/swarm/nope").status_code == 404

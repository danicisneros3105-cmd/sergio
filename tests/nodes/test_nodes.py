"""Nodes: persistent agents with a computer, memory, rules and routines."""

from __future__ import annotations

import time

import pytest

from openjarvis.nodes.store import NodeError, NodeStore, Routine, clean_rules, tools_for
from openjarvis.nodes.worker import NodeWorker, parse_answer


def _worker(tmp_path, answers):
    seen: list[tuple[str, list[str]]] = []

    def runner(prompt, tools, budget, on_tool):
        seen.append((prompt, list(tools)))
        on_tool("web_search", {"query": "pisos en Cuenca"})
        answer = answers.pop(0) if answers else "Hecho."
        return answer, 1

    worker = NodeWorker(
        NodeStore(tmp_path),
        runner=runner,
        ask=lambda p, **k: {"presentacion": "Hola, soy Ana."},
    )
    return worker, seen


def test_rules_lock_sending_and_paying():
    rules = clean_rules(
        {"messages": "allow", "purchases": "allow", "web": "block", "nope": "allow"}
    )
    assert (
        rules["messages"] == "ask"
        and rules["purchases"] == "block"
        and rules["web"] == "block"
    )
    tools = tools_for(rules)
    assert "web_search" not in tools and "file_write" in tools
    assert "workspace" not in tools and "workspace" in tools_for(rules, ["workspace"])
    assert not any(
        t in tools_for(rules, ["messages", "purchases"])
        for t in ("whatsapp_send", "channel_send")
    )


def test_create_introduces_itself_and_gets_a_computer(tmp_path):
    worker, _ = _worker(tmp_path, [])
    node = worker.create("Ana", "Vigila pisos en alquiler")
    assert node.primary and node.id.startswith("n_")
    assert worker.store.messages(node.id)[0]["text"] == "Hola, soy Ana."
    assert worker.store.computer(node.id).is_dir()
    second = worker.create("Leo")
    assert not second.primary
    with pytest.raises(NodeError):
        worker.create("  ")
    assert worker.store.get("../etc") is None


def test_a_turn_logs_activity_remembers_and_asks_for_approval(tmp_path):
    answer = (
        "Encontré 3 pisos y le dejé la tabla en su computadora.\n"
        "<recordar>Busca pisos de 2 habitaciones en Cuenca</recordar>"
        '<aprobacion categoria="messages">Enviar un correo al casero del piso 2</aprobacion>'
    )
    worker, seen = _worker(tmp_path, [answer])
    node = worker.create("Ana", "Vigila pisos")
    worker.send(node.id, "Busca pisos")
    worker.wait(node.id)
    prompt, tools = seen[0]
    assert "Vigila pisos" in prompt and str(worker.store.computer(node.id)) in prompt
    assert "whatsapp_send" not in tools
    kinds = [a["kind"] for a in worker.store.activity(node.id)]
    assert (
        kinds[:2] == ["created", "started"] and "tool" in kinds and "approval" in kinds
    )
    assert "2 habitaciones" in worker.store.memory(node.id)
    reply = worker.store.messages(node.id)[-1]
    assert reply["role"] == "node" and "<" not in reply["text"]
    node = worker.store.get(node.id)
    assert node.status == "waiting_approval"
    pending = worker.store.approvals(node.id)[0]
    worker.decide(node.id, pending["id"], True)  # messages: never sent by a Node
    assert "para que usted lo haga" in worker.store.messages(node.id)[-1]["text"]
    assert worker.store.get(node.id).status == "idle"
    with pytest.raises(NodeError):
        worker.decide(node.id, pending["id"], True)


def test_approved_workspace_action_runs_once_with_that_tool(tmp_path):
    worker, seen = _worker(
        tmp_path,
        [
            '<aprobacion categoria="workspace">Crear la página «Pisos»</aprobacion>',
            "Página creada.",
        ],
    )
    node = worker.create("Ana")
    worker.send(node.id, "Organízalo")
    worker.wait(node.id)
    item = worker.store.approvals(node.id)[0]
    worker.decide(node.id, item["id"], True)
    worker.wait(node.id)
    assert "workspace" in seen[-1][1] and "workspace" not in seen[0][1]
    assert worker.store.messages(node.id)[-1]["text"] == "Página creada."


def test_take_over_and_hand_back(tmp_path):
    worker, seen = _worker(
        tmp_path,
        ["<usuario>Inicie sesión en https://idealista.test</usuario>", "Sigo."],
    )
    node = worker.create("Ana")
    worker.send(node.id, "Mira mis favoritos")
    worker.wait(node.id)
    node = worker.store.get(node.id)
    assert node.status == "needs_you" and "idealista" in node.waiting
    worker.hand_back(node.id)
    worker.wait(node.id)
    assert "ya hizo lo que pediste" in seen[-1][0]
    assert worker.store.get(node.id).status == "idle"


def test_emergency_stop_pauses_and_discards(tmp_path):
    worker, _ = _worker(tmp_path, [])
    node = worker.create("Ana")
    assert worker.stop(node.id)
    assert worker.store.get(node.id).status == "paused"
    worker.store.add_routine(node.id, {"task": "revisa", "every_minutes": 15})
    assert worker.tick(time.time() + 3600) == 0  # paused: routines wait
    worker.resume(node.id)
    assert worker.tick(time.time() + 3600) == 1
    worker.wait(node.id)


def test_routines_are_due_on_time():
    every = Routine(id="r", task="t", every_minutes=30, last_run=1000.0)
    assert not every.due(1000 + 29 * 60) and every.due(1000 + 30 * 60)
    lt = time.localtime()
    at = Routine(id="r", task="t", at="00:00", days=[])
    assert at.due(time.time())
    at.last_run = time.time()
    assert not at.due(time.time())
    other_day = Routine(id="r", task="t", at="00:00", days=[(lt.tm_wday + 1) % 7])
    assert not other_day.due(time.time())


def test_parse_answer():
    out = parse_answer(
        "Hola <usuario>entra</usuario> <recordar>a</recordar><aprobacion>b</aprobacion>"
    )
    assert (
        out["say"] == "Hola" and out["user"] == ["entra"] and out["remember"] == ["a"]
    )
    assert out["approvals"] == [("messages", "b")]


def test_routes(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server import nodes_routes

    app = FastAPI()
    app.include_router(nodes_routes.router)
    worker, _ = _worker(tmp_path, ["Listo, guardé informe.md"])
    app.state.node_worker = worker
    c = TestClient(app)
    assert c.get("/v1/nodes/rules").json()["rules"][0]["key"] == "web"
    node = c.post("/v1/nodes", json={"name": "Ana", "instructions": "x"}).json()
    nid = node["id"]
    assert node["primary"] and node["unread"] >= 0
    c.post(f"/v1/nodes/{nid}/messages", json={"text": "hola"})
    worker.wait(nid)
    said = c.get(f"/v1/nodes/{nid}/messages").json()["messages"][-1]["text"]
    # It claimed a file it never wrote: code says so (no silent hallucination).
    assert (
        said.startswith("Listo, guardé informe.md")
        and "no encuentro en mi computadora «informe.md»" in said
    )
    assert c.get(f"/v1/nodes/{nid}/activity").json()["activity"]
    (worker.store.computer(nid) / "informe.md").write_text("# hola")
    files = c.get(f"/v1/nodes/{nid}/computer").json()["files"]
    assert files[0]["path"] == "informe.md"
    assert (
        c.get(f"/v1/nodes/{nid}/computer/file", params={"path": "informe.md"}).text
        == "# hola"
    )
    assert (
        c.get(
            f"/v1/nodes/{nid}/computer/file", params={"path": "../node.json"}
        ).status_code
        == 404
    )
    assert c.put(f"/v1/nodes/{nid}/memory", json={"text": "- le gusta el café"}).json()[
        "text"
    ]
    r = c.post(
        f"/v1/nodes/{nid}/routines",
        json={"task": "revisa", "at": "08:30", "days": [0, 1]},
    )
    assert r.json()["routines"][0]["at"] == "08:30"
    assert (
        c.post(
            f"/v1/nodes/{nid}/routines", json={"task": "x", "at": "99:00"}
        ).status_code
        == 400
    )
    assert (
        c.patch(f"/v1/nodes/{nid}", json={"rules": {"messages": "allow"}}).json()[
            "rules"
        ]["messages"]
        == "ask"
    )
    assert c.post(f"/v1/nodes/{nid}/stop").json()["status"] == "paused"
    assert c.delete(f"/v1/nodes/{nid}").json()["deleted"]
    assert c.get(f"/v1/nodes/{nid}").status_code == 404

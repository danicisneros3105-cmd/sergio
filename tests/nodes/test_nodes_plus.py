"""Nodes, Muse + Dots: faces, tone, apps with read/write, threads, triggers,
code-run actions (CLI, MCP, API on the Dev plan), swarm delegation, checks."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from openjarvis.nodes import connections, skills
from openjarvis.nodes.store import (
    CAST,
    CAST_LOOK,
    NodeError,
    NodeStore,
    clean_apps,
    clean_avatar,
    clean_routine,
    random_avatar,
)
from openjarvis.nodes.worker import NodeWorker, parse_answer, unverified_files


def _worker(tmp_path, answers, **kw):
    seen: list[tuple[str, list[str]]] = []

    def runner(prompt, tools, budget, on_tool):
        seen.append((prompt, list(tools)))
        return (answers.pop(0) if answers else "Hecho."), 1

    worker = NodeWorker(
        NodeStore(tmp_path),
        runner=runner,
        ask=lambda p, **k: {"presentacion": "Hola."},
        **kw,
    )
    return worker, seen


def test_the_cast_is_fixed_and_cannot_be_designed():
    # only WHICH character it is can be chosen; its colour, clothes and eyes
    # are always its own
    glove = clean_avatar(
        {"shape": "glove", "color": "#ff0000", "accessory": "crown", "eyes": "googly"}
    )
    assert glove == CAST_LOOK["glove"]
    # an older custom shape becomes one of the four, the same one every time
    old = {"shape": "frog", "color": "#8fd14f", "accessory": "beret", "eyes": "happy"}
    first = clean_avatar(None, old)
    assert first["shape"] in CAST and first == clean_avatar(None, old)
    assert first == CAST_LOOK[first["shape"]]
    # an unknown shape from the outside is ignored, never kept
    assert clean_avatar({"shape": "star"}, CAST_LOOK["orb"]) == CAST_LOOK["orb"]
    # a new Node always gets a member of the cast
    assert all(random_avatar(f"n{i}")["shape"] in CAST for i in range(20))


def test_face_tone_and_apps_are_checked():
    assert clean_apps(["gmail", "bad app!"]) == {"gmail": "read"}
    assert clean_apps({"gmail": "write", "slack": "admin"}) == {"gmail": "write"}
    with pytest.raises(NodeError):
        clean_routine({"kind": "web", "task": "x", "url": "ftp://nope"})
    r = clean_routine(
        {
            "kind": "app",
            "task": "x",
            "app": "gmail",
            "keywords": ["urgente"],
            "every_minutes": 5,
        }
    )
    assert r.every_minutes == 15 and r.keywords == ["urgente"]


def test_template_creates_a_ready_node(tmp_path):
    worker, seen = _worker(tmp_path, [])
    node = worker.create("Mía", template="correo")
    assert node.avatar["shape"] == "glove" and node.apps == {
        "gmail": "read",
        "gcalendar": "read",
    }
    kinds = sorted(r.kind for r in node.routines)
    assert kinds == ["app", "time"]
    assert "correo" in node.instructions.lower()


def test_threads_keep_conversations_apart(tmp_path):
    worker, seen = _worker(tmp_path, ["En el hilo 2."])
    node = worker.create("Ana", tone="breve")
    thread = worker.store.add_thread(node.id, "Viaje")
    worker.send(node.id, "Planea el viaje", thread=thread["id"])
    worker.wait(node.id)
    assert "muy breve" in seen[0][0]
    assert [m["text"] for m in worker.store.messages(node.id, thread=thread["id"])] == [
        "Planea el viaje",
        "En el hilo 2.",
    ]
    assert all(
        m.get("thread") == "main" for m in worker.store.messages(node.id, thread="main")
    )
    worker.send(node.id, "hola", thread="t_nope")  # unknown thread → the main one
    worker.wait(node.id)
    assert worker.store.messages(node.id, thread="main")[-2]["text"] == "hola"


def test_actions_are_parsed_and_tags_never_shown():
    out = parse_answer(
        'Voy. <cli>git status</cli> <mcp servidor="docs" herramienta="buscar">{"q": "x"}</mcp>'
        ' <api nombre="crm" metodo="post" ruta="/clientes">{"a": 1}</api> <enjambre>50 contratos</enjambre>'
    )
    assert out["say"] == "Voy."
    kinds = [a["kind"] for a in out["actions"]]
    assert kinds == ["cli", "mcp", "api", "swarm"]
    assert (
        out["actions"][2]["method"] == "POST"
        and out["actions"][1]["args"] == '{"q": "x"}'
    )


def test_cli_allow_list_runs_by_code_and_result_goes_back(tmp_path):
    worker, seen = _worker(tmp_path, ["<cli>python -c print(6*7)</cli>", "Salió 42."])
    node = worker.create("Dev")
    worker.store.update(node.id, rules={"cli": "allow"})
    worker.store.add_connection(node.id, "cli", {"name": "py", "command": "python"})
    worker.send(node.id, "calcula")
    worker.wait(node.id)
    assert "Resultados reales" in seen[-1][0] and "42" in seen[-1][0]
    assert worker.store.messages(node.id)[-1]["text"] == "Salió 42."


def test_cli_refuses_what_was_not_allowed(tmp_path):
    store = NodeStore(tmp_path)
    node = store.create("Dev")
    store.add_connection(node.id, "cli", {"name": "git", "command": "git status"})
    node = store.get(node.id)
    assert connections.cli_entry(node, "git status --short")["argv"] == [
        "git",
        "status",
        "--short",
    ]
    for bad in (
        "git push",
        "ls; rm -rf /",
        "cat x | sh",
        "curl x",
        "git status && reboot",
    ):
        with pytest.raises(NodeError):
            connections.cli_entry(node, bad)
    with pytest.raises(NodeError):
        store.add_connection(node.id, "cli", {"name": "bash", "command": "bash"})


def test_cli_asks_first_when_the_rule_says_so_and_runs_exactly_that(tmp_path):
    worker, seen = _worker(tmp_path, ["<cli>python --version</cli>", "Versión vista."])
    node = worker.create("Dev")  # cli: ask by default
    worker.store.add_connection(node.id, "cli", {"name": "py", "command": "python"})
    worker.send(node.id, "¿qué python hay?")
    worker.wait(node.id)
    item = worker.store.approvals(node.id)[0]
    assert item["action"] == {"kind": "cli", "command": "python --version"}
    assert worker.store.get(node.id).status == "waiting_approval"
    worker.decide(node.id, item["id"], True)
    worker.wait(node.id)
    assert "Python" in seen[-1][0]
    assert worker.store.messages(node.id)[-1]["text"] == "Versión vista."


def test_api_is_dev_plan_only_confined_and_never_leaks_the_key(tmp_path, monkeypatch):
    store = NodeStore(tmp_path)
    node = store.create("Dev")
    store.add_connection(
        node.id,
        "api",
        {"name": "crm", "base_url": "https://api.test/v1", "prefix": "Bearer"},
        secret="s3cret",
    )
    node = store.get(node.id)
    assert "s3cret" not in json.dumps(node.to_dict())
    entry = connections.api_entry(node, "crm")
    assert (
        connections.api_url(entry, "/clients?x=1") == "https://api.test/v1/clients?x=1"
    )
    for bad in ("https://evil.test/x", "//evil.test/x", "../../admin"):
        with pytest.raises(NodeError):
            connections.api_url(entry, bad)
    monkeypatch.setattr(connections, "api_allowed", lambda: False)
    with pytest.raises(NodeError):
        connections.run_api(store, node, "crm", "GET", "/clients")
    monkeypatch.setattr(connections, "api_allowed", lambda: True)
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, text='{"echo": "s3cret", "n": 2}')

    out = connections.run_api(
        store,
        node,
        "crm",
        "GET",
        "/clients",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert seen["auth"] == "Bearer s3cret" and "s3cret" not in out and '"n": 2' in out


def test_changing_data_through_an_api_always_asks(tmp_path, monkeypatch):
    monkeypatch.setattr(connections, "api_allowed", lambda: True)
    worker, _ = _worker(
        tmp_path, ['<api nombre="crm" metodo="DELETE" ruta="/clients/1"/>']
    )
    node = worker.create("Dev")
    worker.store.update(node.id, rules={"api": "allow"})
    worker.store.add_connection(
        node.id, "api", {"name": "crm", "base_url": "https://api.test"}
    )
    worker.send(node.id, "borra el cliente 1")
    worker.wait(node.id)
    assert worker.store.approvals(node.id)[0]["action"]["method"] == "DELETE"


def test_mcp_runs_through_code(tmp_path, monkeypatch):
    class Fake:
        def call_tool(self, name, args):
            return {"content": [{"type": "text", "text": f"{name}:{args['q']}"}]}

        def close(self):
            pass

    monkeypatch.setattr(connections, "_mcp_client", lambda entry: Fake())
    worker, seen = _worker(
        tmp_path,
        [
            '<mcp servidor="docs" herramienta="buscar">{"q": "sergio"}</mcp>',
            "Encontrado.",
        ],
    )
    node = worker.create("Leo")
    worker.store.update(node.id, rules={"mcp": "allow"})
    worker.store.add_connection(
        node.id, "mcp", {"name": "docs", "command": "docs-server"}
    )
    worker.send(node.id, "busca")
    worker.wait(node.id)
    assert "buscar:sergio" in seen[-1][0]


def test_swarm_delegation_brings_the_report_back(tmp_path):
    class Run:
        id, status, report, error = "sw_1", "running", "", ""

    class Swarm:
        def __init__(self):
            self.run = Run()

        def start(self, task):
            self.task = task
            return self.run

    swarm = Swarm()
    worker, seen = _worker(
        tmp_path,
        ["<enjambre>lee 50 contratos</enjambre>", "Resumen listo."],
        swarm=swarm,
    )
    node = worker.create("Leo")
    worker.store.update(node.id, rules={"swarm": "allow"})
    worker.send(node.id, "revisa los contratos")
    worker.wait(node.id)
    assert swarm.task == "lee 50 contratos"
    assert "Lancé un Agent Swarm" in worker.store.messages(node.id)[-1]["text"]
    swarm.run.report, swarm.run.status = "# Informe\nTodo en orden.", "done"
    for _ in range(100):
        if len(seen) >= 2:
            break
        time.sleep(0.05)
    worker.wait(node.id)
    assert "Todo en orden" in seen[-1][0]


def test_web_watch_wakes_only_on_a_real_change(tmp_path):
    pages = [
        "Producto\nPrecio: 120 €",
        "Producto\nPrecio: 120 €",
        "Producto\nPrecio: 99 €",
    ]
    worker, seen = _worker(tmp_path, ["Bajó a 99 €."], fetch=lambda url: pages.pop(0))
    node = worker.create("Cazador")
    routine = worker.store.add_routine(
        node.id, {"kind": "web", "task": "¿bajó?", "url": "https://tienda.test/p"}
    )
    assert worker.check_now(node.id, routine.id) == {"woke": False}  # reference copy
    assert worker.check_now(node.id, routine.id) == {
        "woke": False
    }  # same page: no model call
    assert seen == []
    out = worker.check_now(node.id, routine.id)
    assert out["woke"] and "99" in out["change"] and "120" in out["change"]
    worker.wait(node.id)
    assert "comprobado por código" in seen[0][0]


def test_app_trigger_needs_access_and_only_wakes_on_new_items(tmp_path):
    calls = []

    def items(app, since, keywords):
        calls.append((app, keywords))
        return (
            []
            if len(calls) == 1
            else [
                {
                    "id": "1",
                    "title": "URGENTE: factura",
                    "author": "Banco",
                    "time": "2026-10-11T10:00",
                    "url": "",
                    "snippet": "pague hoy",
                }
            ]
        )

    worker, seen = _worker(tmp_path, ["Es urgente: borrador listo."], app_items=items)
    node = worker.create("Mía")
    with pytest.raises(NodeError):
        worker.store.add_routine(node.id, {"kind": "app", "app": "gmail", "task": "x"})
    worker.store.update(node.id, apps={"gmail": "read"})
    routine = worker.store.add_routine(
        node.id,
        {"kind": "app", "app": "gmail", "keywords": ["urgente"], "task": "¿urgente?"},
    )
    assert worker.check_now(node.id, routine.id)["woke"] is False
    assert worker.check_now(node.id, routine.id)["woke"] is True
    worker.wait(node.id)
    assert "URGENTE: factura" in seen[0][0] and calls[0] == ("gmail", ["urgente"])


def test_unverified_files():
    assert unverified_files(
        "Guardé el informe en `informe.md` y la tabla en datos.csv", ["informe.md"]
    ) == ["datos.csv"]
    assert unverified_files("Te cuento que el archivo informe.md existe", []) == []


def test_skills_prices_and_diffs():
    assert skills.prices("Antes 1.299,00 € ahora $1,099.50") == [1299.0, 1099.5]
    added, removed = skills.changes("a\nb", "a\nc")
    assert added == ["c"] and removed == ["b"]


def test_catalog_and_connections_routes(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server import nodes_routes

    app = FastAPI()
    app.include_router(nodes_routes.router)
    worker, _ = _worker(tmp_path, [])
    app.state.node_worker = worker
    c = TestClient(app)
    cat = c.get("/v1/nodes/catalog").json()
    assert (
        cat["shapes"] == list(CAST)
        and cat["templates"][0]["id"] == "vigia"
        and "api_allowed" in cat
    )
    refused = c.post(
        "/v1/nodes",
        json={"name": "Vigía", "template": "vigia", "avatar": {"shape": "star"}},
    )
    assert refused.status_code == 400 and "equipo fijo" in refused.json()["detail"]
    assert [m["name"] for m in cat["team"]] == ["Rihno", "Manchas", "Hous", "Tennessee"]
    worker.store.ensure_team()
    node = next(
        n for n in c.get("/v1/nodes").json()["nodes"] if n["name"] == "Tennessee"
    )
    # its character is fixed: the invisible orb, whatever anyone asks
    assert node["avatar"] == CAST_LOOK["orb"] and node["team"] == "tennessee"
    assert c.delete(f"/v1/nodes/{node['id']}").status_code == 400
    nid = node["id"]
    assert (
        c.post(
            f"/v1/nodes/{nid}/connections/cli",
            json={"name": "git", "command": "git log"},
        ).status_code
        == 200
    )
    monkeypatch.setattr(connections, "api_allowed", lambda: False)
    r = c.post(
        f"/v1/nodes/{nid}/connections/api",
        json={"name": "crm", "base_url": "https://api.test", "secret": "k"},
    )
    assert r.status_code == 402 and "Dev" in r.json()["detail"]
    monkeypatch.setattr(connections, "api_allowed", lambda: True)
    body = c.post(
        f"/v1/nodes/{nid}/connections/api",
        json={"name": "crm", "base_url": "https://api.test", "secret": "k"},
    ).json()
    assert body["connections"]["api"][0][
        "has_secret"
    ] is True and "k" not in json.dumps(body["connections"])
    t = c.post(f"/v1/nodes/{nid}/threads", json={"title": "Viaje"}).json()["thread"]
    assert any(
        x["id"] == t["id"] for x in c.get(f"/v1/nodes/{nid}/threads").json()["threads"]
    )
    assert c.patch(
        f"/v1/nodes/{nid}", json={"tone": "formal", "apps": {"gmail": "write"}}
    ).json()["apps"] == {"gmail": "write"}

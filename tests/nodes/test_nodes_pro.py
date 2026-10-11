"""Codex's Nodes features on the joined Nodes: goals, notes, audit, reviewed
integrations and plan gates, without external services."""

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis import tiers
from openjarvis.agents.manager import AgentManager
from openjarvis.nodes.integrations import ReviewTickets, clean_env, run_connection
from openjarvis.nodes.records import RecordStore
from openjarvis.nodes.store import NodeStore
from openjarvis.nodes.worker import NodeWorker
from openjarvis.server.nodes_pro_routes import router
from openjarvis.server.nodes_routes import router as nodes_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    from openjarvis.server.nodes_pro_routes import _API_NAMES

    for key in _API_NAMES:
        monkeypatch.setenv(key, "")
    app = FastAPI()
    app.include_router(router)
    app.include_router(nodes_router)
    app.state.node_worker = NodeWorker(
        NodeStore(tmp_path / "nodes"),
        runner=lambda *a, **k: ("", 0),
        ask=lambda p, **k: {"presentacion": "Hola."},
    )
    app.state.nodes_records = RecordStore(tmp_path / "nodes.sqlite")
    app.state.agent_manager = AgentManager(str(tmp_path / "agents.sqlite"))
    with TestClient(app) as client:
        yield client
    if hasattr(app.state, "nodes_mcp_sessions"):
        app.state.nodes_mcp_sessions.close_all()
    app.state.nodes_records.close()
    app.state.agent_manager.close()


def test_presets_never_install_or_execute_and_require_local_program(
    client, monkeypatch
):
    from openjarvis.nodes import catalog

    monkeypatch.setattr(catalog.shutil, "which", lambda _: None)
    n = node(client)
    result = client.get("/v1/nodes/integration-presets").json()["presets"]
    assert {p["id"] for p in result} == {"browser-use", "openclaw"}
    assert not any(p["available"] for p in result)
    assert (
        client.post(
            f"/v1/nodes/{n}/integration-presets", json={"preset_id": "browser-use"}
        ).status_code
        == 409
    )
    assert not client.get(f"/v1/nodes/{n}/integrations").json()["integrations"]
    monkeypatch.setattr(catalog.shutil, "which", lambda _: "/installed/browser-use")
    spec = client.post(
        f"/v1/nodes/{n}/integration-presets", json={"preset_id": "browser-use"}
    ).json()
    assert spec["command"] == ["/installed/browser-use", "--mcp"]
    assert spec["session_mode"] == "persistent" and spec["policy"] == "confirm"


def _stateful_mcp(tmp_path):
    server = tmp_path / "stateful.py"
    server.write_text("""import json,sys,os
value = "initial"
for line in sys.stdin:
    request=json.loads(line)
    if "id" not in request: continue
    method=request["method"]
    if method == "initialize":
        result={"protocolVersion":"2025-03-26", "capabilities":{"tools":{}}, "serverInfo":{"name":"test","version":"1"}}
    elif method == "tools/list":
        result={"tools":[{"name":"state","description":"Stateful test", "inputSchema":{"type":"object"}}]}
    else:
        args=request["params"].get("arguments",{})
        value=args.get("value",value)
        result={"content":[{"type":"text","text":value}], "pid":os.getpid()}
    print(json.dumps({"jsonrpc":"2.0", "id":request["id"], "result":result}),flush=True)
""")
    return {
        "kind": "mcp",
        "command": [sys.executable, str(server)],
        "session_mode": "persistent",
    }


def test_reviewed_mcp_preserves_state_and_invalidates_stale_actions(client, tmp_path):
    n = node(client)
    conn = client.post(
        f"/v1/nodes/{n}/integrations",
        json={"name": "Browser fixture", **_stateful_mcp(tmp_path)},
    ).json()
    endpoint = f"/v1/nodes/{n}/integrations/{conn['id']}"

    def reviewed(action):
        ticket = client.post(endpoint + "/review", json=action).json()["ticket"]
        return client.post(endpoint + "/execute", json={**action, "ticket": ticket})

    assert reviewed({}).json()["session_active"]
    action = {"tool": "state", "tool_arguments": {"value": "page one"}}
    assert reviewed(action).json()["result"]["content"][0]["text"] == "page one"
    stale = client.post(endpoint + "/review", json={"tool": "state"}).json()["ticket"]
    assert (
        reviewed({"tool": "state"}).json()["result"]["content"][0]["text"] == "page one"
    )
    assert (
        client.post(
            endpoint + "/execute", json={"tool": "state", "ticket": stale}
        ).status_code
        == 403
    )
    ticket = client.post(endpoint + "/review", json={"tool": "state"}).json()["ticket"]
    client.post(endpoint + "/close-session")
    assert (
        client.post(
            endpoint + "/execute", json={"tool": "state", "ticket": ticket}
        ).status_code
        == 403
    )
    assert (
        reviewed({"tool": "state"}).json()["result"]["content"][0]["text"] == "initial"
    )
    client.patch(
        endpoint,
        json={
            "name": conn["name"],
            "kind": "mcp",
            "command": conn["command"],
            "session_mode": "persistent",
            "policy": "block",
        },
    )
    assert client.post(endpoint + "/review", json={}).status_code == 403
    assert not client.app.state.nodes_mcp_sessions._sessions


def test_mcp_sessions_capacity_idle_cleanup_and_revision_race(tmp_path):
    import time

    from openjarvis.nodes.sessions import MCPSessions, SessionBusy

    pool = MCPSessions(idle_seconds=0.15, capacity=1)
    spec = _stateful_mcp(tmp_path)
    try:
        revision = pool.revision()
        result = pool.run(("a", "1"), spec, "state", {"value": "persisted"}, revision)
        assert result["session_active"]
        with pytest.raises(PermissionError):
            pool.run(("a", "1"), spec, "state", {}, revision)
        with pytest.raises(SessionBusy):
            pool.run(("b", "2"), spec, "state", {})
        deadline = time.monotonic() + 3
        while pool._sessions and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not pool._sessions
        result = pool.run(("b", "2"), spec, "state", {})
        assert result["result"]["content"][0]["text"] == "initial"
    finally:
        pool.close_all()


def test_native_workflows_have_real_dependency_order_and_accounting():
    from openjarvis.agents._stubs import AgentResult
    from openjarvis.agents.workflows import run_workflow

    prompts = []

    def run(prompt):
        prompts.append(prompt)
        return AgentResult(
            content=f"evidence {len(prompts)}",
            turns=2,
            metadata={"total_tokens": 5, "cost": 0.1},
        )

    result = run_workflow("Review Python", "sequential", run)
    assert len(prompts) == 3
    assert "evidence 1" in prompts[1]
    assert "evidence 1" in prompts[2] and "evidence 2" in prompts[2]
    assert result.metadata["total_tokens"] == 15 and result.turns == 6
    assert result.metadata["cost"] == pytest.approx(0.3)
    assert result.metadata["verified"] is False


def test_parallel_experts_are_independent_and_failed_expert_blocks_synthesis():
    from openjarvis.agents._stubs import AgentResult
    from openjarvis.agents.workflows import run_workflow

    barrier = threading.Barrier(2)
    prompts = []

    def run(prompt):
        prompts.append(prompt)
        if "Objetivo:" in prompt:
            barrier.wait(timeout=2)
            assert "expert output" not in prompt
            return AgentResult(content="expert output")
        assert prompt.count("expert output") == 2
        return AgentResult(content="synthesis")

    assert run_workflow("goal", "parallel_review", run).content == "synthesis"
    assert len(prompts) == 3
    calls = []

    def failed(prompt):
        calls.append(prompt)
        return AgentResult(content="denied", metadata={"security_denied": True})

    with pytest.raises(RuntimeError):
        run_workflow("goal", "parallel_review", failed)
    assert len(calls) == 2
    with pytest.raises(ValueError):
        run_workflow("x" * 12001, "parallel_review", failed)


def test_goal_workflow_reaches_executor_and_recurring_failures_pause(
    client, monkeypatch
):
    from unittest.mock import Mock

    from openjarvis.agents._stubs import AgentResult
    from openjarvis.agents.errors import RetryableError
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.core.events import EventBus

    client.app.state.agent_scheduler = Mock()
    n = node(client, interval_minutes=5)
    goal = client.post(
        f"/v1/nodes/{n}/goals",
        json={"text": "Check docs", "scheduled": True, "workflow": "sequential"},
    ).json()
    manager = client.app.state.agent_manager
    executor = AgentExecutor(manager, EventBus())
    calls = []
    monkeypatch.setattr(
        executor,
        "_run_with_retries",
        lambda agent: (
            calls.append(agent["config"]["instruction"])
            or AgentResult(content="proposal")
        ),
    )
    executor.execute_tick(goal["agent_id"])
    assert len(calls) == 3

    def fail(_):
        raise RetryableError("temporary test error")

    monkeypatch.setattr(executor, "_run_with_retries", fail)
    for _ in range(3):
        executor.execute_tick(goal["agent_id"])
    assert manager.get_agent(goal["agent_id"])["status"] == "paused"
    task = manager.list_tasks(goal["agent_id"])[0]
    assert task["progress"]["consecutive_failures"] == 3
    assert client.post(f"/v1/nodes/{n}/goals/resume").status_code == 200
    assert (
        manager.list_tasks(goal["agent_id"])[0]["progress"]["consecutive_failures"] == 0
    )


def node(client, interval_minutes=0, **fields):
    response = client.post("/v1/nodes", json={"name": "Lumen", **fields})
    assert response.status_code == 200
    nid = response.json()["id"]
    if interval_minutes:
        settings = client.patch(
            f"/v1/nodes/{nid}/goal-settings",
            json={"interval_minutes": interval_minutes},
        )
        assert settings.status_code == 200
    return nid


def test_profile_memory_forget_goals_and_audit(client):
    n = node(client)
    other = node(client, name="Bruma")
    note = client.post(
        f"/v1/nodes/{n}/notes", json={"text": "Trabajo en Python", "source": "perfil"}
    ).json()
    assert client.get(f"/v1/nodes/{other}/notes").json()["memories"] == []
    client.delete(f"/v1/nodes/{other}/notes/{note['id']}")
    assert len(client.get(f"/v1/nodes/{n}/notes").json()["memories"]) == 1
    goal = client.post(
        f"/v1/nodes/{n}/goals", json={"text": "Busca documentación oficial"}
    ).json()
    assert goal["status"] == "pending"
    assert (
        client.get(f"/v1/nodes/{n}/goals").json()["goals"][0]["task_id"]
        == goal["task_id"]
    )
    client.delete(f"/v1/nodes/{n}/notes/{note['id']}")
    assert not client.get(f"/v1/nodes/{n}/notes").json()["memories"]
    events = client.get(f"/v1/nodes/{n}/audit").json()["events"]
    assert any(e["action"] == "delete:memory" for e in events)
    assert "Trabajo en Python" not in json.dumps(events)


def test_denied_single_agent_result_is_failed_not_a_successful_goal(
    client, monkeypatch
):
    from openjarvis.agents._stubs import AgentResult
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.core.events import EventBus

    n = node(client)
    goal = client.post(f"/v1/nodes/{n}/goals", json={"text": "Read docs"}).json()
    executor = AgentExecutor(client.app.state.agent_manager, EventBus())
    monkeypatch.setattr(
        executor,
        "_run_with_retries",
        lambda _: AgentResult(content="Denied", metadata={"security_denied": True}),
    )
    executor.execute_tick(goal["agent_id"])
    row = client.get(f"/v1/nodes/{n}/goals").json()["goals"][0]
    assert row["status"] == "failed"
    assert row["consecutive_failures"] == 1


def test_invalid_profile_and_scheduling_leave_no_partial_goal(client):
    n = node(client, interval_minutes=10)
    bad = client.patch(f"/v1/nodes/{n}/goal-settings", json={"interval_minutes": -1})
    assert bad.status_code == 422
    assert (
        client.post(
            f"/v1/nodes/{n}/goals", json={"text": "Scheduled", "scheduled": True}
        ).status_code
        == 503
    )
    assert client.get(f"/v1/nodes/{n}/goals").json()["goals"] == []
    assert client.app.state.agent_manager.list_agents() == []


def test_cli_requires_matching_one_time_review_and_revoke(client):
    n = node(client)
    conn = client.post(
        f"/v1/nodes/{n}/integrations",
        json={
            "name": "Python",
            "kind": "cli",
            "command": [sys.executable, "-c", 'print("REAL_OUTPUT")'],
        },
    ).json()
    endpoint = f"/v1/nodes/{n}/integrations/{conn['id']}"
    assert client.post(endpoint + "/execute", json={}).status_code == 403
    ticket = client.post(endpoint + "/review", json={}).json()["ticket"]
    result = client.post(endpoint + "/execute", json={"ticket": ticket})
    assert (
        result.status_code == 200 and result.json()["stdout"].strip() == "REAL_OUTPUT"
    )
    assert (
        client.post(endpoint + "/execute", json={"ticket": ticket}).status_code == 403
    )
    ticket = client.post(endpoint + "/review", json={}).json()["ticket"]
    assert (
        client.post(
            endpoint + "/execute", json={"ticket": ticket, "arguments": ["changed"]}
        ).status_code
        == 403
    )
    ticket = client.post(endpoint + "/review", json={}).json()["ticket"]
    client.delete(endpoint)
    assert (
        client.post(endpoint + "/execute", json={"ticket": ticket}).status_code == 404
    )


def test_dev_gate_with_real_signed_license_and_no_secret_response(
    client, tmp_path, monkeypatch
):
    from openjarvis.server import cloud_router

    target = tmp_path / "private.env"
    monkeypatch.setattr(cloud_router, "_CLOUD_ENV_FILE", target)
    key = {"name": "MOONSHOT_API_KEY", "value": "test-private-secret"}
    assert client.post("/v1/nodes/api-key", json=key).status_code == 403
    assert not target.exists()
    keys = tiers.generate_keypair()
    monkeypatch.setenv("SERGIO_LICENSE_PUBKEY", keys["public"])
    tiers.activate(tiers.issue(keys["private"], "pro", holder="Test"))
    assert client.post("/v1/nodes/api-key", json=key).status_code == 403
    tiers.activate(tiers.issue(keys["private"], "dev", holder="Test"))
    response = client.post("/v1/nodes/api-key", json=key)
    assert response.status_code == 200 and key["value"] not in response.text
    monkeypatch.delenv("MOONSHOT_API_KEY")
    assert key["value"] in target.read_text()
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600
    status = client.get("/v1/nodes/api-key/status")
    assert status.json()["MOONSHOT_API_KEY"] is True and key["value"] not in status.text


def test_approval_race_has_only_one_winner():
    tickets = ReviewTickets()
    payload = {"command": ["git", "--version"]}
    ticket = tickets.issue(payload)
    barrier = threading.Barrier(4)

    def consume(_):
        barrier.wait()
        try:
            tickets.consume(ticket, payload)
            return True
        except PermissionError:
            return False

    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(consume, range(4))) == 1


def test_connection_does_not_inherit_keys_and_output_is_bounded(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "never-inherit")
    monkeypatch.setenv("SystemRoot", "/fake/windows")
    assert "MOONSHOT_API_KEY" not in clean_env()
    assert clean_env()["SystemRoot"] == "/fake/windows"
    result = run_connection(
        {
            "kind": "cli",
            "command": [
                sys.executable,
                "-c",
                'import os; print(os.getenv("MOONSHOT_API_KEY")); print("x"*100000)',
            ],
        },
        [],
    )
    assert result["returncode"] == 0 and result["stdout"].startswith("None")
    assert result["truncated"] and len(result["stdout"]) <= 64000


def test_mcp_discovery_and_reviewed_call_use_real_stdio(tmp_path):
    server = tmp_path / "mcp.py"
    server.write_text("""import json,sys
for line in sys.stdin:
 r=json.loads(line)
 if "id" not in r: continue
 method=r["method"]
 if method=="initialize":
  result={"protocolVersion":"2024-11-05","capabilities":{},"serverInfo":{"name":"test","version":"1"}}
 elif method=="tools/list": result={"tools":[{"name":"echo","description":"Echo","inputSchema":{"type":"object"}}]}
 elif method=="tools/call": result={"content":[{"type":"text","text":r["params"]["arguments"]["text"]}],"isError":False}
 else: result={}
 print(json.dumps({"jsonrpc":"2.0","id":r["id"],"result":result}),flush=True)
""")
    spec = {"kind": "mcp", "command": [sys.executable, str(server)]}
    assert run_connection(spec, [])["tools"][0]["name"] == "echo"
    assert (
        run_connection(spec, [], "echo", {"text": "actual"})["result"]["content"][0][
            "text"
        ]
        == "actual"
    )


def test_goal_reaches_executor_and_is_not_declared_verified(client, monkeypatch):
    from openjarvis.agents._stubs import AgentResult
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.core.events import EventBus

    n = node(client)
    goal = client.post(
        f"/v1/nodes/{n}/goals", json={"text": "Encuentra documentación de asyncio"}
    ).json()
    executor = AgentExecutor(client.app.state.agent_manager, EventBus())
    inputs = []

    def run(agent):
        inputs.append(agent["config"]["instruction"])
        return AgentResult(content="Respuesta de prueba sin verificación de fuentes")

    monkeypatch.setattr(executor, "_run_with_retries", run)
    executor.execute_tick(goal["agent_id"])
    assert "documentación de asyncio" in inputs[0]
    row = client.get(f"/v1/nodes/{n}/goals").json()["goals"][0]
    assert row["status"] == "needs_review"
    assert row["findings"][0]["verified"] is False


def test_scheduled_goal_repeats_with_read_only_tools(client, monkeypatch):
    from unittest.mock import Mock

    from openjarvis.agents._stubs import AgentResult
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.core.events import EventBus

    client.app.state.agent_scheduler = Mock()
    n = node(client, interval_minutes=5)
    goal = client.post(
        f"/v1/nodes/{n}/goals", json={"text": "Comprueba fuentes", "scheduled": True}
    ).json()
    manager = client.app.state.agent_manager
    config = manager.get_agent(goal["agent_id"])["config"]
    assert config["schedule_value"] == 300
    assert set(config["tools"]) == {"web_search", "calculator", "think"}
    executor = AgentExecutor(manager, EventBus())
    inputs = []

    def run(agent):
        inputs.append(agent["config"]["instruction"])
        return AgentResult(content="Resultado")

    monkeypatch.setattr(executor, "_run_with_retries", run)
    executor.execute_tick(goal["agent_id"])
    executor.execute_tick(goal["agent_id"])
    assert len(inputs) == 2 and all("Comprueba fuentes" in x for x in inputs)


def test_key_revocation_remains_effective_after_restart(client, tmp_path, monkeypatch):
    from openjarvis.server import cloud_router

    target = tmp_path / "keys.env"
    target.write_text("# Sergio Nodes API\nMOONSHOT_API_KEY=updated-key\n")
    monkeypatch.setattr(cloud_router, "_CLOUD_ENV_FILE", target)
    monkeypatch.setenv("MOONSHOT_API_KEY", "old-desktop-key")
    assert cloud_router._load_keys()["MOONSHOT_API_KEY"] == "updated-key"
    assert (
        client.post(
            "/v1/nodes/api-key", json={"name": "MOONSHOT_API_KEY", "value": ""}
        ).status_code
        == 200
    )
    monkeypatch.setenv("MOONSHOT_API_KEY", "old-desktop-key")
    assert not cloud_router._load_keys()["MOONSHOT_API_KEY"]


def test_block_policy_cancels_an_existing_review(client):
    n = node(client)
    spec = {"name": "version", "kind": "cli", "command": [sys.executable, "--version"]}
    connection = client.post(f"/v1/nodes/{n}/integrations", json=spec).json()
    route = f"/v1/nodes/{n}/integrations/{connection['id']}"
    ticket = client.post(route + "/review", json={}).json()["ticket"]
    assert client.patch(route, json={**spec, "policy": "block"}).status_code == 200
    assert client.post(route + "/execute", json={"ticket": ticket}).status_code == 403
    assert client.post(route + "/review", json={}).status_code == 403


def test_idle_node_does_not_invoke_a_model(client, monkeypatch):
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.core.events import EventBus
    from openjarvis.server.nodes_pro_routes import _agent_config, find

    n = node(client)
    assert client.get("/v1/nodes").json()["nodes"][0]["id"] == n

    class _Request:
        app = client.app

    profile = find(_Request(), n)
    manager = client.app.state.agent_manager
    agent = manager.create_agent("Idle", config=_agent_config(profile))
    executor = AgentExecutor(manager, EventBus())
    calls = []
    monkeypatch.setattr(executor, "_run_with_retries", lambda *_: calls.append(True))
    executor.execute_tick(agent["id"])
    assert calls == []
    assert manager.get_agent(agent["id"])["status"] != "running"

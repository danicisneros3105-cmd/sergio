"""User flows, plan gates and executable boundaries without external services."""

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
from openjarvis.nodes.store import NodeStore
from openjarvis.server.nodes_routes import router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    from openjarvis.server.nodes_routes import _API_NAMES

    for key in _API_NAMES:
        monkeypatch.setenv(key, "")
    app = FastAPI()
    app.include_router(router)
    app.state.nodes_store = NodeStore(tmp_path / "nodes.sqlite")
    app.state.agent_manager = AgentManager(str(tmp_path / "agents.sqlite"))
    with TestClient(app) as client:
        yield client
    app.state.nodes_store.close()
    app.state.agent_manager.close()


def node(client, **fields):
    response = client.post("/v1/nodes", json={"name": "Lumen", **fields})
    assert response.status_code == 200
    return response.json()["id"]


def test_profile_memory_forget_goals_and_audit(client):
    n = node(client, fur=1, species="nival")
    other = node(client, name="Bruma")
    note = client.post(
        f"/v1/nodes/{n}/memory", json={"text": "Trabajo en Python", "source": "perfil"}
    ).json()
    assert client.get(f"/v1/nodes/{other}/memory").json()["memories"] == []
    client.delete(f"/v1/nodes/{other}/memory/{note['id']}")
    assert len(client.get(f"/v1/nodes/{n}/memory").json()["memories"]) == 1
    goal = client.post(
        f"/v1/nodes/{n}/goals", json={"text": "Busca documentación oficial"}
    ).json()
    assert goal["status"] == "pending"
    assert (
        client.get(f"/v1/nodes/{n}/goals").json()["goals"][0]["task_id"]
        == goal["task_id"]
    )
    client.delete(f"/v1/nodes/{n}/memory/{note['id']}")
    assert not client.get(f"/v1/nodes/{n}/memory").json()["memories"]
    events = client.get(f"/v1/nodes/{n}/audit").json()["events"]
    assert any(e["action"] == "delete:memory" for e in events)
    assert "Trabajo en Python" not in json.dumps(events)


def test_invalid_profile_and_scheduling_leave_no_partial_goal(client):
    assert client.post("/v1/nodes", json={"name": "x", "fur": 2}).status_code == 422
    n = node(client, interval_minutes=10)
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
        f"/v1/nodes/{n}/connections",
        json={
            "name": "Python",
            "kind": "cli",
            "command": [sys.executable, "-c", 'print("REAL_OUTPUT")'],
        },
    ).json()
    endpoint = f"/v1/nodes/{n}/connections/{conn['id']}"
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
    connection = client.post(f"/v1/nodes/{n}/connections", json=spec).json()
    route = f"/v1/nodes/{n}/connections/{connection['id']}"
    ticket = client.post(route + "/review", json={}).json()["ticket"]
    assert client.patch(route, json={**spec, "policy": "block"}).status_code == 200
    assert client.post(route + "/execute", json={"ticket": ticket}).status_code == 403
    assert client.post(route + "/review", json={}).status_code == 403


def test_idle_node_does_not_invoke_a_model(client, monkeypatch):
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.core.events import EventBus
    from openjarvis.server.nodes_routes import _agent_config

    n = node(client)
    profile = client.get("/v1/nodes").json()["nodes"][0]
    assert profile["id"] == n
    manager = client.app.state.agent_manager
    agent = manager.create_agent("Idle", config=_agent_config(profile))
    executor = AgentExecutor(manager, EventBus())
    calls = []
    monkeypatch.setattr(executor, "_run_with_retries", lambda *_: calls.append(True))
    executor.execute_tick(agent["id"])
    assert calls == []
    assert manager.get_agent(agent["id"])["status"] != "running"

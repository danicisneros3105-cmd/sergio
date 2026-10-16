"""/v1/mcp and the Claude-format plugin routes over HTTP."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
real = pytest.importorskip("real_servers")
warnings.filterwarnings("ignore")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    import openjarvis.mcp.hub as hub_module
    from openjarvis.server.hub_routes import router as hub_router
    from openjarvis.server.mcp_routes import router

    monkeypatch.setattr(
        hub_module,
        "_hub",
        hub_module.ConnectorHub(tmp_path / "connectors", approver=lambda *a: True),
    )
    app = FastAPI()
    app.include_router(router)
    app.include_router(hub_router)
    from openjarvis.server.auth_middleware import AuthMiddleware
    from openjarvis.server.mobile import RemoteAccessMiddleware

    app.add_middleware(AuthMiddleware, api_key="test-key")
    app.add_middleware(RemoteAccessMiddleware, api_key="test-key")
    return TestClient(
        app, base_url="http://localhost", headers={"Authorization": "Bearer test-key"}
    )


@pytest.fixture(scope="module")
def site():
    port = real.free_port()
    base = f"http://127.0.0.1:{port}"
    real.serve(
        real.oauth_server(base, real.MemoryProvider()).streamable_http_app(), port
    )
    yield base
    real.stop_all()


def test_directory_has_the_owners_picks(client):
    data = client.get("/v1/mcp/directory").json()
    ids = {c["id"] for c in data["connectors"]}
    assert {"gmail", "notion", "higgsfield"} <= ids
    assert "En su PC" in data["categories"]


def test_custom_connector_signs_in_through_the_callback_page(client, site):
    server = client.post(
        "/v1/mcp/servers", json={"name": "Protegido", "url": f"{site}/mcp"}
    ).json()["server"]
    started = client.post(f"/v1/mcp/servers/{server['id']}/connect").json()
    assert started["status"] == "needs_auth"
    assert (
        "redirect_uri=http%3A%2F%2Flocalhost%2Fv1%2Fmcp%2Foauth%2Fcallback"
        in started["auth_url"]
    )
    back = urlparse(
        httpx.get(started["auth_url"], follow_redirects=False).headers["location"]
    )
    page = client.get(
        f"/v1/mcp/oauth/callback?{back.query}",
        headers={"Authorization": "", "x-forwarded-for": "203.0.113.1"},
    )
    assert page.status_code == 200 and "Protegido conectado" in page.text
    listed = client.get("/v1/mcp/servers").json()["servers"][0]
    assert listed["status"] == "connected" and len(listed["tools"]) == 2
    out = client.post(
        f"/v1/mcp/servers/{server['id']}/call",
        json={"tool": "sumar", "arguments": {"a": 1, "b": 2}},
    )
    assert out.json()["content"][0]["text"] == "3"
    client.post(
        f"/v1/mcp/servers/{server['id']}/permissions", json={"permission": "block"}
    )
    blocked = client.post(
        f"/v1/mcp/servers/{server['id']}/call", json={"tool": "sumar", "arguments": {}}
    )
    assert blocked.status_code == 400 and "no permite" in blocked.json()["detail"]


def test_callback_with_a_bad_state_says_so(client):
    page = client.get("/v1/mcp/oauth/callback?state=x&code=y")
    assert page.status_code == 400 and "ya no es válido" in page.text


def test_claude_plugin_marketplace_from_a_local_folder(client, tmp_path):
    market = tmp_path / "market"
    plugin = market / "plugins" / "demo"
    (market / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / "skills" / "saludo").mkdir(parents=True)
    (plugin / "commands").mkdir()
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "prueba",
                "plugins": [
                    {
                        "name": "demo",
                        "source": "./plugins/demo",
                        "description": "Un demo",
                    }
                ],
            }
        )
    )
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "demo", "version": "1.0.0"})
    )
    (plugin / "skills" / "saludo" / "SKILL.md").write_text(
        "---\nname: saludo\ndescription: Saluda\n---\nDi hola.\n"
    )
    (plugin / "commands" / "resumen.md").write_text(
        "---\ndescription: Resume el día\n---\nResume el día del señor.\n"
    )
    (plugin / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "notas": {"type": "http", "url": "https://mcp.ejemplo.com/mcp"}
                }
            }
        )
    )

    assert client.post("/v1/hub/marketplaces", json={"source": str(market)}).json() == {
        "name": "prueba",
        "plugins": 1,
    }
    listed = client.get("/v1/hub/claude-plugins?q=demo").json()["available"]
    assert listed[0]["id"] == "demo@prueba" and not listed[0]["installed"]
    info = client.post(
        "/v1/hub/claude-plugins/install", json={"id": "demo@prueba"}
    ).json()["plugin"]
    assert info["skills"] == ["saludo", "resumen"] and info["connectors"] == ["notas"]
    skills_dir = tmp_path / "skills" / info["skill_root"]
    assert (skills_dir / "saludo" / "SKILL.md").exists() and (
        skills_dir / "resumen" / "SKILL.md"
    ).exists()
    client.post(
        "/v1/hub/claude-plugins/enabled?enabled=false", json={"id": "demo@prueba"}
    )
    assert not skills_dir.exists()
    assert client.get("/v1/mcp/servers").json()["servers"][0]["status"] == "disabled"
    client.post("/v1/hub/claude-plugins/remove", json={"id": "demo@prueba"})
    assert client.get("/v1/mcp/servers").json()["servers"] == []

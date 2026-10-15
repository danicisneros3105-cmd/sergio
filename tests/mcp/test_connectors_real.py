"""Connectors against real MCP servers built with the official SDK.

The remote one signs in exactly like Notion's or Linear's: 401 + resource
metadata, dynamic client registration, PKCE, token, refresh.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from openjarvis.mcp.hub import ConnectorError, ConnectorHub, tool_name

sys.path.insert(0, str(Path(__file__).parent))
real = pytest.importorskip("real_servers")

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def oauth_site():
    port = real.free_port()
    base = f"http://127.0.0.1:{port}"
    provider = real.MemoryProvider()
    app = real.oauth_server(base, provider).streamable_http_app()
    real.serve(app, port)
    yield base, provider
    real.stop_all()


@pytest.fixture(scope="module")
def open_site():
    port = real.free_port()
    real.serve(real.tool_server().streamable_http_app(), port)
    yield f"http://127.0.0.1:{port}/mcp"


def _sign_in(hub: ConnectorHub, server_id: str) -> dict:
    """What the browser does: open the service page, follow it back to Sergio."""
    started = hub.connect(server_id, "http://localhost:8000/v1/mcp/oauth/callback")
    assert started["status"] == "needs_auth"
    page = httpx.get(started["auth_url"], follow_redirects=False)
    back = urlparse(page.headers["location"])
    assert back.path == "/v1/mcp/oauth/callback"
    query = parse_qs(back.query)
    assert query["state"][0] == started["state"]
    return hub.finish(query["state"][0], query["code"][0])


def test_remote_connector_signs_in_and_uses_tools(tmp_path, oauth_site):
    base, provider = oauth_site
    hub = ConnectorHub(tmp_path, approver=lambda what, payload: True)
    server = hub.add_remote("Protegido", f"{base}/mcp")
    assert server["status"] == "needs_auth"

    connected = _sign_in(hub, server["id"])
    assert connected["status"] == "connected"
    names = {t["name"]: t for t in connected["tools"]}
    assert set(names) == {"sumar", "borrar_todo"}
    assert names["sumar"]["permission"] == "ask"  # no read-only hint: ask first

    result = hub.call(server["id"], "sumar", {"a": 20, "b": 22})
    assert result["content"][0]["text"] == "42"
    # The secrets file is private and holds the tokens; servers.json does not.
    secrets = (tmp_path / "secrets.json").read_text()
    assert (
        "access_token" in secrets
        and "access_token" not in (tmp_path / "servers.json").read_text()
    )
    assert oct((tmp_path / "secrets.json").stat().st_mode)[-3:] == "600"


def test_expired_token_is_renewed_without_asking_again(tmp_path, oauth_site):
    base, provider = oauth_site
    hub = ConnectorHub(tmp_path, approver=lambda what, payload: True)
    server = hub.add_remote("Protegido", f"{base}/mcp")
    _sign_in(hub, server["id"])
    signed_in = provider.authorize_calls
    provider.expire_all()
    hub._drop_client(server["id"])  # a fresh session, as after a restart
    result = hub.call(server["id"], "sumar", {"a": 1, "b": 1})
    assert result["content"][0]["text"] == "2"
    assert provider.authorize_calls == signed_in  # refreshed, not re-authorized


def test_permissions_never_and_ask(tmp_path, oauth_site):
    base, _ = oauth_site
    asked = []
    hub = ConnectorHub(
        tmp_path, approver=lambda what, payload: asked.append(payload["tool"]) or False
    )
    server = hub.add_remote("Protegido", f"{base}/mcp")
    _sign_in(hub, server["id"])
    with pytest.raises(ConnectorError, match="no aprobó"):
        hub.call(server["id"], "borrar_todo", {"confirmacion": "sí"})
    assert asked == ["borrar_todo"]
    hub.set_permission(server["id"], "borrar_todo", "block")
    with pytest.raises(ConnectorError, match="no permite"):
        hub.call(server["id"], "borrar_todo", {"confirmacion": "sí"})
    hub.set_permission(server["id"], "sumar", "allow")
    assert (
        hub.call(server["id"], "sumar", {"a": 2, "b": 2})["content"][0]["text"] == "4"
    )
    tools = {t.spec.name for t in hub.agent_tools()}
    assert tool_name(server["id"], "sumar") in tools
    assert tool_name(server["id"], "borrar_todo") not in tools  # «Nunca» hides it


def test_open_server_needs_no_sign_in(tmp_path, open_site):
    hub = ConnectorHub(tmp_path, approver=lambda what, payload: True)
    server = hub.add_remote("Abierto", open_site)
    connected = hub.connect(server["id"], "http://localhost/cb")
    assert connected["status"] == "connected"
    tool = next(t for t in hub.agent_tools() if t.spec.name.endswith("__sumar"))
    out = tool.execute(a=3, b=4)
    assert out.success and out.content == "7"


def test_local_connector_runs_the_real_sdk_over_stdio(tmp_path):
    script = tmp_path / "srv.py"
    script.write_text(
        "import sys\nsys.path.insert(0, %r)\nfrom real_servers import tool_server\ntool_server().run()\n"
        % str(Path(__file__).parent)
    )
    hub = ConnectorHub(tmp_path, approver=lambda what, payload: True)
    server = hub.add_local("Local", [sys.executable, str(script)])
    connected = hub.connect(server["id"])
    assert connected["status"] == "connected"
    assert hub.call(server["id"], "sumar", {"a": 5, "b": 5})["structuredContent"] == {
        "result": 10
    }
    hub.remove(server["id"])
    assert hub.list() == []


def test_disconnect_and_bad_urls(tmp_path, oauth_site):
    base, _ = oauth_site
    hub = ConnectorHub(tmp_path, approver=lambda what, payload: True)
    with pytest.raises(ConnectorError, match="https"):
        hub.add_remote("Malo", "http://ejemplo.com/mcp")
    server = hub.add_remote("Protegido", f"{base}/mcp")
    _sign_in(hub, server["id"])
    assert hub.disconnect(server["id"])["status"] == "needs_auth"
    with pytest.raises(ConnectorError):
        hub.finish("estado-falso", "codigo")

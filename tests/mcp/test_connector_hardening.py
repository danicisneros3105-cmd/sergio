"""Regression scenarios: uncertain writes, OAuth boundaries, private config."""

import json
import time
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.mcp import oauth
from openjarvis.mcp.hub import ConnectorError, ConnectorHub
from openjarvis.server.auth_middleware import AuthMiddleware
from openjarvis.server.mcp_routes import router
from openjarvis.server.mobile import RemoteAccessMiddleware


def auth_server(token="https://auth.test/token"):
    return oauth.AuthServer(
        "https://resource.test/mcp",
        "https://auth.test",
        "https://auth.test/authorize",
        token,
    )


def test_lost_write_response_is_not_replayed(tmp_path):
    hub = ConnectorHub(tmp_path)
    server = hub.add_local("Invoices", ["never-run"])
    remote = Mock()
    remote.call_tool.side_effect = TimeoutError("write committed; reply lost")
    hub._clients[server["id"]] = remote
    with pytest.raises(ConnectorError, match="No repetí"):
        hub.call(server["id"], "create_invoice", approved=True)
    remote.call_tool.assert_called_once()
    remote.close.assert_called_once()


@pytest.mark.parametrize(
    "url",
    ["http://outside.test/token", "file:///tmp/token", "https://a:b@auth.test/token"],
)
def test_no_credentials_sent_to_unsafe_endpoints(url):
    requests = []
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: requests.append(r))
    ) as http:
        with pytest.raises(oauth.OAuthError):
            oauth.exchange(
                http,
                auth_server(url),
                {"client_id": "id", "client_secret": "secret"},
                oauth.Pending("state", "verifier", "http://localhost/cb", "s"),
                "code",
            )
    assert requests == []


def test_token_redirect_never_forwards_secret():
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(307, headers={"location": "https://other.test/token"})

    with httpx.Client(
        transport=httpx.MockTransport(reply), follow_redirects=True
    ) as http:
        with pytest.raises(oauth.OAuthError, match="redirigió"):
            oauth.refresh(
                http,
                auth_server(),
                {"client_id": "id", "client_secret": "secret"},
                oauth.Tokens("access", refresh_token="refresh"),
            )
    assert len(requests) == 1 and requests[0].url.host == "auth.test"


def test_discovery_redirect_cannot_downgrade():
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/metadata"})

    with httpx.Client(
        transport=httpx.MockTransport(reply), follow_redirects=True
    ) as http:
        with pytest.raises(oauth.OAuthError, match="seguridad"):
            oauth.discover(http, "https://resource.test/mcp", {})
    assert len(requests) == 1


def test_expired_and_empty_callback_codes_rejected_before_exchange(
    tmp_path, monkeypatch
):
    hub = ConnectorHub(tmp_path)
    exchange = Mock()
    monkeypatch.setattr(oauth, "exchange", exchange)
    for code, age in [("code", 901), ("", 1)]:
        hub._pending["state"] = oauth.Pending(
            "state", "verifier", "http://localhost/cb", "s", created=time.time() - age
        )
        with pytest.raises(ConnectorError, match="ya no es válido"):
            hub.finish("state", code)
        assert "state" not in hub._pending
    exchange.assert_not_called()


@pytest.mark.parametrize("forwarded", [False, True])
def test_callback_passes_both_auth_gates_but_other_routes_do_not(forwarded):
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(AuthMiddleware, api_key="test-key")
    app.add_middleware(RemoteAccessMiddleware, api_key="test-key")
    with TestClient(app) as client:
        headers = {"x-forwarded-for": "203.0.113.1"} if forwarded else {}
        response = client.get(
            "/v1/mcp/oauth/callback?error=access_denied", headers=headers
        )
        assert response.status_code == 400
        for path in ("/v1/mcp/servers", "/v1/mcp/oauth/callback/extra"):
            assert client.get(path, headers=headers).status_code == 401


def test_custom_credentials_are_private_and_cache_is_invalidated(tmp_path):
    hub = ConnectorHub(tmp_path)
    remote = hub.add_remote(
        "API",
        "https://resource.test/mcp",
        headers={"Authorization": "Bearer private-key"},
    )
    local = hub.add_local("Local", ["never-run"], env={"API_KEY": "private-env"})
    assert "private-" not in (tmp_path / "servers.json").read_text()
    assert hub._secrets()[local["id"]]["env"]["API_KEY"] == "private-env"
    assert (tmp_path / "secrets.json").stat().st_mode & 0o777 == 0o600
    before = hub.cache_hits
    public = hub.list()
    public[0]["name"] = "must not mutate cache"
    assert hub.list()[0]["name"] == "API" and hub.cache_hits > before
    raw = json.loads((tmp_path / "servers.json").read_text())
    raw["servers"][0]["enabled"] = False
    (tmp_path / "servers.json").write_text(json.dumps(raw))
    assert hub.get(remote["id"])["status"] == "disabled"


def test_legacy_credentials_migrate_without_loss(tmp_path):
    (tmp_path / "servers.json").write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "id": "s",
                        "name": "S",
                        "headers": {"API-Key": "private"},
                        "env": {"K": "v"},
                    }
                ]
            }
        )
    )
    hub = ConnectorHub(tmp_path)
    assert "private" not in (tmp_path / "servers.json").read_text()
    assert hub._secrets()["s"]["headers"]["API-Key"] == "private"


def test_rejected_token_response_does_not_echo_secrets():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                400, json={"error_description": "secret-from-provider"}
            )
        )
    ) as http:
        with pytest.raises(oauth.OAuthError) as caught:
            oauth.refresh(
                http,
                auth_server(),
                {"client_id": "id"},
                oauth.Tokens("a", refresh_token="r"),
            )
    assert "secret-from-provider" not in str(caught.value)

"""Real MCP servers for the tests, built with the official ``mcp`` SDK.

* ``tool_server()``   – an MCPServer with two tools (no auth).
* ``oauth_server()``  – the same tools behind the SDK's own OAuth 2.1
  authorization server (dynamic client registration, PKCE, refresh),
  the way remote connectors such as Notion's or Linear's work.

``serve(app)`` runs either one on a free local port in a thread and returns
its base URL. The consent screen is replaced by an automatic «Allow».
"""

from __future__ import annotations

import secrets
import socket
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import pytest

mcp = pytest.importorskip("mcp")

from mcp.server.auth.provider import (  # noqa: E402
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
)
from mcp.server.auth.settings import (  # noqa: E402
    AuthSettings,
    ClientRegistrationOptions,
)
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _add_tools(server: Any) -> None:
    @server.tool()
    def sumar(a: int, b: int) -> int:
        """Suma dos números."""
        return a + b

    @server.tool()
    def borrar_todo(confirmacion: str) -> str:
        """Borra todo (solo para probar los permisos)."""
        return f"borrado: {confirmacion}"


def tool_server() -> Any:
    server = MCPServer("prueba")
    _add_tools(server)
    return server


class MemoryProvider:
    """An OAuth authorization server kept in memory, auto-approving consent."""

    def __init__(self, ttl: int = 3600) -> None:
        self.clients: Dict[str, OAuthClientInformationFull] = {}
        self.codes: Dict[str, AuthorizationCode] = {}
        self.access: Dict[str, AccessToken] = {}
        self.refresh: Dict[str, RefreshToken] = {}
        self.ttl = ttl
        self.authorize_calls = 0

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        self.authorize_calls += 1
        code = secrets.token_urlsafe(16)
        self.codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + 300,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        query = {"code": code}
        if params.state:
            query["state"] = params.state
        return f"{params.redirect_uri}?{urlencode(query)}"

    async def load_authorization_code(
        self, client: Any, authorization_code: str
    ) -> Optional[AuthorizationCode]:
        return self.codes.get(authorization_code)

    def _issue(
        self, client_id: str, scopes: list, resource: Optional[str]
    ) -> OAuthToken:
        access = secrets.token_urlsafe(24)
        refresh = secrets.token_urlsafe(24)
        self.access[access] = AccessToken(
            token=access,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + self.ttl,
            resource=resource,
        )
        self.refresh[refresh] = RefreshToken(
            token=refresh, client_id=client_id, scopes=scopes, resource=resource
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=self.ttl,
            refresh_token=refresh,
            scope=" ".join(scopes) or None,
        )

    async def exchange_authorization_code(
        self, client: Any, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self.codes.pop(authorization_code.code, None)
        return self._issue(
            client.client_id, authorization_code.scopes, authorization_code.resource
        )

    async def load_refresh_token(
        self, client: Any, refresh_token: str
    ) -> Optional[RefreshToken]:
        return self.refresh.get(refresh_token)

    async def exchange_refresh_token(
        self, client: Any, refresh_token: RefreshToken, scopes: list
    ) -> OAuthToken:
        self.refresh.pop(refresh_token.token, None)
        return self._issue(
            client.client_id, scopes or refresh_token.scopes, refresh_token.resource
        )

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        found = self.access.get(token)
        if found and found.expires_at and found.expires_at < time.time():
            return None
        return found

    async def revoke_token(self, token: Any) -> None:
        self.access.pop(getattr(token, "token", ""), None)

    def expire_all(self) -> None:
        for token in self.access.values():
            token.expires_at = int(time.time()) - 1


def oauth_server(base: str, provider: MemoryProvider) -> Any:
    server = MCPServer(
        "protegido",
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=base,
            resource_server_url=f"{base}/mcp",
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=["leer"], default_scopes=["leer"]
            ),
            required_scopes=["leer"],
            validate_token_resource=False,
        ),
    )
    _add_tools(server)
    return server


def serve(app: Any, port: int) -> str:
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.02)
    serve.servers.append(server)  # type: ignore[attr-defined]
    return f"http://127.0.0.1:{port}"


serve.servers = []  # type: ignore[attr-defined]


def stop_all() -> None:
    for server in serve.servers:  # type: ignore[attr-defined]
        server.should_exit = True
    serve.servers.clear()  # type: ignore[attr-defined]

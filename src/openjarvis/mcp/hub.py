"""Sergio's connectors, the way Claude does them.

A connector is an MCP server the owner added — a remote one by URL (signed in
with OAuth when the service asks for it) or a local one started on the PC —
plus, for each of its tools, the owner's permission: «Permitir siempre»,
«Pedir permiso» or «Nunca». Everything lives in ``~/.openjarvis/connectors/``:

* ``servers.json`` — what was added (no secrets)
* ``secrets.json`` — OAuth clients and tokens, readable only by the owner

The web (``/v1/mcp``), the CLI (``sergio mcp``) and the agents all go through
one ``ConnectorHub``; agents get each connected tool as a normal tool named
``<conector>__<herramienta>``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openjarvis.mcp import oauth
from openjarvis.mcp.oauth import AuthServer, OAuthError, Pending, Tokens

logger = logging.getLogger(__name__)

PERMISSIONS = ("allow", "ask", "block")
PERMISSION_ES = {"allow": "Permitir siempre", "ask": "Pedir permiso", "block": "Nunca"}
CLIENT_INFO = {"name": "Sergio", "version": "1.0"}
PROTOCOL = "2025-06-18"
APPROVAL_WAIT = 180.0


class ConnectorError(RuntimeError):
    """Something the owner can act on (the message is in plain Spanish)."""


def _root() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "connectors"


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")
    return value[:40] or "conector"


def tool_name(server_id: str, tool: str) -> str:
    """The name an agent sees: ``notion__search`` (≤ 64 chars, safe chars)."""
    name = f"{server_id.replace('-', '_')}__{re.sub(r'[^A-Za-z0-9_-]', '_', tool)}"
    return name[:64]


def default_permission(tool: Dict[str, Any]) -> str:
    """Read-only tools run freely; anything that may change things asks."""
    notes = tool.get("annotations") or {}
    return "allow" if notes.get("readOnlyHint") is True else "ask"


class ConnectorHub:
    def __init__(
        self,
        root: Optional[Path] = None,
        *,
        http: Any = None,
        approver: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
    ) -> None:
        self.root = Path(root) if root else _root()
        self._http = http
        self._approver = approver
        self._lock = threading.RLock()
        self._clients: Dict[str, Any] = {}
        self._pending: Dict[str, Pending] = {}

    # -- storage --------------------------------------------------------------
    def _read(self, name: str) -> Dict[str, Any]:
        path = self.root / name
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, name: str, data: Dict[str, Any], *, private: bool = False) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / name
        tmp = path.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        if private:
            os.chmod(tmp, 0o600)
        tmp.replace(path)

    def _servers(self) -> List[Dict[str, Any]]:
        return list(self._read("servers.json").get("servers", []))

    def _save_servers(self, servers: List[Dict[str, Any]]) -> None:
        self._write("servers.json", {"servers": servers})

    def _secrets(self) -> Dict[str, Any]:
        return self._read("secrets.json")

    def _save_secrets(self, data: Dict[str, Any]) -> None:
        self._write("secrets.json", data, private=True)

    def _get(self, server_id: str) -> Dict[str, Any]:
        for server in self._servers():
            if server["id"] == server_id:
                return server
        raise ConnectorError(f"No hay un conector «{server_id}».")

    def _update(self, server_id: str, **changes: Any) -> Dict[str, Any]:
        with self._lock:
            servers = self._servers()
            for server in servers:
                if server["id"] == server_id:
                    server.update(changes)
                    self._save_servers(servers)
                    return server
        raise ConnectorError(f"No hay un conector «{server_id}».")

    def _http_client(self) -> Any:
        if self._http is not None:
            return self._http
        import httpx

        return httpx.Client(timeout=20.0, follow_redirects=True)

    # -- what the owner sees --------------------------------------------------
    def public(self, server: Dict[str, Any]) -> Dict[str, Any]:
        secrets = self._secrets().get(server["id"], {})
        tools = server.get("tools") or []
        perms = server.get("permissions") or {}
        if not server.get("enabled", True):
            status = "disabled"
        elif (
            server.get("kind") == "remote"
            and server.get("auth")
            and not secrets.get("tokens")
        ):
            status = "needs_auth"
        elif server.get("error"):
            status = "error"
        elif server.get("connected"):
            status = "connected"
        else:
            status = "needs_auth" if server.get("kind") == "remote" else "off"
        return {
            "id": server["id"],
            "name": server["name"],
            "kind": server.get("kind", "remote"),
            "url": server.get("url", ""),
            "transport": server.get("transport", ""),
            "command": server.get("command", []),
            "source": server.get("source", "custom"),
            "directory_id": server.get("directory_id", ""),
            "enabled": server.get("enabled", True),
            "status": status,
            "error": server.get("error", ""),
            "oauth": bool(server.get("auth")),
            "own_client": bool(secrets.get("client", {}).get("manual")),
            "server_info": server.get("server_info", {}),
            "tools": [
                {
                    "name": t.get("name", ""),
                    "title": t.get("title")
                    or (t.get("annotations") or {}).get("title")
                    or "",
                    "description": t.get("description", ""),
                    "read_only": (t.get("annotations") or {}).get("readOnlyHint")
                    is True,
                    "permission": perms.get(t.get("name", ""), default_permission(t)),
                }
                for t in tools
            ],
            "added": server.get("added", 0),
        }

    def list(self) -> List[Dict[str, Any]]:
        return [self.public(s) for s in self._servers()]

    def get(self, server_id: str) -> Dict[str, Any]:
        return self.public(self._get(server_id))

    # -- adding and removing --------------------------------------------------
    def _new_id(self, name: str) -> str:
        taken = {s["id"] for s in self._servers()}
        base = slug(name)
        candidate, n = base, 2
        while candidate in taken:
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def add_remote(
        self,
        name: str,
        url: str,
        *,
        client_id: str = "",
        client_secret: str = "",
        source: str = "custom",
        directory_id: str = "",
        transport: str = "",
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = url.strip()
        if not re.match(r"^https?://", url):
            raise ConnectorError("La URL del servidor MCP debe empezar por https://")
        if url.startswith("http://") and not re.match(
            r"^http://(localhost|127\.0\.0\.1|\[::1\])(:|/)", url
        ):
            raise ConnectorError("Por seguridad, un servidor remoto debe usar https://")
        name = (name or "").strip() or re.sub(r"^https?://(mcp\.)?", "", url).split(
            "/"
        )[0]
        with self._lock:
            for existing in self._servers():
                if existing.get("url") == url:
                    return self.public(existing)
            server = {
                "id": self._new_id(name),
                "name": name[:60],
                "kind": "remote",
                "url": url,
                "transport": transport
                or ("sse" if url.rstrip("/").endswith("/sse") else "http"),
                "source": source,
                "directory_id": directory_id,
                "enabled": True,
                "permissions": {},
                "tools": [],
                "headers": dict(headers or {}),
                "added": time.time(),
            }
            self._save_servers([*self._servers(), server])
            if client_id:
                secrets = self._secrets()
                secrets.setdefault(server["id"], {})["client"] = {
                    "client_id": client_id.strip(),
                    "client_secret": client_secret.strip(),
                    "manual": True,
                }
                self._save_secrets(secrets)
        return self.public(server)

    def add_local(
        self,
        name: str,
        command: List[str],
        *,
        env: Optional[Dict[str, str]] = None,
        source: str = "custom",
        directory_id: str = "",
    ) -> Dict[str, Any]:
        command = [str(part) for part in command if str(part).strip()]
        if not command:
            raise ConnectorError("Indique la orden que arranca el servidor.")
        with self._lock:
            server = {
                "id": self._new_id(name or command[0]),
                "name": (name or command[0])[:60],
                "kind": "local",
                "command": command,
                "env": dict(env or {}),
                "source": source,
                "directory_id": directory_id,
                "enabled": True,
                "permissions": {},
                "tools": [],
                "added": time.time(),
            }
            self._save_servers([*self._servers(), server])
        return self.public(server)

    def add_from_directory(
        self, entry_id: str, *, args: Optional[List[str]] = None, **client: str
    ) -> Dict[str, Any]:
        from openjarvis.mcp.directory import find

        try:
            entry = find(entry_id)
        except KeyError as exc:
            raise ConnectorError("Ese conector no está en el directorio.") from exc
        if entry["kind"] == "local":
            return self.add_local(
                entry["name"],
                [*entry["command"], *(args or [])],
                source="directory",
                directory_id=entry_id,
            )
        return self.add_remote(
            entry["name"],
            entry["url"],
            client_id=client.get("client_id", ""),
            client_secret=client.get("client_secret", ""),
            source="directory",
            directory_id=entry_id,
        )

    def remove(self, server_id: str) -> None:
        with self._lock:
            self._drop_client(server_id)
            self._save_servers([s for s in self._servers() if s["id"] != server_id])
            secrets = self._secrets()
            if secrets.pop(server_id, None) is not None:
                self._save_secrets(secrets)

    def set_enabled(self, server_id: str, enabled: bool) -> Dict[str, Any]:
        if not enabled:
            self._drop_client(server_id)
        return self.public(self._update(server_id, enabled=bool(enabled)))

    def set_permission(
        self, server_id: str, tool: str, permission: str
    ) -> Dict[str, Any]:
        if permission not in PERMISSIONS:
            raise ConnectorError("Permiso desconocido.")
        server = self._get(server_id)
        perms = dict(server.get("permissions") or {})
        perms[tool] = permission
        return self.public(self._update(server_id, permissions=perms))

    def set_all_permissions(self, server_id: str, permission: str) -> Dict[str, Any]:
        if permission not in PERMISSIONS:
            raise ConnectorError("Permiso desconocido.")
        server = self._get(server_id)
        perms = {t.get("name", ""): permission for t in server.get("tools") or []}
        return self.public(self._update(server_id, permissions=perms))

    # -- signing in -----------------------------------------------------------
    def connect(self, server_id: str, redirect_uri: str = "") -> Dict[str, Any]:
        """Connect now; for a service that asks for a sign-in, returns the page
        to open (``auth_url``) and finishes in :meth:`finish`."""
        server = self._get(server_id)
        if server.get("kind") == "local":
            return {"status": "connected", "server": self.refresh_tools(server_id)}
        http = self._http_client()
        try:
            challenge = oauth.probe(http, server["url"])
        except OAuthError as exc:
            self._update(server_id, error=str(exc), connected=False)
            raise ConnectorError(str(exc)) from exc
        if challenge is None and not self._secrets().get(server_id, {}).get(
            "client", {}
        ).get("manual"):
            self._update(server_id, auth=None)
            return {"status": "connected", "server": self.refresh_tools(server_id)}
        if not redirect_uri:
            raise ConnectorError("Falta la dirección de vuelta para iniciar sesión.")
        try:
            auth_server = oauth.discover(http, server["url"], challenge or {})
        except OAuthError as exc:
            raise ConnectorError(str(exc)) from exc
        secrets = self._secrets()
        mine = secrets.setdefault(server_id, {})
        client = mine.get("client") or {}
        if not client.get("manual") and client.get("redirect_uri") != redirect_uri:
            try:
                client = {
                    **oauth.register(http, auth_server, redirect_uri),
                    "redirect_uri": redirect_uri,
                }
            except OAuthError as exc:
                raise ConnectorError(str(exc)) from exc
            mine["client"] = client
            self._save_secrets(secrets)
        url, pending = oauth.authorize_url(
            auth_server, client["client_id"], redirect_uri, server_id
        )
        with self._lock:
            self._pending = {
                k: p for k, p in self._pending.items() if time.time() - p.created < 900
            }
            self._pending[pending.state] = pending
        self._update(server_id, auth=auth_server.to_dict(), error="")
        return {"status": "needs_auth", "auth_url": url, "state": pending.state}

    def finish(self, state: str, code: str) -> Dict[str, Any]:
        """The browser came back from the service with ``code``."""
        with self._lock:
            pending = self._pending.pop(state, None)
        if pending is None:
            raise ConnectorError(
                "Ese inicio de sesión ya no es válido; vuelva a pulsar «Conectar»."
            )
        server = self._get(pending.server_id)
        auth_server = AuthServer.from_dict(server.get("auth") or {})
        secrets = self._secrets()
        client = secrets.get(pending.server_id, {}).get("client") or {}
        try:
            tokens = oauth.exchange(
                self._http_client(), auth_server, client, pending, code
            )
        except OAuthError as exc:
            self._update(pending.server_id, error=str(exc), connected=False)
            raise ConnectorError(str(exc)) from exc
        secrets.setdefault(pending.server_id, {})["tokens"] = tokens.to_dict()
        self._save_secrets(secrets)
        self._drop_client(pending.server_id)
        return self.refresh_tools(pending.server_id)

    def disconnect(self, server_id: str) -> Dict[str, Any]:
        """Forget the sign-in (the connector stays, ready to connect again)."""
        self._drop_client(server_id)
        secrets = self._secrets()
        if secrets.get(server_id, {}).pop("tokens", None) is not None:
            self._save_secrets(secrets)
        return self.public(self._update(server_id, connected=False, error=""))

    def _token(self, server_id: str, force: bool) -> Optional[str]:
        """The access token to send, renewed when it expired (or on a 401)."""
        with self._lock:
            secrets = self._secrets()
            mine = secrets.get(server_id, {})
            raw = mine.get("tokens")
            if not raw:
                return None
            tokens = Tokens.from_dict(raw)
            if not force and not tokens.expired():
                return tokens.access_token
            server = self._get(server_id)
            if not server.get("auth") or not tokens.refresh_token:
                return None if force else tokens.access_token
            try:
                tokens = oauth.refresh(
                    self._http_client(),
                    AuthServer.from_dict(server["auth"]),
                    mine.get("client") or {},
                    tokens,
                )
            except OAuthError as exc:
                logger.info("Refreshing the token for %s failed: %s", server_id, exc)
                mine.pop("tokens", None)
                self._save_secrets(secrets)
                return None
            mine["tokens"] = tokens.to_dict()
            self._save_secrets(secrets)
            return tokens.access_token

    # -- talking to the server ------------------------------------------------
    def _drop_client(self, server_id: str) -> None:
        with self._lock:
            client = self._clients.pop(server_id, None)
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass

    def _client(self, server_id: str) -> Any:
        from openjarvis.mcp.client import MCPClient
        from openjarvis.mcp.transport import (
            LegacySSETransport,
            StdioTransport,
            StreamableHTTPTransport,
        )

        with self._lock:
            client = self._clients.get(server_id)
            if client is not None:
                return client
            server = self._get(server_id)
            if not server.get("enabled", True):
                raise ConnectorError(f"«{server['name']}» está desactivado.")
            if server.get("kind") == "local":
                env = {**os.environ, **(server.get("env") or {})}
                transport: Any = StdioTransport(
                    list(server["command"]), env=env, response_timeout=120.0
                )
            else:

                def auth(force: bool, sid: str = server_id) -> Optional[str]:
                    return self._token(sid, force)

                if server.get("transport") == "sse":
                    transport = LegacySSETransport(server["url"], auth=auth)
                else:
                    transport = StreamableHTTPTransport(
                        server["url"],
                        auth=auth,
                        headers=server.get("headers") or None,
                        request_timeout=120.0,
                    )
            client = MCPClient(
                transport, protocol_version=PROTOCOL, client_info=CLIENT_INFO
            )
            try:
                result = client.initialize()
            except Exception:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass
                raise
            server_info = result.get("serverInfo") or {}
            self._update(
                server_id,
                server_info={
                    "name": server_info.get("name", ""),
                    "version": server_info.get("version", ""),
                },
            )
            self._clients[server_id] = client
            return client

    def refresh_tools(self, server_id: str) -> Dict[str, Any]:
        from openjarvis.mcp.transport import MCPAuthRequired

        self._drop_client(server_id)
        try:
            tools = self._client(server_id).list_tools_raw()
        except MCPAuthRequired:
            self._update(server_id, connected=False, error="")
            raise ConnectorError(
                "El servicio pide iniciar sesión: pulse «Conectar»."
            ) from None
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001 - shown to the owner
            message = f"No pude conectar: {exc}"[:300]
            self._update(server_id, connected=False, error=message)
            raise ConnectorError(message) from exc
        keep = ("name", "title", "description", "inputSchema", "annotations")
        tools = [{k: t[k] for k in keep if k in t} for t in tools]
        return self.public(
            self._update(
                server_id, tools=tools, connected=True, error="", checked=time.time()
            )
        )

    def permission(self, server_id: str, tool: str) -> str:
        server = self._get(server_id)
        perms = server.get("permissions") or {}
        if tool in perms:
            return perms[tool]
        for t in server.get("tools") or []:
            if t.get("name") == tool:
                return default_permission(t)
        return "ask"

    def call(
        self,
        server_id: str,
        tool: str,
        args: Optional[Dict[str, Any]] = None,
        *,
        approved: bool = False,
    ) -> Dict[str, Any]:
        """Run a tool, honouring the owner's permission for it."""
        server = self._get(server_id)
        permission = self.permission(server_id, tool)
        if permission == "block":
            raise ConnectorError(
                f"El señor no permite usar «{tool}» de {server['name']}."
            )
        if permission == "ask" and not approved:
            ask = self._approver or wait_for_owner
            summary = json.dumps(args or {}, ensure_ascii=False)[:400]
            if not ask(
                f"{server['name']}: {tool} {summary}",
                {"server": server_id, "tool": tool, "arguments": args or {}},
            ):
                raise ConnectorError(
                    f"El señor no aprobó «{tool}» de {server['name']}."
                )
        try:
            return self._client(server_id).call_tool(tool, args or {})
        except ConnectorError:
            raise
        except Exception as first:  # noqa: BLE001 - one reconnect, then report
            from openjarvis.mcp.transport import MCPAuthRequired

            if isinstance(first, MCPAuthRequired):
                self._update(server_id, connected=False)
                raise ConnectorError(
                    f"{server['name']} pide iniciar sesión de nuevo: pulse «Conectar»."
                ) from first
            self._drop_client(server_id)
            try:
                return self._client(server_id).call_tool(tool, args or {})
            except Exception as exc:  # noqa: BLE001
                raise ConnectorError(f"{server['name']} falló: {exc}"[:300]) from exc

    # -- for the agents -------------------------------------------------------
    def agent_tools(self) -> List[Any]:
        """Every allowed tool of every connected connector, as agent tools."""
        tools: List[Any] = []
        for server in self._servers():
            if not server.get("enabled", True) or not server.get("connected"):
                continue
            for raw in server.get("tools") or []:
                if self.permission(server["id"], raw.get("name", "")) == "block":
                    continue
                tools.append(ConnectorTool(self, server["id"], server["name"], raw))
        return tools


def ConnectorTool(
    hub: ConnectorHub, server_id: str, server_name: str, raw: Dict[str, Any]
) -> Any:  # noqa: N802
    from openjarvis.core.types import ToolResult
    from openjarvis.tools._stubs import BaseTool, ToolSpec

    class _ConnectorTool(BaseTool):
        tool_id = "connector"

        def __init__(self) -> None:
            self._spec = ToolSpec(
                name=tool_name(server_id, raw.get("name", "")),
                description=f"[{server_name}] {raw.get('description', '')}".strip()[
                    :1024
                ],
                parameters=raw.get("inputSchema")
                or {"type": "object", "properties": {}},
                timeout_seconds=600.0,
            )

        @property
        def spec(self) -> ToolSpec:
            return self._spec

        def execute(self, **params: Any) -> ToolResult:
            try:
                result = hub.call(server_id, raw.get("name", ""), params)
            except ConnectorError as exc:
                return ToolResult(
                    tool_name=self._spec.name, content=str(exc), success=False
                )
            parts = result.get("content") or []
            text = "\n".join(
                p.get("text", "")
                if p.get("type") == "text"
                else f"[{p.get('type', 'contenido')}]"
                for p in parts
                if isinstance(p, dict)
            )
            if not text and result.get("structuredContent") is not None:
                text = json.dumps(result["structuredContent"], ensure_ascii=False)
            return ToolResult(
                tool_name=self._spec.name,
                content=text,
                success=not result.get("isError", False),
            )

    return _ConnectorTool()


def MetaTools(hub: ConnectorHub) -> List[Any]:  # noqa: N802
    """Two always-present tools so connectors added after Sergio started can
    be used right away (the direct tools appear after a restart)."""
    from openjarvis.core.types import ToolResult
    from openjarvis.tools._stubs import BaseTool, ToolSpec

    class _List(BaseTool):
        tool_id = "connectors_list"

        @property
        def spec(self) -> ToolSpec:
            return ToolSpec(
                name="conectores_lista",
                description="Lista los conectores del señor (Gmail, Notion, Higgsfield…) y sus herramientas, "
                "para usarlas con conectores_usar.",
                parameters={"type": "object", "properties": {}},
            )

        def execute(self, **params: Any) -> ToolResult:
            lines = []
            for server in hub.list():
                if server["status"] != "connected":
                    lines.append(f"{server['id']} ({server['name']}): no conectado")
                    continue
                for tool in server["tools"]:
                    if tool["permission"] != "block":
                        lines.append(
                            f"{server['id']} · {tool['name']}: {tool['description'][:140]}"
                        )
            return ToolResult(
                tool_name="conectores_lista",
                content="\n".join(lines) or "No hay conectores.",
                success=True,
            )

    class _Use(BaseTool):
        tool_id = "connectors_call"

        @property
        def spec(self) -> ToolSpec:
            return ToolSpec(
                name="conectores_usar",
                description="Usa una herramienta de un conector del señor: conector (id), herramienta y argumentos.",
                parameters={
                    "type": "object",
                    "properties": {
                        "conector": {"type": "string"},
                        "herramienta": {"type": "string"},
                        "argumentos": {"type": "object"},
                    },
                    "required": ["conector", "herramienta"],
                },
                timeout_seconds=600.0,
            )

        def execute(self, **params: Any) -> ToolResult:
            try:
                result = hub.call(
                    str(params.get("conector")),
                    str(params.get("herramienta")),
                    params.get("argumentos") or {},
                )
            except ConnectorError as exc:
                return ToolResult(
                    tool_name="conectores_usar", content=str(exc), success=False
                )
            text = "\n".join(
                p.get("text", "")
                for p in result.get("content") or []
                if isinstance(p, dict)
            )
            return ToolResult(
                tool_name="conectores_usar",
                content=text,
                success=not result.get("isError", False),
            )

    return [_List(), _Use()]


def connector_tools(existing: Optional[set] = None) -> List[Any]:
    """What to give an agent: every connected tool plus the two meta tools."""
    hub = get_hub()
    taken = set(existing or ())
    out = []
    for tool in [*hub.agent_tools(), *MetaTools(hub)]:
        if tool.spec.name not in taken:
            taken.add(tool.spec.name)
            out.append(tool)
    return out


def wait_for_owner(
    description: str, payload: Dict[str, Any], timeout: float = APPROVAL_WAIT
) -> bool:
    """Ask the owner through the approvals bell and wait for the answer."""
    from openjarvis.tools.approval_store import (
        STATUS_APPROVED,
        STATUS_DENIED,
        ApprovalStore,
    )

    store = ApprovalStore()
    action = store.queue_action(
        action_type="mcp_tool",
        description=f"Usar {description}",
        payload=payload,
        permission_key=f"mcp:{payload.get('server')}:{payload.get('tool')}",
        tier="medium",
        ttl_hours=1,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = store.get_action(action.id)
        if current is not None and current.status == STATUS_APPROVED:
            store.update_status(action.id, "executed")
            return True
        if current is not None and current.status == STATUS_DENIED:
            return False
        time.sleep(0.5)
    store.update_status(action.id, "expired")
    return False


_hub: Optional[ConnectorHub] = None
_hub_lock = threading.Lock()


def get_hub() -> ConnectorHub:
    global _hub
    with _hub_lock:
        if _hub is None:
            _hub = ConnectorHub()
        return _hub


__all__ = [
    "ConnectorError",
    "connector_tools",
    "ConnectorHub",
    "PERMISSIONS",
    "PERMISSION_ES",
    "default_permission",
    "get_hub",
    "slug",
    "tool_name",
    "wait_for_owner",
]

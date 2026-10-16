"""``sergio mcp``: connectors from the terminal, with Claude's command names.

    sergio mcp add notion                           # from the directory
    sergio mcp add --transport http notion https://mcp.notion.com/mcp
    sergio mcp add archivos -- npx -y @modelcontextprotocol/server-filesystem ~/Documentos
    sergio mcp add-json mio '{"type":"http","url":"https://…/mcp"}'
    sergio mcp add-from-claude-desktop              # what Claude Desktop has
    sergio mcp list                                 # with a live check
    sergio mcp get notion
    sergio mcp login notion                         # the service's sign-in page
    sergio mcp logout notion
    sergio mcp tools notion
    sergio mcp call notion notion-search '{"query":"actas"}'
    sergio mcp permiso notion notion-search allow   # allow | ask | block
    sergio mcp remove notion
    sergio mcp directorio [buscar]
    sergio mcp serve                                # Sergio as an MCP server (stdio)

Spanish names work too: añadir, lista, ver, conectar, desconectar,
herramientas, usar, quitar. The web (Extensiones › Conectores) shows the same.
"""

from __future__ import annotations

import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import click
from rich.console import Console
from rich.table import Table

console = Console()
STATUS_ES = {
    "connected": "conectado",
    "needs_auth": "falta iniciar sesión",
    "error": "error",
    "disabled": "desactivado",
    "off": "sin probar",
}


def _hub() -> Any:
    from openjarvis.mcp.hub import get_hub

    return get_hub()


def _fail(exc: Exception) -> None:
    console.print(f"[red]{exc}[/red]")
    raise SystemExit(1)


def _find(name: str) -> Dict[str, Any]:
    from openjarvis.mcp.hub import slug

    for server in _hub().list():
        if name in (server["id"], server["name"]) or slug(name) == server["id"]:
            return server
    _fail(RuntimeError(f"No hay un conector «{name}». Vea: sergio mcp list"))
    raise AssertionError  # unreachable


@click.group("mcp")
def mcp() -> None:
    """Conectores MCP (como en Claude): añadir, conectar, permisos, servir."""


# -- adding ----------------------------------------------------------------------
@mcp.command(
    "add",
    context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False},
)
@click.option(
    "--transport", "-t", type=click.Choice(["http", "sse", "stdio"]), default=None
)
@click.option("--env", "-e", multiple=True, help="KEY=valor para un servidor local.")
@click.option(
    "--header", "-H", multiple=True, help="«Nombre: valor» para un servidor remoto."
)
@click.option(
    "--client-id",
    default="",
    help="Client ID propio (servicios sin registro automático).",
)
@click.option(
    "--client-secret", default="", help="Secreto de ese Client ID, si lo tiene."
)
@click.argument("name")
@click.argument("target", nargs=-1, type=click.UNPROCESSED)
def add(
    transport: Optional[str],
    env: tuple[str, ...],
    header: tuple[str, ...],
    client_id: str,
    client_secret: str,
    name: str,
    target: tuple[str, ...],
) -> None:
    """Añade un conector: una URL (remoto), una orden tras «--» (local),
    o solo el nombre si está en el directorio."""
    from openjarvis.mcp.directory import DIRECTORY
    from openjarvis.mcp.hub import ConnectorError

    hub = _hub()
    parts = [t for t in target if t != "--"]
    try:
        if not parts:
            entry = next(
                (e for e in DIRECTORY if name.lower() in (e["id"], e["name"].lower())),
                None,
            )
            if entry is None:
                _fail(
                    RuntimeError(
                        "Falta la URL o la orden. Vea el directorio: sergio mcp directorio"
                    )
                )
            server = hub.add_from_directory(
                entry["id"], client_id=client_id, client_secret=client_secret
            )
        elif transport == "stdio" or not parts[0].startswith(("http://", "https://")):
            envs = dict(item.split("=", 1) for item in env if "=" in item)
            server = hub.add_local(name, parts, env=envs)
        else:
            headers = {
                k.strip(): v.strip()
                for k, _, v in (h.partition(":") for h in header)
                if v
            }
            server = hub.add_remote(
                name,
                parts[0],
                client_id=client_id,
                client_secret=client_secret,
                transport=transport if transport in ("http", "sse") else "",
                headers=headers,
            )
    except ConnectorError as exc:
        _fail(exc)
        return
    console.print(f"Añadido «{server['name']}» ({server['id']}).")
    console.print(f"Conéctelo con: [bold]sergio mcp login {server['id']}[/bold]")


@mcp.command("add-cli", context_settings={"ignore_unknown_options": True})
@click.option("--cwd", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--env", "-e", multiple=True, help="Variable privada KEY=valor.")
@click.argument("name")
@click.argument("command", nargs=-1, required=True, type=click.UNPROCESSED)
def add_cli(
    cwd: str, env: tuple[str, ...], name: str, command: tuple[str, ...]
) -> None:
    """Connect an installed CLI (not an MCP server), asking before each call."""
    from openjarvis.mcp.hub import ConnectorError

    if any("=" not in item for item in env):
        _fail(ValueError("Use KEY=valor para cada variable."))
    try:
        server = _hub().add_cli(
            name,
            list(command),
            cwd=str(Path(cwd).resolve()),
            env=dict(item.split("=", 1) for item in env),
        )
        _hub().connect(server["id"])
    except ConnectorError as exc:
        _fail(exc)
        return
    console.print(f"CLI conectada: {server['id']}. Cada ejecución requiere permiso.")


@mcp.command("add-json")
@click.argument("name")
@click.argument("config")
def add_json(name: str, config: str) -> None:
    """Añade un conector desde su JSON (el mismo formato de .mcp.json)."""
    try:
        cfg = json.loads(config)
    except ValueError as exc:
        _fail(RuntimeError(f"JSON no válido: {exc}"))
        return
    _add_config(name, cfg)


def _add_config(
    name: str, cfg: Dict[str, Any], source: str = "custom"
) -> Optional[Dict[str, Any]]:
    from openjarvis.mcp.hub import ConnectorError

    hub = _hub()
    try:
        if cfg.get("url"):
            return hub.add_remote(
                name,
                cfg["url"],
                headers=cfg.get("headers") or None,
                transport="sse" if cfg.get("type") == "sse" else "",
            )
        if cfg.get("command"):
            command = [str(cfg["command"]), *[str(a) for a in cfg.get("args") or []]]
            return hub.add_local(name, command, env=cfg.get("env") or {}, source=source)
    except ConnectorError as exc:
        _fail(exc)
    _fail(RuntimeError("El JSON necesita «url» o «command»."))
    return None


def claude_desktop_configs() -> List[Path]:
    """Where Claude Desktop keeps its config (Windows seen from WSL, macOS, Linux)."""
    home = Path.home()
    found = [
        home / "Library/Application Support/Claude/claude_desktop_config.json",
        home / ".config/Claude/claude_desktop_config.json",
    ]
    found += sorted(
        Path("/mnt/c/Users").glob("*/AppData/Roaming/Claude/claude_desktop_config.json")
    )
    return [p for p in found if p.is_file()]


@mcp.command("add-from-claude-desktop")
def add_from_claude_desktop() -> None:
    """Trae los servidores MCP que ya tiene en Claude Desktop."""
    paths = claude_desktop_configs()
    if not paths:
        _fail(
            RuntimeError(
                "No encuentro la configuración de Claude Desktop en este equipo."
            )
        )
    added = 0
    for path in paths:
        try:
            servers = json.loads(path.read_text("utf-8")).get("mcpServers") or {}
        except (OSError, ValueError):
            continue
        for name, cfg in servers.items():
            if isinstance(cfg, dict) and _add_config(
                name, cfg, source="claude-desktop"
            ):
                added += 1
    console.print(f"{added} conectores traídos de Claude Desktop.")


# -- looking -----------------------------------------------------------------
@mcp.command("list")
@click.option(
    "--sin-probar", "no_check", is_flag=True, help="No comprobar la conexión."
)
def list_cmd(no_check: bool) -> None:
    """Sus conectores y si responden."""
    from openjarvis.mcp.hub import ConnectorError

    hub = _hub()
    servers = hub.list()
    if not servers:
        console.print("Ningún conector. Añada uno: sergio mcp add notion")
        return
    for server in servers:
        status = server["status"]
        if (
            not no_check
            and server["enabled"]
            and status in ("connected", "off", "error")
        ):
            try:
                server = hub.refresh_tools(server["id"])
                status = "connected"
            except ConnectorError:
                status = hub.get(server["id"])["status"]
        where = server["url"] or " ".join(server["command"])
        mark = {
            "connected": "[green]✓[/green]",
            "needs_auth": "[yellow]![/yellow]",
        }.get(status, "[red]✗[/red]")
        tools = f" · {len(server['tools'])} herramientas" if server["tools"] else ""
        console.print(
            f"{mark} {server['id']}: {where} — {STATUS_ES.get(status, status)}{tools}"
        )


@mcp.command("get")
@click.argument("name")
def get(name: str) -> None:
    """Detalles de un conector."""
    server = _find(name)
    console.print(f"[bold]{server['name']}[/bold] ({server['id']})")
    console.print(f"  Tipo: {'remoto' if server['kind'] == 'remote' else 'local'}")
    console.print(
        f"  {'URL' if server['url'] else 'Orden'}: {server['url'] or ' '.join(server['command'])}"
    )
    console.print(f"  Estado: {STATUS_ES.get(server['status'], server['status'])}")
    console.print(f"  Origen: {server['source']}")
    if server["oauth"]:
        console.print("  Inicia sesión con OAuth")
    for tool in server["tools"]:
        console.print(f"  · {tool['name']}  [{tool['permission']}]")


@mcp.command("directorio")
@click.argument("consulta", nargs=-1)
def directorio(consulta: tuple[str, ...]) -> None:
    """El directorio de conectores listos para añadir."""
    from openjarvis.mcp.directory import directory

    query = " ".join(consulta).lower()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Conector")
    table.add_column("Para")
    table.add_column("Qué hace", overflow="fold")
    for entry in directory():
        if (
            query
            and query
            not in f"{entry['id']} {entry['name']} {entry['description']}".lower()
        ):
            continue
        table.add_row(entry["id"], entry["category"], entry["description"])
    console.print(table)
    console.print("Añada uno con: sergio mcp add <conector>")


# -- signing in ----------------------------------------------------------------
def _browser_sign_in(server_id: str) -> Dict[str, Any]:
    """Run the OAuth round trip with a one-shot local page for the return."""
    from openjarvis.mcp.hub import ConnectorError

    hub = _hub()
    got: Dict[str, str] = {}
    done = threading.Event()

    class Back(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            query = parse_qs(urlparse(self.path).query)
            got.update({k: v[0] for k, v in query.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<p style='font:16px system-ui'>Listo. Vuelva a la terminal.</p>".encode()
            )
            done.set()

        def log_message(self, *args: Any) -> None:
            return

    httpd = HTTPServer(("127.0.0.1", 0), Back)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        started = hub.connect(server_id, f"http://localhost:{port}/callback")
        if started["status"] == "connected":
            return started["server"]
        console.print("Abriendo la página de inicio de sesión del servicio…")
        console.print(
            f"Si no se abre, copie esto en el navegador:\n{started['auth_url']}"
        )
        try:
            webbrowser.open(started["auth_url"])
        except Exception:  # noqa: BLE001 - the URL is printed anyway
            pass
        if not done.wait(300):
            raise ConnectorError(
                "No llegó la respuesta del inicio de sesión (5 minutos)."
            )
        if got.get("error"):
            raise ConnectorError(got.get("error_description") or got["error"])
        return hub.finish(got.get("state", ""), got.get("code", ""))
    finally:
        httpd.shutdown()


@mcp.command("login")
@click.argument("name")
def login(name: str) -> None:
    """Conecta (inicia sesión en el servicio si lo pide)."""
    from openjarvis.mcp.hub import ConnectorError

    server = _find(name)
    try:
        server = _browser_sign_in(server["id"])
    except ConnectorError as exc:
        _fail(exc)
        return
    console.print(
        f"[green]✓[/green] {server['name']} conectado · {len(server['tools'])} herramientas."
    )


@mcp.command("logout")
@click.argument("name")
def logout(name: str) -> None:
    """Cierra la sesión (el conector se queda)."""
    server = _hub().disconnect(_find(name)["id"])
    console.print(f"{server['name']}: sesión cerrada.")


@mcp.command("remove")
@click.argument("name")
def remove(name: str) -> None:
    """Quita un conector y su sesión."""
    server = _find(name)
    _hub().remove(server["id"])
    console.print(f"«{server['name']}» quitado.")


# -- tools -------------------------------------------------------------------
@mcp.command("tools")
@click.argument("name")
def tools(name: str) -> None:
    """Las herramientas de un conector y su permiso."""
    from openjarvis.mcp.hub import PERMISSION_ES, ConnectorError

    try:
        server = _hub().refresh_tools(_find(name)["id"])
    except ConnectorError as exc:
        _fail(exc)
        return
    for tool in server["tools"]:
        console.print(
            f"[bold]{tool['name']}[/bold]  ({PERMISSION_ES[tool['permission']]})"
        )
        if tool["description"]:
            console.print(f"  {tool['description'][:160]}")


@mcp.command("call")
@click.argument("name")
@click.argument("tool")
@click.argument("arguments", default="{}")
def call(name: str, tool: str, arguments: str) -> None:
    """Usa una herramienta a mano (cuenta como aprobada; «Nunca» la bloquea)."""
    from openjarvis.mcp.hub import ConnectorError

    try:
        args = json.loads(arguments)
        result = _hub().call(_find(name)["id"], tool, args, approved=True)
    except (ValueError, ConnectorError) as exc:
        _fail(exc)
        return
    for part in result.get("content") or []:
        console.print(
            part.get("text", "")
            if part.get("type") == "text"
            else f"[{part.get('type')}]"
        )
    if result.get("isError"):
        raise SystemExit(1)


@mcp.command("permiso")
@click.argument("name")
@click.argument("tool")
@click.argument("permission", type=click.Choice(["allow", "ask", "block"]))
def permiso(name: str, tool: str, permission: str) -> None:
    """Permiso de una herramienta («*» = todas): allow, ask o block."""
    hub = _hub()
    server = _find(name)
    if tool == "*":
        hub.set_all_permissions(server["id"], permission)
    else:
        hub.set_permission(server["id"], tool, permission)
    console.print("Hecho.")


# -- Sergio as an MCP server ------------------------------------------------
@mcp.command("serve")
@click.option(
    "--tools", "only", default="", help="Solo estas herramientas (separadas por comas)."
)
def serve(only: str) -> None:
    """Sirve las herramientas de Sergio por MCP (stdio), para Claude u otros.

    En Claude Desktop: {"mcpServers": {"sergio": {"command": "sergio", "args": ["mcp", "serve"]}}}
    """
    from openjarvis.mcp.protocol import MCPRequest, MCPResponse
    from openjarvis.mcp.server import MCPServer

    server = MCPServer()
    if only:
        keep = {name.strip() for name in only.split(",") if name.strip()}
        server = MCPServer([t for t in server.get_tools() if t.spec.name in keep])
    server.SERVER_NAME = "sergio"
    out = sys.stdout
    # Anything else printing to stdout would break the protocol.
    sys.stdout = sys.stderr
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict) or "method" not in message:
            continue  # a response from the client: nothing to do
        if "id" not in message:
            continue  # a notification (e.g. notifications/initialized)
        try:
            request = MCPRequest(
                method=message["method"],
                params=message.get("params") or {},
                id=message["id"],
            )
            response = server.handle(request)
        except Exception as exc:  # noqa: BLE001 - always answer the client
            response = MCPResponse.error_response(message.get("id"), -32603, str(exc))
        out.write(response.to_json() + "\n")
        out.flush()


# Spanish names for the same commands.
for _es, _cmd in (
    ("añadir", add),
    ("lista", list_cmd),
    ("ver", get),
    ("conectar", login),
    ("desconectar", logout),
    ("quitar", remove),
    ("herramientas", tools),
    ("usar", call),
    ("servir", serve),
):
    mcp.add_command(_cmd, _es)


__all__ = ["claude_desktop_configs", "mcp"]

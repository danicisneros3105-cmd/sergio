"""What a Node does through code, not through the model: commands, MCP, APIs.

The model only *asks* (``<cli>git log -5</cli>``, ``<mcp servidor="x"
herramienta="y">{…}</mcp>``, ``<api nombre="crm" metodo="GET"
ruta="/clients"/>``); this module checks the request against what you
allowed and runs it, and the real output goes back to the Node. Nothing is
invented in between and nothing runs that you did not allow.

* **CLI**: only the programs on the Node's list, with the arguments the
  entry allows (``git status`` allows only ``git status…``), no shell, in
  the Node's own computer folder, 60 s at most, output capped.
* **MCP**: the servers you added (a command for stdio, or a URL).
* **API** (Dev plan): your base URL with your key added by code — the key is
  never shown to the model. GET follows the «api» rule; anything that
  changes data always needs your approval.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

from openjarvis.nodes.store import BLOCKED_PROGRAMS, Node, NodeError, NodeStore

OUTPUT_LIMIT = 12_000
CLI_TIMEOUT = 60
API_TIMEOUT = 20
SHELL_CHARS = re.compile(r"[;&|`$<>]|\$\(|\n")


def _cap(text: str, limit: int = OUTPUT_LIMIT) -> str:
    text = text or ""
    return (
        text
        if len(text) <= limit
        else text[:limit] + f"\n… (recortado: {len(text) - limit} caracteres más)"
    )


# -- CLI ---------------------------------------------------------------------------
def cli_entry(node: Node, command: str) -> Dict[str, Any]:
    """The allow-list entry that permits *command*, or NodeError."""
    if SHELL_CHARS.search(command or ""):
        raise NodeError("Sin tuberías, redirecciones ni varios comandos: uno a la vez.")
    try:
        argv = shlex.split(command or "")
    except ValueError as exc:
        raise NodeError(f"Comando mal escrito: {exc}") from exc
    if not argv:
        raise NodeError("Comando vacío.")
    program = os.path.basename(argv[0])
    if program in BLOCKED_PROGRAMS:
        raise NodeError(f"«{program}» nunca está permitido.")
    for entry in node.connections.get("cli", []):
        allowed = shlex.split(entry["command"])
        if (
            os.path.basename(allowed[0]) == program
            and argv[: len(allowed)][1:] == allowed[1:]
        ):
            return {**entry, "argv": argv}
    raise NodeError(f"«{program}» no está en los comandos permitidos de {node.name}.")


def run_cli(store: NodeStore, node: Node, command: str) -> str:
    entry = cli_entry(node, command)
    env = {
        k: os.environ[k]
        for k in ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "TEMP", "TMP")
        if k in os.environ
    }
    try:
        done = subprocess.run(
            entry["argv"],
            cwd=store.computer(node.id),
            env=env,
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT,
            shell=False,
        )
    except FileNotFoundError:
        return f"No encuentro el programa «{entry['argv'][0]}» en este equipo."
    except subprocess.TimeoutExpired:
        return f"«{command}» tardó más de {CLI_TIMEOUT} s y lo detuve."
    out = (done.stdout or "") + (("\n[stderr]\n" + done.stderr) if done.stderr else "")
    return _cap(f"$ {command}\n(código de salida {done.returncode})\n{out}")


# -- MCP ---------------------------------------------------------------------------
def _mcp_client(entry: Dict[str, Any]):  # noqa: ANN202
    from openjarvis.mcp.client import MCPClient
    from openjarvis.mcp.transport import StdioTransport, StreamableHTTPTransport

    if entry.get("url"):
        transport = StreamableHTTPTransport(entry["url"], request_timeout=60.0)
    else:
        transport = StdioTransport(shlex.split(entry["command"]), response_timeout=60.0)
    client = MCPClient(transport)
    client.initialize()
    return client


def mcp_entry(node: Node, server: str) -> Dict[str, Any]:
    for entry in node.connections.get("mcp", []):
        if entry["name"].lower() == (server or "").strip().lower():
            return entry
    raise NodeError(f"No hay un servidor MCP «{server}» en {node.name}.")


def mcp_tools(entry: Dict[str, Any]) -> List[Dict[str, str]]:
    client = _mcp_client(entry)
    try:
        return [
            {"name": t.name, "description": (t.description or "")[:200]}
            for t in client.list_tools()
        ]
    finally:
        client.close()


def run_mcp(node: Node, server: str, tool: str, args: Any) -> str:
    entry = mcp_entry(node, server)
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except ValueError as exc:
            raise NodeError(
                f"Los argumentos para MCP no son JSON válido: {exc}"
            ) from exc
    if not isinstance(args, dict):
        raise NodeError("Los argumentos para MCP deben ser un objeto JSON.")
    client = _mcp_client(entry)
    try:
        result = client.call_tool(tool, args)
    finally:
        client.close()
    parts = []
    for item in (result or {}).get("content") or []:
        if isinstance(item, dict):
            parts.append(str(item.get("text") or json.dumps(item, ensure_ascii=False)))
    text = "\n".join(parts) or json.dumps(result, ensure_ascii=False)
    return _cap(("ERROR: " if (result or {}).get("isError") else "") + text)


# -- API (Dev plan) ----------------------------------------------------------------
def api_allowed() -> bool:
    from openjarvis.tiers import has_feature

    return has_feature("node_api")


def api_entry(node: Node, name: str) -> Dict[str, Any]:
    for entry in node.connections.get("api", []):
        if entry["name"].lower() == (name or "").strip().lower():
            return entry
    raise NodeError(f"No hay una API «{name}» en {node.name}.")


def api_url(entry: Dict[str, Any], path: str) -> str:
    """Only paths under the base URL: never another host."""
    path = (path or "/").strip()
    if re.match(r"^[a-z][a-z0-9+.\-]*:", path, re.I) or path.startswith("//"):
        raise NodeError("La ruta debe ser relativa a la API (p. ej. /clientes).")
    base = entry["base_url"].rstrip("/") + "/"
    url = urljoin(base, path.lstrip("/"))
    if urlsplit(url).netloc != urlsplit(base).netloc or not url.startswith(
        base.rstrip("/")
    ):
        raise NodeError("Esa ruta sale de la API configurada.")
    return url


def run_api(
    store: NodeStore,
    node: Node,
    name: str,
    method: str,
    path: str,
    body: Optional[str] = None,
    http: Any = None,
) -> str:
    if not api_allowed():
        raise NodeError(
            "Las APIs propias en los Nodes son del plan Dev (sergio planes)."
        )
    method = (method or "GET").upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        raise NodeError("Método HTTP no válido.")
    entry = api_entry(node, name)
    url = api_url(entry, path)
    headers = {"Accept": "application/json, text/plain;q=0.9, */*;q=0.5"}
    secret = store.secret(node.id, entry["id"])
    if secret:
        headers[entry.get("auth_header") or "Authorization"] = (
            f"{entry.get('prefix')} {secret}".strip() if entry.get("prefix") else secret
        )
    payload = None
    if body and method != "GET":
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise NodeError(f"El cuerpo no es JSON válido: {exc}") from exc
    if http is None:
        import httpx

        http = httpx.Client(timeout=API_TIMEOUT, follow_redirects=False)
    resp = http.request(method, url, headers=headers, json=payload)
    text = resp.text
    if secret:
        text = text.replace(secret, "•••")  # an echoed key never reaches the model
    return _cap(f"{method} {path} → {resp.status_code}\n{text}")


__all__ = [
    "api_allowed",
    "api_entry",
    "api_url",
    "cli_entry",
    "mcp_entry",
    "mcp_tools",
    "run_api",
    "run_cli",
    "run_mcp",
]

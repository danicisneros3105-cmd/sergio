"""Owner-installed CLI/MCP connections. No shell and no automatic installation."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from typing import Any

from openjarvis.security.process_runner import run_bounded


class ReviewTickets:
    def __init__(self):
        self.lock = threading.Lock()
        self.tickets: dict[str, tuple[float, str]] = {}

    @staticmethod
    def digest(payload: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()

    def issue(self, payload: dict[str, Any]) -> str:
        with self.lock:
            now = time.monotonic()
            self.tickets = {k: v for k, v in self.tickets.items() if v[0] > now}
            if len(self.tickets) >= 100:
                raise ValueError("Demasiadas revisiones pendientes")
            ticket = secrets.token_urlsafe(32)
            self.tickets[ticket] = (now + 120, self.digest(payload))
            return ticket

    def consume(self, ticket: str, payload: dict[str, Any]) -> None:
        with self.lock:
            grant = self.tickets.pop(ticket, None)
        if (
            not grant
            or grant[0] <= time.monotonic()
            or not secrets.compare_digest(grant[1], self.digest(payload))
        ):
            raise PermissionError(
                "Revisa de nuevo la acción: autorización vencida o distinta"
            )


def clean_env() -> dict[str, str]:
    # Configured credentials belong to the connection, not the inherited process.
    return {
        k: v
        for k, v in os.environ.items()
        if k.upper()
        in {
            "PATH",
            "HOME",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
        }
    }


def run_connection(
    spec: dict[str, Any],
    arguments: list[str],
    tool: str = "",
    tool_arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    command = [*spec["command"], *arguments]
    if spec["kind"] == "cli":
        result = run_bounded(
            command, timeout=30, max_output_bytes=64_000, env=clean_env()
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "truncated": result.truncated,
            "timed_out": result.timed_out,
        }
    from openjarvis.mcp.client import MCPClient
    from openjarvis.mcp.transport import StdioTransport

    if arguments:
        raise ValueError("La prueba MCP no admite argumentos adicionales")
    # Discovery and tool calls use the same exact-payload review boundary.
    with MCPClient(
        StdioTransport(command, response_timeout=10, env=clean_env())
    ) as client:
        capabilities = client.initialize()
        if tool:
            result = client.call_tool(tool, tool_arguments or {})
            return {"result": result}
        tools = client.list_tools()
        return {
            "capabilities": capabilities,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description[:500],
                    "parameters": t.parameters,
                }
                for t in tools[:100]
            ],
        }


__all__ = ["ReviewTickets", "clean_env", "run_connection"]

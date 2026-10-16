"""Adapt a real CLI to the existing connector permission and tool pipeline.

This is an in-process adapter, not an external MCP server. No shell, package
installation or command is executed while connecting. CLI calls are bounded
and require approval by default. This is not filesystem isolation.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from typing import Any

from openjarvis.mcp.local import local_environment, validate_command
from openjarvis.mcp.protocol import MCPRequest, MCPResponse
from openjarvis.mcp.transport import MCPTransport
from openjarvis.security.process_runner import run_bounded


class CLITransport(MCPTransport):
    def __init__(
        self, command: list[str], *, cwd: str, env: dict[str, str] | None = None
    ):
        if (
            not isinstance(cwd, str)
            or not cwd.strip()
            or not Path(cwd).expanduser().is_absolute()
        ):
            raise ValueError(
                "Indique la ruta completa de una carpeta de trabajo existente."
            )
        self.command = validate_command(command)
        self.env = local_environment(env)
        executable = shutil.which(self.command[0], path=self.env.get("PATH"))
        if not executable:
            raise ValueError(
                f"No se encuentra el ejecutable «{self.command[0]}» en el motor de Sergio."
            )
        if Path(executable).suffix.lower() in (".bat", ".cmd"):
            raise ValueError(
                "Use el ejecutable .exe o su intérprete explícito, no un archivo .bat/.cmd."
            )
        self.command[0] = executable
        self.cwd = str(Path(cwd).expanduser().resolve(strict=True))
        if not Path(self.cwd).is_dir():
            raise ValueError("La carpeta de trabajo debe existir.")
        self.closed = False

    def send(self, request: MCPRequest) -> MCPResponse:
        if self.closed:
            raise RuntimeError("CLI desconectada.")
        if request.method == "initialize":
            result: Any = {
                "protocolVersion": request.params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "Sergio CLI", "version": "1.0"},
            }
        elif request.method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "run",
                        "title": "Ejecutar CLI",
                        "description": (
                            f"Run the configured CLI in {self.cwd}. "
                            "Ask for approval; may modify files or services."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "arguments": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "maxItems": 255,
                                },
                                "timeout": {
                                    "type": "number",
                                    "minimum": 0.1,
                                    "maximum": 90,
                                    "default": 30,
                                },
                            },
                            "additionalProperties": False,
                        },
                        "annotations": {
                            "readOnlyHint": False,
                            "destructiveHint": True,
                            "idempotentHint": False,
                        },
                    }
                ]
            }
        elif request.method == "tools/call":
            try:
                result = self._call(request.params)
            except (ValueError, TypeError, OSError) as exc:
                result = {
                    "isError": True,
                    "content": [{"type": "text", "text": str(exc)[:1000]}],
                }
        elif request.method.startswith("notifications/") or request.method == "ping":
            result = {}
        else:
            return MCPResponse(
                id=request.id,
                error={"code": -32601, "message": "Método no compatible."},
            )
        return MCPResponse(id=request.id, result=result)

    def _call(self, params: dict) -> dict:
        args = params.get("arguments", {})
        if (
            params.get("name") != "run"
            or not isinstance(args, dict)
            or set(args) - {"arguments", "timeout"}
        ):
            raise ValueError("Herramienta o parámetros CLI no válidos.")
        argv = args.get("arguments", [])
        if not isinstance(argv, list):
            raise ValueError("Los argumentos deben ser una lista de textos.")
        command = validate_command([*self.command, *argv])
        timeout = args.get("timeout", 30)
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0.1 <= timeout <= 90
        ):
            raise ValueError("El tiempo máximo debe estar entre 0,1 y 90 segundos.")
        out = run_bounded(
            command, cwd=self.cwd, env=self.env, timeout=timeout, max_output_bytes=32768
        )
        data = {
            "stdout": out.stdout,
            "stderr": out.stderr,
            "exit_code": out.returncode,
            "timed_out": out.timed_out,
            "truncated": out.truncated,
        }
        return {
            "isError": out.timed_out or out.returncode != 0,
            "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
        }

    def close(self) -> None:
        self.closed = True


__all__ = ["CLITransport"]

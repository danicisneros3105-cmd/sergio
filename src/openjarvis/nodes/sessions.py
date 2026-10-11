"""Bounded, explicitly owned MCP sessions for multi-action browser tasks."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from openjarvis.nodes.integrations import ReviewTickets, clean_env


class SessionBusy(RuntimeError):
    pass


@dataclass
class _Session:
    digest: str
    client: Any
    capabilities: dict
    timer: threading.Timer | None = None


class MCPSessions:
    def __init__(self, *, idle_seconds: float = 120, capacity: int = 2):
        self._lock = threading.RLock()
        self._sessions: dict[tuple[str, str], _Session] = {}
        self._idle_seconds = idle_seconds
        self._capacity = capacity
        self._closed = False
        self._revision = 0

    def revision(self) -> int:
        # A read must not block the ASGI event loop behind a browser request.
        # run() checks this revision again while holding the execution lock.
        return self._revision

    def _expire(self, key, expected_timer):
        with self._lock:
            session = self._sessions.get(key)
            if session and session.timer is expected_timer:
                self.close(key)

    def _arm(self, key, session):
        if session.timer:
            session.timer.cancel()
        timer = threading.Timer(self._idle_seconds, lambda: self._expire(key, timer))
        timer.daemon = True
        session.timer = timer
        timer.start()

    def run(
        self,
        key,
        spec,
        tool: str,
        arguments: dict,
        expected_revision: int | None = None,
    ) -> dict:
        # Serialization also prevents two reviews acting on different page
        # states simultaneously. Busy requests fail instead of forming a queue.
        if not self._lock.acquire(timeout=0.1):
            raise SessionBusy(
                "Una sesión MCP está ejecutando una acción; espera a que termine"
            )
        try:
            if self._closed:
                raise RuntimeError("Sesiones MCP cerradas")
            if expected_revision is not None and expected_revision != self._revision:
                raise PermissionError(
                    "La sesión cambió tras la revisión; revisa de nuevo"
                )
            digest = ReviewTickets.digest(spec)
            session = self._sessions.get(key)
            if session and session.digest != digest:
                self.close(key)
                session = None
            if session is None:
                if len(self._sessions) >= self._capacity:
                    raise SessionBusy("Cierra una sesión MCP antes de abrir otra")
                from openjarvis.mcp.client import MCPClient
                from openjarvis.mcp.transport import StdioTransport

                env = {**clean_env(), "ANONYMIZED_TELEMETRY": "false"}
                client = MCPClient(
                    StdioTransport(spec["command"], response_timeout=30, env=env)
                )
                try:
                    capabilities = client.initialize()
                except BaseException:
                    client.close()
                    raise
                session = _Session(digest, client, capabilities)
                self._sessions[key] = session
            if session.timer:
                session.timer.cancel()
                session.timer = None
            try:
                if tool:
                    result = {"result": session.client.call_tool(tool, arguments)}
                else:
                    result = {
                        "capabilities": session.capabilities,
                        "tools": [
                            {
                                "name": t.name,
                                "description": t.description[:500],
                                "parameters": t.parameters,
                            }
                            for t in session.client.list_tools()[:100]
                        ],
                    }
            except BaseException:
                # No automatic replay: the failed request may have had effects.
                self.close(key)
                raise
            self._arm(key, session)
            self._revision += 1
            return {
                **result,
                "session_active": True,
                "idle_seconds": self._idle_seconds,
            }
        finally:
            self._lock.release()

    def close(self, key) -> None:
        with self._lock:
            self._revision += 1
            session = self._sessions.pop(key, None)
            if session:
                if session.timer:
                    session.timer.cancel()
                session.client.close()

    def close_all(self) -> None:
        with self._lock:
            self._closed = True
            for key in list(self._sessions):
                self.close(key)

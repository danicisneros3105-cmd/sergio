"""MCP transport implementations."""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from openjarvis.mcp.protocol import MCPRequest, MCPResponse

if TYPE_CHECKING:
    from openjarvis.mcp.server import MCPServer

logger = logging.getLogger(__name__)


class MCPAuthRequired(RuntimeError):
    """The server wants a (new) sign-in; ``challenge`` is its WWW-Authenticate."""

    def __init__(self, message: str, challenge: str = "") -> None:
        super().__init__(message)
        self.challenge = challenge


class MCPTransport(ABC):
    """Abstract transport layer for MCP communication."""

    @abstractmethod
    def send(self, request: MCPRequest) -> MCPResponse:
        """Send a request and return the response."""

    def send_notification(self, request: MCPRequest) -> None:
        """Send a JSON-RPC notification (no response expected).

        The default implementation delegates to :meth:`send` and discards the
        response.  Transports may override this when the server returns no
        body for notifications (e.g. HTTP 202 Accepted).
        """
        self.send(request)

    @abstractmethod
    def close(self) -> None:
        """Release transport resources."""


class InProcessTransport(MCPTransport):
    """Direct in-process transport for testing.

    Routes requests directly to an ``MCPServer`` instance without
    serialization overhead.
    """

    def __init__(self, server: MCPServer) -> None:
        self._server = server

    def send(self, request: MCPRequest) -> MCPResponse:
        """Dispatch request directly to the server."""
        return self._server.handle(request)

    def close(self) -> None:
        """No resources to release."""


class StdioTransport(MCPTransport):
    """JSON-RPC over stdin/stdout subprocess transport.

    Launches a subprocess and communicates via JSON lines on
    stdin/stdout.
    """

    _STDOUT_QUEUE_SIZE = 1024
    _STDOUT_EOF = object()

    def __init__(
        self,
        command: List[str],
        *,
        response_timeout: float = 600.0,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        if response_timeout <= 0:
            raise ValueError("response_timeout must be positive")
        self._command = command
        self._response_timeout = response_timeout
        self._env = env
        self._process: Optional[subprocess.Popen[str]] = None
        self._stdout_queue: queue.Queue[Any] = queue.Queue(
            maxsize=self._STDOUT_QUEUE_SIZE
        )
        self._reader_stop = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        # A single stdout stream cannot safely serve multiple independent
        # readers: one request could consume and discard another request's
        # response. Serialize complete write/read exchanges (and notification
        # writes) so response correlation remains lossless.
        self._request_lock = threading.Lock()
        self._start()

    def _start(self) -> None:
        """Start the subprocess."""
        self._job = None
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self._env,
            start_new_session=os.name != "nt",
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x4)
            if os.name == "nt"
            else 0,
        )
        if os.name == "nt":
            from openjarvis.security.windows_job import WindowsJob

            try:
                self._job = WindowsJob(int(self._process._handle))
            except BaseException:
                self._process.kill()
                self._process.wait(timeout=5)
                raise
        self._reader_thread = threading.Thread(
            target=self._read_stdout,
            name="openjarvis-mcp-stdout",
            daemon=True,
        )
        self._reader_thread.start()
        # Nothing else reads stderr. Once the child writes more than the OS
        # pipe buffer to it, the child blocks on that write and never gets
        # to answer on stdout. Drain it continuously on a background thread.
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(self._process,),
            name="openjarvis-mcp-stderr",
            daemon=True,
        )
        self._stderr_thread.start()

    def _read_stdout(self) -> None:
        """Read the subprocess pipe without tying up the request thread.

        A dedicated reader is portable to Windows, where ``select`` cannot
        wait on an anonymous subprocess pipe. The bounded queue also applies
        backpressure if a server writes stdout while no request is reading.
        """
        proc = self._process
        stdout = proc.stdout if proc is not None else None
        if stdout is None:
            return

        try:
            while not self._reader_stop.is_set():
                line = stdout.readline(1_048_577)
                if len(line) > 1_048_576:
                    break  # reject oversized JSON before it enters the queue
                if not line:
                    break
                while not self._reader_stop.is_set():
                    try:
                        self._stdout_queue.put(line, timeout=0.1)
                        break
                    except queue.Full:
                        continue
        finally:
            while not self._reader_stop.is_set():
                try:
                    self._stdout_queue.put(self._STDOUT_EOF, timeout=0.1)
                    break
                except queue.Full:
                    continue

    def _next_stdout_line(self, deadline: float, request_id: Any) -> str:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"Timed out waiting for MCP response id {request_id!r}")
        try:
            item = self._stdout_queue.get(timeout=remaining)
        except queue.Empty as exc:
            raise RuntimeError(
                f"Timed out waiting for MCP response id {request_id!r}"
            ) from exc
        if item is self._STDOUT_EOF:
            raise RuntimeError("No response from subprocess")
        return item

    def _drain_stderr(self, proc: subprocess.Popen[str]) -> None:
        """Continuously read the child's stderr so its pipe never fills."""
        if proc.stderr is None:
            return
        while proc.stderr.read(4096):
            # Drain bounded chunks without retaining or logging server secrets.
            pass

    def send(self, request: MCPRequest) -> MCPResponse:
        """Write request as JSON line, read lines until the matching response.

        MCP servers may emit unsolicited notifications or stray/stale
        replies on stdout before the real response. Skip anything that
        isn't a well-formed JSON-RPC response carrying this request's id,
        rather than treating the first line as gospel (#751).
        """
        with self._request_lock:
            proc = self._process
            if proc is None or proc.stdin is None or proc.stdout is None:
                raise RuntimeError("Transport process is not running")

            line = request.to_json() + "\n"
            proc.stdin.write(line)
            proc.stdin.flush()

            deadline = time.monotonic() + self._response_timeout
            while True:
                # Check the wall-clock deadline even when a server continuously
                # floods stdout, so queued blank/noise/notification lines cannot
                # keep extending the request forever.
                response_line = self._next_stdout_line(deadline, request.id)
                response_line = response_line.strip()
                if not response_line:
                    continue

                try:
                    parsed = json.loads(response_line)
                except (json.JSONDecodeError, ValueError):
                    parsed = None

                is_response = (
                    isinstance(parsed, dict)
                    and "id" in parsed
                    and ("result" in parsed or "error" in parsed)
                    and parsed["id"] == request.id
                )
                if is_response:
                    return MCPResponse.from_json(response_line)

    def send_notification(self, request: MCPRequest) -> None:
        """Send a JSON-RPC notification — write only, never read.

        Overrides the base implementation: stdio servers do not reply
        to notifications, so the default ``send()`` would block forever
        on ``proc.stdout.readline()``.
        """
        with self._request_lock:
            proc = self._process
            if proc is None or proc.stdin is None:
                raise RuntimeError("Transport process is not running")
            line = request.to_json() + "\n"
            proc.stdin.write(line)
            proc.stdin.flush()

    def close(self) -> None:
        """Terminate the subprocess."""
        if self._process is not None:
            self._reader_stop.set()
            # Wake a request waiting on the queue before stopping the process.
            try:
                self._stdout_queue.put_nowait(self._STDOUT_EOF)
            except queue.Full:
                try:
                    self._stdout_queue.get_nowait()
                    self._stdout_queue.put_nowait(self._STDOUT_EOF)
                except (queue.Empty, queue.Full):
                    pass
            from openjarvis.security.process_runner import terminate_tree

            if self._job:
                self._job.close()
                self._job = None
            else:
                terminate_tree(self._process)
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
            if self._reader_thread is not None:
                self._reader_thread.join(timeout=1)
                self._reader_thread = None
            self._process = None
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=5)
            self._stderr_thread = None


class StreamableHTTPTransport(MCPTransport):
    """MCP Streamable HTTP transport (JSON-RPC over HTTP).

    Uses a persistent ``httpx.Client`` session, tracks the
    ``Mcp-Session-Id`` header, and sends the ``Accept`` header
    required by the MCP Streamable HTTP specification.
    """

    def __init__(
        self,
        url: str,
        *,
        token: Optional[str] = None,
        connect_timeout: float = 10.0,
        request_timeout: float = 60.0,
        auth: Optional[Callable[[bool], Optional[str]]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        import httpx

        self._url = url
        self._token = token
        # ``auth(force_refresh)`` returns the current access token (or a
        # renewed one after a 401) — how OAuth connectors stay signed in.
        self._auth = auth
        self._extra_headers = dict(headers or {})
        self._session_id: Optional[str] = None
        self.protocol_version: Optional[str] = None
        self._client = httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=request_timeout,
                write=request_timeout,
                pool=connect_timeout,
            ),
        )

    def _safe_url(self) -> str:
        """Return scheme://host:port without path or query (avoids leaking tokens)."""
        from urllib.parse import urlparse

        parsed = urlparse(self._url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _build_headers(self) -> dict:
        """Build common request headers.

        Sends ``Authorization: Bearer <token>`` when the transport was
        constructed with a token (#461) — required by authenticated MCP
        servers such as Home Assistant's. Falsy tokens (None / empty
        string) deliberately do NOT send the header, matching the
        upstream MCP spec and the cfg.get("token") plumbing in the
        builder.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        headers.update(self._extra_headers)
        token = self._auth(False) if self._auth is not None else self._token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _post(self, request: MCPRequest) -> Any:
        """Post a request and return the raw httpx response."""
        import httpx

        headers = self._build_headers()
        try:
            response = self._client.post(
                self._url,
                json=request.to_dict(),
                headers=headers,
            )
            if response.status_code == 401 and self._auth is not None:
                # The token may have just expired: renew it once and retry.
                if self._auth(True):
                    response = self._client.post(
                        self._url, json=request.to_dict(), headers=self._build_headers()
                    )
            if response.status_code in (401, 403) and (
                self._auth is not None or "www-authenticate" in response.headers
            ):
                raise MCPAuthRequired(
                    "El servidor pide iniciar sesión de nuevo.",
                    response.headers.get("www-authenticate", ""),
                )
            if response.status_code == 404 and self._session_id is not None:
                # The server forgot our session: start a new one next time.
                self._session_id = None
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Failed to connect to MCP server at {self._safe_url()}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Timeout communicating with MCP server at {self._safe_url()}: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"MCP server at {self._safe_url()} returned HTTP "
                f"{exc.response.status_code}"
            ) from exc

        # Track session id from the first response
        new_session_id = response.headers.get("mcp-session-id")
        if new_session_id is not None:
            self._session_id = new_session_id
        return response

    @staticmethod
    def _extract_json_from_sse(text: str) -> str:
        """Extract JSON payload from an SSE response body.

        MCP Streamable HTTP servers may respond with ``text/event-stream``
        instead of ``application/json``.  In that case the body looks like::

            event: message
            data: {"jsonrpc":"2.0", ...}

        This helper finds the last ``data:`` line and returns its content,
        which is the actual JSON-RPC response.
        """
        last_data = ""
        for line in text.splitlines():
            if line.startswith("data:"):
                last_data = line[len("data:") :].strip()
        if not last_data:
            raise RuntimeError(
                "SSE response contained no 'data:' lines"
                " — cannot extract JSON-RPC payload"
            )
        return last_data

    @staticmethod
    def _response_from_sse(text: str, request_id: Any) -> Optional[str]:
        """The JSON-RPC message answering *request_id* in an SSE body (the
        stream may also carry notifications and progress before it)."""
        events: List[str] = []
        data: List[str] = []
        for line in text.splitlines() + [""]:
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif not line.strip() and data:
                events.append("\n".join(data))
                data = []
        for payload in events:
            try:
                message = json.loads(payload)
            except ValueError:
                continue
            if (
                isinstance(message, dict)
                and message.get("id") == request_id
                and ("result" in message or "error" in message)
            ):
                return payload
        return None

    def send(self, request: MCPRequest) -> MCPResponse:
        """Send request via HTTP POST following the MCP Streamable HTTP spec.

        Handles both ``application/json`` and ``text/event-stream`` responses
        as allowed by the MCP Streamable HTTP specification.
        """
        response = self._post(request)
        content_type = response.headers.get("content-type", "")
        body = response.text
        if "text/event-stream" in content_type or body.lstrip().startswith("event:"):
            body = self._response_from_sse(
                body, request.id
            ) or self._extract_json_from_sse(body)
        return MCPResponse.from_json(body)

    def send_notification(self, request: MCPRequest) -> None:
        """Send a notification — accept any 2xx, don't parse the body."""
        # Track session id but don't try to parse a JSON-RPC response.
        # Servers may return 202 Accepted with an empty body.
        self._post(request)

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()


class LegacySSETransport(MCPTransport):
    """The HTTP+SSE transport of MCP 2024-11-05 (URLs ending in ``/sse``).

    A GET opens an event stream whose first ``endpoint`` event says where to
    POST messages; every answer then arrives on that stream.
    """

    def __init__(
        self,
        url: str,
        *,
        auth: Optional[Callable[[bool], Optional[str]]] = None,
        token: Optional[str] = None,
        request_timeout: float = 60.0,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        import httpx

        self._url = url
        self._auth = auth
        self._token = token
        self._timeout = request_timeout
        self._extra_headers = dict(headers or {})
        self._client = httpx.Client(timeout=httpx.Timeout(10.0, read=None))
        self._endpoint: Optional[str] = None
        self._ready = threading.Event()
        self._waiting: Dict[Any, "queue.Queue[str]"] = {}
        self._lock = threading.Lock()
        self._closed = False
        self._error: Optional[BaseException] = None
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        if not self._ready.wait(15):
            self.close()
            raise self._error or RuntimeError(
                "El servidor SSE no indicó dónde enviar mensajes."
            )

    def _headers(self) -> Dict[str, str]:
        token = self._auth(False) if self._auth is not None else self._token
        headers = dict(self._extra_headers)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _listen(self) -> None:

        try:
            with self._client.stream(
                "GET",
                self._url,
                headers={"Accept": "text/event-stream", **self._headers()},
            ) as response:
                if response.status_code in (401, 403):
                    raise MCPAuthRequired(
                        "El servidor pide iniciar sesión.",
                        response.headers.get("www-authenticate", ""),
                    )
                response.raise_for_status()
                event, data = "message", []
                for line in response.iter_lines():
                    if self._closed:
                        return
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data.append(line[5:].lstrip())
                    elif not line.strip() and data:
                        payload = "\n".join(data)
                        data = []
                        if event == "endpoint":
                            self._endpoint = self._message_endpoint(payload)
                            self._ready.set()
                        else:
                            self._deliver(payload)
                        event = "message"
        except BaseException as exc:  # noqa: BLE001 - surfaced to callers
            self._error = exc
            self._ready.set()
            with self._lock:
                for box in self._waiting.values():
                    box.put("")

    def _message_endpoint(self, payload: str) -> str:
        from urllib.parse import urljoin, urlparse

        from openjarvis.mcp.oauth import validate_endpoint

        endpoint = validate_endpoint(urljoin(self._url, payload))
        source, target = urlparse(self._url), urlparse(endpoint)

        def origin(parts):
            return (
                parts.scheme,
                parts.hostname,
                parts.port or (443 if parts.scheme == "https" else 80),
            )

        if origin(source) != origin(target):
            raise RuntimeError("El servidor SSE indicó un destino de otro origen.")
        return endpoint

    def _deliver(self, payload: str) -> None:
        try:
            message = json.loads(payload)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        with self._lock:
            box = self._waiting.get(message.get("id"))
        if box is not None:
            box.put(payload)

    def _post(self, request: MCPRequest) -> None:
        if self._error is not None or not self._endpoint:
            raise self._error or RuntimeError("Sin conexión con el servidor SSE.")
        response = self._client.post(
            self._endpoint,
            json=request.to_dict(),
            headers={"Content-Type": "application/json", **self._headers()},
            timeout=self._timeout,
        )
        if response.status_code in (401, 403):
            raise MCPAuthRequired(
                "El servidor pide iniciar sesión.",
                response.headers.get("www-authenticate", ""),
            )
        response.raise_for_status()

    def send(self, request: MCPRequest) -> MCPResponse:
        box: "queue.Queue[str]" = queue.Queue()
        with self._lock:
            self._waiting[request.id] = box
        try:
            self._post(request)
            payload = box.get(timeout=self._timeout)
        except queue.Empty as exc:
            raise RuntimeError("El servidor SSE no respondió a tiempo.") from exc
        finally:
            with self._lock:
                self._waiting.pop(request.id, None)
        if not payload:
            raise self._error or RuntimeError("Se cerró la conexión SSE.")
        return MCPResponse.from_json(payload)

    def send_notification(self, request: MCPRequest) -> None:
        self._post(request)

    def close(self) -> None:
        self._closed = True
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 - closing is best effort
            pass


# Backward-compatible alias
SSETransport = StreamableHTTPTransport


__all__ = [
    "InProcessTransport",
    "LegacySSETransport",
    "MCPAuthRequired",
    "MCPTransport",
    "SSETransport",
    "StdioTransport",
    "StreamableHTTPTransport",
]

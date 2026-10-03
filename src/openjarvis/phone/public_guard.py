"""Only the phone/WhatsApp webhooks may be reached through the public tunnel.

The tunnel (ngrok/Cloudflare) forwards *every* path to the local server, and
a local install normally has no API key. Requests that arrive through the
tunnel are recognised by the forwarding headers the tunnel adds (or by the
public host name) and are refused unless they target one of the webhook
paths, which carry their own signatures/tokens. Local use is unaffected.
"""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlparse

# Paths Twilio/Meta must reach; each verifies its own signature or token.
PUBLIC_PATHS = ("/phone/incoming", "/phone/status", "/phone/ws")
PUBLIC_PREFIXES = ("/webhooks/",)

# Headers a reverse proxy/tunnel adds. A direct local request has none.
_FORWARD_HEADERS = (
    b"x-forwarded-for",
    b"x-forwarded-host",
    b"forwarded",
    b"cf-connecting-ip",
    b"ngrok-trace-id",
)


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def _public_host(config_getter: Callable[[], Any]) -> str:
    try:
        url = config_getter().phone.public_url or ""
    except Exception:  # noqa: BLE001
        return ""
    return (urlparse(url).hostname or "").lower()


class PublicExposureGuard:
    """Pure ASGI middleware (covers HTTP and WebSocket)."""

    def __init__(self, app: Any, config_getter: Callable[[], Any]) -> None:
        self.app = app
        self._config_getter = config_getter
        self._host: str | None = None

    def _from_tunnel(self, scope: dict) -> bool:
        headers = dict(scope.get("headers") or [])
        if any(name in headers for name in _FORWARD_HEADERS):
            return True
        if self._host is None:
            self._host = _public_host(self._config_getter)
        host = headers.get(b"host", b"").decode("latin-1").split(":")[0].lower()
        return bool(self._host) and host == self._host

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] in ("http", "websocket") and self._from_tunnel(scope):
            if not is_public_path(scope.get("path", "")):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [(b"content-type", b"text/plain")],
                    }
                )
                await send({"type": "http.response.body", "body": b"Forbidden"})
                return
        await self.app(scope, receive, send)


__all__ = ["PUBLIC_PATHS", "PublicExposureGuard", "is_public_path"]

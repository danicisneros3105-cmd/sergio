"""Phone access to Sergio: a pairing token and a guard for relayed requests.

``sergio movil`` opens a Cloudflare tunnel to this server and shows a QR code.
Requests that arrive through a tunnel or reverse proxy carry forwarding
headers (``Cf-Connecting-Ip``, ``X-Forwarded-For`` …); those must present the
phone's token, for HTTP and WebSocket alike, except for the app shell (HTML,
JS, icons, manifest, service worker) which holds no data. Requests made on
this computer are untouched, so the desktop app keeps working without a key.

The token lives in ``~/.openjarvis/mobile.json`` (0600); ``sergio movil
olvidar`` replaces it, which unpairs every phone at once. It travels to the
phone inside the URL fragment (``#pair=…``), which browsers never send to a
server, so it does not end up in tunnel or proxy logs.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

FORWARDED_HEADERS = (
    b"cf-connecting-ip",
    b"cf-ray",
    b"x-forwarded-for",
    b"x-real-ip",
    b"forwarded",
)
_PUBLIC_EXACT = {
    "/v1/mcp/oauth/callback",  # Expiring single-use OAuth state and PKCE.
    "/v1/healthdata/ingest",  # Phones push health data; the route checks its own sync key.
    "/",
    "/health",
    "/manifest.webmanifest",
    "/sw.js",
    "/registerSW.js",
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/pwa-192x192.png",
    "/pwa-512x512.png",
}
_PUBLIC_PREFIXES = ("/assets/", "/workbox-")
_PROTECTED_PREFIXES = (
    "/v1",
    "/api",
    "/ws",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/dashboard",
)
_WS_KEY_PREFIX = "openjarvis.key.b64url."
_cache: Dict[str, Any] = {"mtime": None, "token": ""}


def _home() -> Path:
    return Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")


def token_path() -> Path:
    return _home() / "mobile.json"


def current_token() -> str:
    """The phone token, or '' when no phone was ever paired (cached by mtime)."""
    path = token_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ""
    if _cache["mtime"] != mtime:
        try:
            _cache["token"] = str(json.loads(path.read_text("utf-8")).get("token", ""))
        except (OSError, ValueError):
            _cache["token"] = ""
        _cache["mtime"] = mtime
    return _cache["token"]


def ensure_token(*, renew: bool = False) -> str:
    """Create the phone token if missing (or always, with *renew*)."""
    token = "" if renew else current_token()
    if token:
        return token
    token = f"sm_{secrets.token_urlsafe(32)}"
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"token": token, "created": time.time()}), "utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return token


def valid_token(presented: str) -> bool:
    expected = current_token()
    if not expected or not presented:
        return False
    return secrets.compare_digest(
        presented.encode("utf-8", "replace"), expected.encode("utf-8")
    )


def pair_url(base: str, token: str) -> str:
    """The link the QR code holds: the app plus the token in the fragment."""
    return f"{base.rstrip('/')}/#pair={token}"


def _is_public(path: str) -> bool:
    if path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES):
        return True
    # Single-page-app routes (/pensar, /faces …) return the HTML shell only.
    return (
        not path.startswith(_PROTECTED_PREFIXES) and "." not in path.rsplit("/", 1)[-1]
    )


def _bearer(headers: Dict[bytes, bytes]) -> str:
    scheme, _, token = (
        headers.get(b"authorization", b"").decode("latin-1").partition(" ")
    )
    return token.strip() if scheme.lower() == "bearer" else ""


def _ws_protocol_token(headers: Dict[bytes, bytes]) -> str:
    offered = headers.get(b"sec-websocket-protocol", b"").decode("latin-1")
    for item in offered.split(","):
        item = item.strip()
        if item.startswith(_WS_KEY_PREFIX):
            encoded = item[len(_WS_KEY_PREFIX) :]
            try:
                return base64.urlsafe_b64decode(
                    encoded + "=" * (-len(encoded) % 4)
                ).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return ""
    return ""


Scope = Dict[str, Any]
ASGIApp = Callable[
    [Scope, Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]],
    Awaitable[None],
]


class RemoteAccessMiddleware:
    """Require the phone token (or the server's API key) on relayed requests."""

    def __init__(self, app: ASGIApp, api_key: str = "") -> None:
        self.app = app
        self.api_key = api_key or os.environ.get("OPENJARVIS_API_KEY", "")

    def _allowed(self, presented: str) -> bool:
        if valid_token(presented):
            return True
        return bool(self.api_key) and secrets.compare_digest(
            presented.encode("utf-8", "replace"), self.api_key.encode("utf-8")
        )

    async def __call__(
        self,
        scope: Scope,
        receive: Callable[..., Awaitable[Any]],
        send: Callable[..., Awaitable[Any]],
    ) -> None:
        kind = scope.get("type")
        if kind not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        if not any(h in headers for h in FORWARDED_HEADERS):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if kind == "http":
            if (
                scope.get("method") == "OPTIONS"
                and b"access-control-request-method" in headers
            ):
                return await self.app(scope, receive, send)
            if _is_public(path) or self._allowed(_bearer(headers)):
                return await self.app(scope, receive, send)
            body = json.dumps(
                {"detail": "Pair this phone first: run `sergio movil` on your PC."}
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        presented = _bearer(headers) or _ws_protocol_token(headers)
        if self._allowed(presented):
            return await self.app(scope, receive, send)
        await send({"type": "websocket.close", "code": 4401})


def parse_tunnel_url(line: str) -> Optional[str]:
    """The public URL in a cloudflared log line, if it has one."""
    import re

    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
    return m.group(0) if m else None


def split_pair(fragment: str) -> Tuple[str, str]:
    """(``pair``, token) from a URL fragment — mirrors the frontend parser."""
    key, _, value = fragment.lstrip("#").partition("=")
    return key, value


__all__ = [
    "RemoteAccessMiddleware",
    "current_token",
    "ensure_token",
    "pair_url",
    "parse_tunnel_url",
    "token_path",
    "valid_token",
]

"""Security middleware -- HTTP security headers and request guards."""

from __future__ import annotations

from typing import Any

__all__ = [
    "SECURITY_HEADERS",
    "content_security_policy",
    "create_security_middleware",
]

# Ports of the bundled extensions (OpenClacky, 3D globe) and of Creator's
# programs (OpenDesign, VSCodium web) that the UI embeds.
_CREATOR_EMBED_PORTS = (8790, 8791)
_DEFAULT_EMBED_PORTS = (7070, 4173, *_CREATOR_EMBED_PORTS)


def content_security_policy(embed_ports: tuple[int, ...] = _DEFAULT_EMBED_PORTS) -> str:
    """CSP for the served UI.

    * media-src blob: plays synthesized speech (arrives as a blob URL).
    * img-src/font-src data: — the built UI inlines small fonts and images.
    * frame-src lists only the local extension servers the UI embeds.
    * frame-ancestors 'self': only Sergio's own split screen may show its
      pages in a frame; any other site is still refused (clickjacking).
    * object-src 'none' and base-uri 'self': no plugins, and an injected
      <base> tag cannot send the page's links and scripts elsewhere.
    """
    frames = " ".join(
        f"http://{host}:{port}"
        for port in embed_ports
        for host in ("127.0.0.1", "localhost")
    )
    return (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "media-src 'self' blob:; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        f"frame-src 'self' {frames}; "
        "frame-ancestors 'self'; "
        "object-src 'none'; "
        "base-uri 'self'"
    )


def _embed_ports() -> tuple[int, ...]:
    try:
        from openjarvis.core.config import load_config

        ext = load_config().extensions
        return (int(ext.clacky.port), int(ext.globe.port), *_CREATOR_EMBED_PORTS)
    except Exception:  # noqa: BLE001 — fall back to the default ports
        return _DEFAULT_EMBED_PORTS


def create_security_middleware() -> Any:
    """Create a FastAPI middleware that adds security headers.

    Returns a middleware class/callable, or None if FastAPI is not available.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: SAMEORIGIN (the split screen frames its own pages)
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: camera=(), microphone=(), geolocation=()

    OPTIONS requests are passed through without headers so that
    CORS preflight is not blocked.
    """
    try:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from starlette.responses import Response
    except ImportError:
        return None

    csp = content_security_policy(_embed_ports())

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Response:
            # Let CORS preflight requests pass through without
            # security headers that would conflict with CORS.
            if request.method == "OPTIONS":
                return await call_next(request)

            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            # microphone/camera=(self): voice input and the Faces page use them from
            # this same origin only. An empty allowlist blocked its own features.
            response.headers["Permissions-Policy"] = (
                "camera=(self), microphone=(self), geolocation=()"
            )
            response.headers["Content-Security-Policy"] = csp
            return response

    return SecurityHeadersMiddleware


# Also export the header values as constants for testing
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), microphone=(self), geolocation=()",
    "Content-Security-Policy": content_security_policy(),
}

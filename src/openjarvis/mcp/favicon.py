"""The logo and colour of a service Sergio has no logo for, from its own site.

The owner (29 Oct 2026): «el MCP que tengo conectado aún está sin logo y
color de la marca». Sergio ships the Simple Icons logos of the best-known
services (``brands.json``); any other server the owner connects gets the
icon its own website publishes (``apple-touch-icon``, ``<link rel=icon>``
or ``/favicon.ico``), scaled to 64 px and saved on this computer, and its
colour is the strongest colour in that icon. It only names the service he
connected, like the other logos.

Only public https sites: never an IP, ``localhost`` or a private address.
"""

from __future__ import annotations

import io
import ipaddress
import json
import re
import socket
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urljoin, urlparse

MAX_BYTES = 512_000
SUBDOMAINS = ("mcp", "api", "server", "app", "www", "remote", "sse")
_ICON = re.compile(r"<link[^>]+rel=[\"']?([^\"'>]*icon[^\"'>]*)[\"']?[^>]*>", re.I)
_HREF = re.compile(r"href=[\"']?([^\"' >]+)", re.I)
_SIZES = re.compile(r"sizes=[\"']?(\d+)", re.I)


def site_of(url: str) -> str:
    """``https://mcp.notion.com/mcp`` → ``notion.com`` (the brand's own site)."""
    host = (urlparse(url).hostname or "").lower().strip(".")
    parts = host.split(".")
    while len(parts) > 2 and parts[0] in SUBDOMAINS:
        parts = parts[1:]
    return ".".join(parts)


def public(host: str, resolve: Callable[[str], list] = socket.getaddrinfo) -> bool:
    """A public internet name (never this computer or the local network)."""
    if (
        not host
        or host in ("localhost",)
        or host.endswith((".local", ".internal", ".lan"))
    ):
        return False
    try:
        ipaddress.ip_address(host)
        return False  # a bare IP is never a brand
    except ValueError:
        pass
    try:
        infos = resolve(host, 443)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError):
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


def _candidates(html: str, base: str) -> list:
    found = []
    for tag in re.findall(r"<link[^>]+>", html or "", re.I):
        rel = _ICON.search(tag)
        href = _HREF.search(tag)
        if not rel or not href:
            continue
        size = _SIZES.search(tag)
        score = int(size.group(1)) if size else 0
        if "apple-touch" in rel.group(1).lower():
            score = max(score, 180)
        found.append((score, urljoin(base, href.group(1))))
    found.sort(reverse=True)
    return [u for _s, u in found] + [urljoin(base, "/favicon.ico")]


def colour_of(png: bytes) -> str:
    """The strongest colour of an icon (hex, no '#'); grey when it has none."""
    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("RGBA").resize((32, 32))
    best, score = (110, 110, 115), 0.0
    counts: Dict[tuple, int] = {}
    for r, g, b, a in img.getdata():
        if a < 128:
            continue
        key = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
        counts[key] = counts.get(key, 0) + 1
    for (r, g, b), n in counts.items():
        hi, lo = max(r, g, b), min(r, g, b)
        sat = (hi - lo) / 255
        if hi < 40 or (lo > 225):  # black and white are the background
            continue
        s = n * (0.3 + sat)
        if s > score:
            best, score = (r, g, b), s
    return "%02x%02x%02x" % best


def logo(
    url: str,
    folder: Path,
    *,
    get: Optional[Callable[..., Any]] = None,
    resolve: Callable[[str], list] = socket.getaddrinfo,
) -> Dict[str, str]:
    """``{"site", "file", "hex"}`` for the service at *url* (cached), or {}."""
    site = site_of(url)
    if not site or not public(site, resolve):
        return {}
    folder.mkdir(parents=True, exist_ok=True)
    meta = folder / f"{site}.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8"))
        except ValueError:
            pass
    if get is None:
        import httpx

        def get(u: str) -> Any:  # noqa: ANN001
            return httpx.get(u, timeout=10, follow_redirects=True,
                             headers={"User-Agent": "Sergio/1.0 (logo)"})  # fmt: skip

    base = f"https://{site}/"
    try:
        page = get(base)
        html = page.text if getattr(page, "status_code", 200) < 400 else ""
    except Exception:  # noqa: BLE001 — try the plain favicon
        html = ""
    from PIL import Image

    for candidate in _candidates(html, base)[:5]:
        if urlparse(candidate).scheme != "https" or not public(
            urlparse(candidate).hostname or "", resolve
        ):
            continue
        try:
            r = get(candidate)
            data = r.content if getattr(r, "status_code", 200) < 400 else b""
            if not data or len(data) > MAX_BYTES:
                continue
            img = Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception:  # noqa: BLE001 — not an image: the next one
            continue
        img.thumbnail((64, 64))
        out = io.BytesIO()
        img.save(out, "PNG")
        png = out.getvalue()
        (folder / f"{site}.png").write_bytes(png)
        info = {"site": site, "file": f"{site}.png", "hex": colour_of(png)}
        meta.write_text(json.dumps(info), encoding="utf-8")
        return info
    return {}


__all__ = ["colour_of", "logo", "public", "site_of"]

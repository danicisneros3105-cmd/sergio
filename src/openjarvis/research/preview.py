"""A preview of a web page: title, description, picture and site (owner,
3 Nov 2026: «mejorar agent swarm y búsqueda en la web con imágenes y
preview»).

Read from the page's own Open Graph / Twitter / HTML tags, the way a chat app
shows a link. Only public https and http sites (never this computer or the
local network: ``mcp.favicon.public``), the first 400 KB, 8 s at most, and
kept on this computer for a day so the same link is not fetched twice.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urljoin, urlparse

MAX_BYTES = 400_000
DAY = 86400
UA = {"User-Agent": "Sergio/1.0 (link preview)"}
_META = re.compile(r"<meta\s+[^>]*>", re.I | re.S)
_ATTR = re.compile(r'([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.S)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _home() -> Path:
    from openjarvis.core.config import get_config_dir

    path = Path(get_config_dir()) / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse(page: str, url: str) -> Dict[str, str]:
    """The preview fields of an HTML page (relative picture links resolved)."""
    metas: Dict[str, str] = {}
    for tag in _META.findall(page[:MAX_BYTES]):
        attrs = {
            m.group(1).lower(): (m.group(3) or m.group(4) or m.group(5) or "")
            for m in _ATTR.finditer(tag)
        }
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and attrs.get("content") and key not in metas:
            metas[key] = html.unescape(attrs["content"]).strip()
    title_tag = _TITLE.search(page[:MAX_BYTES])
    title = (
        metas.get("og:title")
        or metas.get("twitter:title")
        or (html.unescape(title_tag.group(1)).strip() if title_tag else "")
    )
    desc = (
        metas.get("og:description")
        or metas.get("twitter:description")
        or metas.get("description")
        or ""
    )
    image = (
        metas.get("og:image")
        or metas.get("og:image:url")
        or metas.get("twitter:image")
        or ""
    )
    if image:
        image = urljoin(url, image)
        if not image.startswith(("https://", "http://")):
            image = ""
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return {
        "url": url,
        "title": " ".join(title.split())[:160],
        "description": " ".join(desc.split())[:300],
        "image": image[:600],
        "site": (metas.get("og:site_name") or host)[:80],
        "host": host,
    }


MAX_IMAGE = 2_000_000
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def keep_image(image_url: str, get: Callable[..., Any], is_public: Callable[[str], bool]) -> str:
    """The picture saved on this computer, served by Sergio (the app's content
    policy never loads pictures from other sites). Returns its path under
    /v1/vista-previa/img/, or "" when it cannot be used."""
    host = (urlparse(image_url).hostname or "").lower()
    if not host or not is_public(host):
        return ""
    name = hashlib.sha256(image_url.encode()).hexdigest()[:32]
    for ext in IMAGE_TYPES.values():
        if (_home() / f"{name}{ext}").is_file():
            return f"/v1/vista-previa/img/{name}{ext}"
    try:
        resp = get(image_url)
        kind = str(resp.headers.get("content-type", "")).split(";")[0].strip().lower()
        data = resp.content
    except Exception:  # noqa: BLE001
        return ""
    ext = IMAGE_TYPES.get(kind)
    if not ext or not data or len(data) > MAX_IMAGE:
        return ""
    (_home() / f"{name}{ext}").write_bytes(data)
    return f"/v1/vista-previa/img/{name}{ext}"


def image_file(name: str) -> Optional[Path]:
    """A saved preview picture by its name (32 hex characters and its extension)."""
    if not re.fullmatch(r"[0-9a-f]{32}\.(?:jpg|png|webp|gif)", name or ""):
        return None
    path = _home() / name
    return path if path.is_file() else None


def preview(
    url: str,
    *,
    get: Optional[Callable[..., Any]] = None,
    is_public: Optional[Callable[[str], bool]] = None,
    now: Optional[float] = None,
) -> Dict[str, str]:
    """The preview of *url* (cached a day). Raises ValueError for a link that
    is not a public web page."""
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError("no es un enlace web")
    if is_public is None:
        from openjarvis.mcp.favicon import public as is_public
    if not is_public(parsed.hostname.lower()):
        raise ValueError("solo sitios públicos")
    now = now or time.time()
    cache = _home() / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")
    try:
        data = json.loads(cache.read_text("utf-8"))
        if now - float(data.get("_at", 0)) < DAY:
            data.pop("_at", None)
            return data
    except (OSError, ValueError):
        pass
    if get is None:
        import httpx

        def get(u: str, **kw: Any) -> Any:
            return httpx.get(u, timeout=8, follow_redirects=True, headers=UA, **kw)

    resp = get(url)
    final = str(getattr(resp, "url", "") or url)
    if final != url:  # a redirect must stay on the public internet too
        host = urlparse(final).hostname or ""
        if not is_public(host.lower()):
            raise ValueError("solo sitios públicos")
    kind = str(getattr(resp, "headers", {}).get("content-type", "text/html")).lower()
    page = resp.text[:MAX_BYTES] if "html" in kind else ""
    data = parse(page, final) if page else {"url": url, "title": "", "description": "", "image": "",
                                            "site": parsed.hostname, "host": parsed.hostname}  # fmt: skip
    data["picture"] = keep_image(data["image"], get, is_public) if data.get("image") else ""
    try:
        cache.write_text(json.dumps({**data, "_at": now}, ensure_ascii=False), "utf-8")
    except OSError:
        pass
    return data


__all__ = ["image_file", "keep_image", "parse", "preview"]

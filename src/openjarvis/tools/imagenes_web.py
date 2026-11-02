"""Pictures from the internet, shown in the chat with their credit.

The owner (2 Nov 2026): «que Sergio te pueda dar imágenes de internet».
Free-licence sources first, each with author and licence:

* Openverse (WordPress; millions of CC and public-domain images, no key);
* Wikimedia Commons (no key);
* Pexels and Pixabay with the owner's keys (``PEXELS_API_KEY``,
  ``PIXABAY_API_KEY``), free to use.

The chosen pictures are downloaded, checked to really be images, made at
most 1600 px wide without their metadata, and saved where the chat can show
them (``studio.media_name``). Nothing is presented as the owner's, and the
credit line always goes with it.
"""

from __future__ import annotations

import io
import os
from typing import Any, Callable, Dict, List, Optional

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

UA = {"User-Agent": "Sergio/1.0 (personal assistant; image search for its owner)"}
MAX_BYTES = 12 * 1024 * 1024


def _get(url: str, **kw: Any) -> Any:
    import httpx

    kw.setdefault("timeout", 15)
    kw.setdefault("headers", UA)
    kw.setdefault("follow_redirects", True)
    return httpx.get(url, **kw)


def openverse(q: str, n: int, get: Callable[..., Any] = _get) -> List[Dict[str, str]]:
    data = get(
        "https://api.openverse.org/v1/images/",
        params={"q": q, "page_size": n * 2, "mature": "false"},
    ).json()
    out = []
    for r in data.get("results") or []:
        if r.get("url"):
            lic = f"CC {str(r.get('license') or '').upper()} {r.get('license_version') or ''}".strip()
            if str(r.get("license")) in ("cc0", "pdm"):
                lic = "Dominio público" if r.get("license") == "pdm" else "CC0"
            out.append(
                {
                    "url": r["url"],
                    "titulo": str(r.get("title") or q)[:100],
                    "autor": str(r.get("creator") or "")[:80],
                    "licencia": lic,
                    "fuente": str(r.get("foreign_landing_url") or r["url"]),
                    "sitio": "Openverse",
                }
            )
    return out[:n]


def commons(q: str, n: int, get: Callable[..., Any] = _get) -> List[Dict[str, str]]:
    data = get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {q}",
            "gsrnamespace": 6,
            "gsrlimit": n * 2,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 1600,
        },
    ).json()
    out = []
    for page in (data.get("query") or {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        artist = str((meta.get("Artist") or {}).get("value") or "")
        import re

        out.append(
            {
                "url": url,
                "titulo": str(page.get("title", "")).replace("File:", "")[:100],
                "autor": re.sub(r"<[^>]+>", "", artist)[:80],
                "licencia": str(
                    (meta.get("LicenseShortName") or {}).get("value")
                    or "Wikimedia Commons"
                ),
                "fuente": str(info.get("descriptionurl") or url),
                "sitio": "Wikimedia Commons",
            }
        )
    return out[:n]


def pexels(q: str, n: int, get: Callable[..., Any] = _get) -> List[Dict[str, str]]:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    data = get(
        "https://api.pexels.com/v1/search",
        params={"query": q, "per_page": n},
        headers={**UA, "Authorization": key},
    ).json()
    return [
        {
            "url": p["src"]["large2x"],
            "titulo": str(p.get("alt") or q)[:100],
            "autor": str(p.get("photographer") or ""),
            "licencia": "Licencia de Pexels (uso libre)",
            "fuente": str(p.get("url") or ""),
            "sitio": "Pexels",
        }
        for p in data.get("photos") or []
        if (p.get("src") or {}).get("large2x")
    ][:n]


def pixabay(q: str, n: int, get: Callable[..., Any] = _get) -> List[Dict[str, str]]:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    data = get(
        "https://pixabay.com/api/",
        params={"key": key, "q": q, "per_page": max(3, n), "safesearch": "true"},
    ).json()
    return [
        {
            "url": h["largeImageURL"],
            "titulo": str(h.get("tags") or q)[:100],
            "autor": str(h.get("user") or ""),
            "licencia": "Licencia de Pixabay (uso libre)",
            "fuente": str(h.get("pageURL") or ""),
            "sitio": "Pixabay",
        }
        for h in data.get("hits") or []
        if h.get("largeImageURL")
    ][:n]


SOURCES = (
    ("pexels", pexels),
    ("openverse", openverse),
    ("commons", commons),
    ("pixabay", pixabay),
)


def save(url: str, folder: Any, get: Callable[..., Any] = _get) -> Optional[str]:
    """The picture, checked and cleaned, saved for the chat; its file name."""
    from PIL import Image

    from openjarvis.creator import studio

    r = get(url)
    data = r.content if hasattr(r, "content") else b""
    if not data or len(data) > MAX_BYTES:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:  # noqa: BLE001 — not a picture
        return None
    img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    name = studio.media_name("imagen-web", ".jpg")
    folder.mkdir(parents=True, exist_ok=True)
    img.save(folder / name, quality=90)  # no EXIF: it is not copied
    return name


def buscar(
    q: str, n: int = 4, *, get: Callable[..., Any] = _get, folder: Any = None
) -> Dict[str, Any]:
    q = " ".join(str(q or "").split())[:120]
    if not q:
        return {"imagenes": [], "aviso": "Dígame qué imagen busca."}
    n = max(1, min(int(n), 8))
    found: List[Dict[str, str]] = []
    problems = []
    for name, fn in SOURCES:
        if len(found) >= n * 2:
            break
        try:
            found += fn(q, n, get)
        except Exception as exc:  # noqa: BLE001 — the next source
            problems.append(f"{name}: {str(exc)[:80]}")
    if folder is None:
        from openjarvis.creator import studio

        folder = studio.projects_root() / "imagenes"
    shown = []
    seen = set()
    for item in found:
        if len(shown) >= n or item["url"] in seen:
            continue
        seen.add(item["url"])
        try:
            fname = save(item["url"], folder, get)
        except Exception:  # noqa: BLE001
            fname = None
        if fname:
            shown.append(
                {**item, "archivo": fname, "ver": f"/v1/creator/media/{fname}"}
            )
    out: Dict[str, Any] = {"consulta": q, "imagenes": shown}
    if not shown:
        out["aviso"] = "No encontré imágenes ahora" + (
            f" ({'; '.join(problems)[:200]})" if problems else "."
        )
    return out


def texto(res: Dict[str, Any]) -> str:
    if not res.get("imagenes"):
        return res.get("aviso") or "No encontré imágenes."
    lines = []
    for im in res["imagenes"]:
        credit = f"{im['autor']} · " if im.get("autor") else ""
        lines.append(
            f"![{im['titulo']}]({im['ver']})\n{credit}{im['licencia']} · {im['sitio']} · {im['fuente']}"
        )
    return "\n\n".join(lines)


@ToolRegistry.register("imagenes_web")
class WebImagesTool(BaseTool):
    tool_id = "imagenes_web"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="imagenes_web",
            description=(
                "Find real pictures on the internet (Pexels, Openverse, Wikimedia Commons, Pixabay; free "
                "licences) and show them in the chat with author, licence and source. Use it when the owner "
                "asks to see or get an image or photo of something that exists ('muéstrame una foto de…'). "
                "Leave the returned markdown as is. To CREATE a new picture use the image tools instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "que": {
                        "type": "string",
                        "description": "what to look for (English works best)",
                    },
                    "cuantas": {"type": "integer", "description": "1-8, default 4"},
                },
                "required": ["que"],
            },
            category="media",
            timeout_seconds=90,
        )

    def execute(self, **p: Any) -> ToolResult:
        try:
            res = buscar(str(p.get("que") or ""), int(p.get("cuantas") or 4))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                tool_name=self.tool_id,
                content=f"No pude buscar imágenes: {str(exc)[:200]}",
                success=False,
            )
        return ToolResult(
            tool_name=self.tool_id,
            content=texto(res),
            success=bool(res.get("imagenes")),
        )


__all__ = [
    "WebImagesTool",
    "buscar",
    "commons",
    "openverse",
    "pexels",
    "pixabay",
    "save",
    "texto",
]

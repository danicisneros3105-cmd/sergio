"""Find the YouTube video the user describes ("un video de MrBeast en el que
salga con traje negro") and say which one to play.

1. The request becomes a short search (filler words out): "mrbeast traje negro".
2. YouTube's own results page is read (no API key): id, title, channel, length.
3. When the request describes what must be *seen* (a black suit, a red car),
   Gemini looks at the thumbnails of the first results (one contact sheet,
   numbered) and the titles, and picks the one that fits best.

The companion then opens the results and clicks that video with the cursor,
so the user watches Sergio do it.
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
from typing import Any, Callable
from urllib.parse import quote_plus

FILLER = {
    "pon", "ponme", "ponlo", "reproduce", "reproduceme", "busca", "buscame", "abre",
    "quiero", "ver", "mira", "un", "una", "el", "la", "los", "las", "video", "videos",
    "de", "del", "en", "que", "donde", "salga", "sale", "aparezca", "aparece", "este",
    "esta", "youtube", "por", "favor", "porfa", "sergio", "me", "algun", "alguno",
    "sobre", "y", "lo", "le", "a", "al", "cual", "cuyo", "con",
}  # fmt: skip
# Words that describe what is SEEN (worth checking the thumbnails).
VISUAL = re.compile(
    r"\b(traje|ropa|vestid|camis|color|negro|blanco|rojo|azul|verde|amarill|"
    r"rosad|dorad|gafas|lentes|sombrero|gorra|con un|con una|sale|salga|aparece|"
    r"aparezca|lleva|llevando|usa|usando|fondo|coche|carro|auto|perro|gato)\w*"
)
SEARCH_URL = "https://www.youtube.com/results?search_query={}"
WATCH_URL = "https://www.youtube.com/watch?v={}"
THUMB_URL = "https://i.ytimg.com/vi/{}/hqdefault.jpg"


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def search_query(request: str) -> str:
    """'pon un video de MrBeast en el que salga con traje negro' ->
    'mrbeast traje negro'."""
    words = [w for w in _plain(request).split() if w not in FILLER]
    return " ".join(words) or _plain(request)


def wants_looks(request: str) -> bool:
    return bool(VISUAL.search(_plain(request)))


def _walk(node: Any):
    if isinstance(node, dict):
        if "videoRenderer" in node and isinstance(node["videoRenderer"], dict):
            yield node["videoRenderer"]
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _text(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node:
        return str(node["simpleText"])
    return "".join(
        str(r.get("text", "")) for r in node.get("runs", []) if isinstance(r, dict)
    )


def parse_results(html: str, limit: int = 8) -> list[dict[str, str]]:
    """Videos on a YouTube results page (from its ytInitialData)."""
    m = re.search(r"ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return []
    out, seen = [], set()
    for video in _walk(data):
        vid = str(video.get("videoId") or "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        out.append(
            {
                "id": vid,
                "title": _text(video.get("title")),
                "channel": _text(video.get("ownerText")),
                "length": _text(video.get("lengthText")),
            }
        )
        if len(out) >= limit:
            break
    return out


def contact_sheet(images: list[bytes], columns: int = 3) -> bytes:
    """Thumbnails in a grid, each with its big number (for Gemini to pick)."""
    from PIL import Image, ImageDraw

    tiles = []
    for data in images:
        try:
            tiles.append(Image.open(io.BytesIO(data)).convert("RGB").resize((320, 180)))
        except Exception:  # noqa: BLE001 — a broken thumbnail: a grey tile
            tiles.append(Image.new("RGB", (320, 180), (60, 60, 60)))
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 320, rows * 180), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    for i, tile in enumerate(tiles):
        x, y = (i % columns) * 320, (i // columns) * 180
        sheet.paste(tile, (x, y))
        draw.rectangle([x, y, x + 44, y + 40], fill=(0, 0, 0))
        draw.text((x + 12, y + 8), str(i + 1), fill=(255, 255, 0))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=85)
    return buf.getvalue()


PICK_PROMPT = """Son miniaturas numeradas de resultados de YouTube. El usuario \
pidió: «{request}». Títulos:
{titles}
Elige el número del video que mejor cumple lo pedido, mirando las miniaturas \
(lo que se ve) y los títulos. Responde SOLO JSON: {{"n": número, "por_que": \
"en pocas palabras"}}"""


def pick(
    request: str,
    get: Callable[[str], Any],
    ask_image: Callable[[bytes, str], str] | None = None,
) -> dict[str, Any]:
    """The video to play: {id, title, channel, url, search_url, why}."""
    query = search_query(request)
    search_url = SEARCH_URL.format(quote_plus(query))
    resp = get(search_url)
    videos = parse_results(getattr(resp, "text", "") or "")
    if not videos:
        raise RuntimeError("YouTube no devolvió resultados para esa búsqueda.")
    chosen, why = videos[0], "el primer resultado"
    if ask_image is not None and wants_looks(request) and len(videos) > 1:
        shown = videos[:6]
        thumbs = []
        for v in shown:
            try:
                thumbs.append(get(THUMB_URL.format(v["id"])).content)
            except Exception:  # noqa: BLE001
                thumbs.append(b"")
        titles = "\n".join(
            f"{i + 1}. {v['title']} ({v['channel']})" for i, v in enumerate(shown)
        )
        try:
            reply = ask_image(
                contact_sheet(thumbs),
                PICK_PROMPT.format(request=request, titles=titles),
            )
            m = re.search(r"\{.*\}", reply, re.S)
            data = json.loads(m.group(0)) if m else {}
            n = int(data.get("n") or 0)
            if 1 <= n <= len(shown):
                chosen, why = shown[n - 1], str(data.get("por_que") or "")[:120]
        except Exception:  # noqa: BLE001 — Gemini unavailable: the top result
            pass
    return {
        **chosen,
        "url": WATCH_URL.format(chosen["id"]),
        "search_url": search_url,
        "query": query,
        "why": why,
    }


__all__ = ["contact_sheet", "parse_results", "pick", "search_query", "wants_looks"]

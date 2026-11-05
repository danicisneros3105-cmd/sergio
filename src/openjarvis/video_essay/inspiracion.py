"""Three videos to take as inspiration, found for each brief.

The owner (3 Nov 2026): «que Sergio entre a Instagram, TikTok o YouTube para
inspirarse y le dé al usuario 3 videos de inspiración basados en el prompt…
el usuario escogerá uno como estilo e inspiración».

Where Sergio looks, and how (only official or public ways; Sergio never
disguises itself nor slips past a site's limits):

* **YouTube** (videos and Shorts): the Data API with the owner's connected
  channel or ``YOUTUBE_API_KEY`` (views, date, likes); without them, a search
  with yt-dlp (views and length).
* **Instagram**: the owner's professional account already connected for
  publishing (``automatiza/canales``): the hashtag's top posts through the
  Graph API (needs Meta's «Instagram Public Content Access»; 30 hashtags a week).
* **TikTok**: TikTok has no public search API. Sergio reads the public
  Creative Center (trending hashtags) with its own browser in the background,
  as a signal; videos come from the other two.

The three are chosen by **momentum** (views per day since published, when the
date is known), **fit** with the brief (shared words), and **variety** (one per
creator, different platforms when there are). Nothing is invented: every
number shown comes from the platform. The choice becomes the job's reference
(``video_essay`` with ``reference``), which the school studies shot by shot.
"""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import subprocess
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

UA = {"User-Agent": "Sergio/1.0 (inspiration for its owner's videos)"}
YT = "https://www.googleapis.com/youtube/v3"
IG = "https://graph.facebook.com/v21.0"
IG_FIELDS = "id,caption,media_type,permalink,like_count,comments_count,timestamp,thumbnail_url,media_url"
CREATIVE_CENTER = (
    "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/es"
)
_SMALL = set(
    "de la el los las un una y o en para por con del al que como mi tu su sus mis "
    "video videos haz hazme quiero sobre".split()
)


def home() -> Path:
    from openjarvis.core.config import get_config_dir

    path = Path(get_config_dir()) / "inspiracion"
    path.mkdir(parents=True, exist_ok=True)
    return path


def plain(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def words(text: str) -> set:
    return {
        w
        for w in re.findall(r"[a-z0-9]+", plain(text))
        if len(w) > 2 and w not in _SMALL
    }


def queries(prompt: str, ask: Optional[Callable[..., str]] = None) -> List[str]:
    """What to search: the brief itself and, when a model is at hand, two
    shorter searches the way creators title such videos (Spanish and English)."""
    keep = words(prompt)  # in the order they were written (a set has none)
    ordered = [
        w for w in dict.fromkeys(re.findall(r"[a-z0-9]+", plain(prompt))) if w in keep
    ]
    base = " ".join(ordered[:8]) or prompt[:80]
    out = [base]
    if ask is not None:
        try:
            raw = ask(
                "Give 3 short YouTube/TikTok search queries (2-5 words each) that would find popular "
                f"short videos for this video idea, one in Spanish and two in English. Idea: {prompt[:300]}\n"
                'Answer ONLY JSON: {"q": ["...", "...", "..."]}',
                json_mode=True,
                max_tokens=200,
            )
            out += [
                str(q)[:80] for q in json.loads(raw).get("q", []) if str(q).strip()
            ][:3]
        except Exception:  # noqa: BLE001 — the brief alone still works
            pass
    return list(dict.fromkeys(out))


# -- YouTube ------------------------------------------------------------------------------


def _yt_auth() -> Dict[str, Any]:
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if key:
        return {"params": {"key": key}}
    try:
        from openjarvis.automatiza import canales

        acc = canales.account("youtube")
        if acc.get("refresh_token"):
            return {
                "headers": {
                    **UA,
                    "Authorization": f"Bearer {canales._yt_token(acc, canales._http(), None)}",
                }
            }
    except Exception:  # noqa: BLE001
        pass
    return {}


def _since(days: int) -> str:
    return datetime.fromtimestamp(time.time() - days * 86400, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def youtube_api(
    q: str, vertical: bool, get: Callable[..., Any], auth: Dict[str, Any], n: int = 15,
    *, days: int = 120,
) -> List[Dict[str, Any]]:
    params = {**auth.get("params", {}), "part": "snippet", "q": q + (" #shorts" if vertical else ""), "type": "video",
              "order": "viewCount", "maxResults": n, "videoDuration": "short" if vertical else "medium",
              "publishedAfter": _since(days)}  # fmt: skip
    found = get(f"{YT}/search", params=params, headers=auth.get("headers", UA)).json()
    ids = [
        i["id"]["videoId"]
        for i in found.get("items", [])
        if i.get("id", {}).get("videoId")
    ]
    if not ids:
        return []
    stats = get(f"{YT}/videos", params={**auth.get("params", {}), "part": "snippet,statistics,contentDetails",
                                         "id": ",".join(ids)}, headers=auth.get("headers", UA)).json()  # fmt: skip
    out = []
    for v in stats.get("items", []):
        sn, st = v.get("snippet") or {}, v.get("statistics") or {}
        dur = _iso_seconds((v.get("contentDetails") or {}).get("duration", ""))
        where = "shorts/" if vertical and dur <= 180 else "watch?v="
        out.append({
            "plataforma": "YouTube", "url": f"https://www.youtube.com/{where}{v['id']}",
            "titulo": sn.get("title", "")[:160], "canal": sn.get("channelTitle", "")[:80],
            "vistas": int(st.get("viewCount") or 0), "me_gusta": int(st.get("likeCount") or 0),
            "publicado": sn.get("publishedAt", ""), "segundos": dur,
            "miniatura": ((sn.get("thumbnails") or {}).get("high") or {}).get("url", ""),
        })  # fmt: skip
    return out


def _iso_seconds(iso: str) -> float:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0.0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return float(d * 86400 + h * 3600 + mi * 60 + s)


def youtube_ytdlp(
    q: str,
    vertical: bool,
    runner: Optional[Callable[[List[str]], str]] = None,
    n: int = 20,
) -> List[Dict[str, Any]]:
    from openjarvis.video_essay import sources

    cmd = sources.ytdlp()
    if not (cmd or runner):
        return []
    args = cmd + [
        "--dump-json",
        "--flat-playlist",
        "--no-warnings",
        f"ytsearch{n}:{q[:80]}{' #shorts' if vertical else ''}",
    ]
    try:
        text = (
            runner(args)
            if runner
            else subprocess.run(args, capture_output=True, text=True, timeout=90).stdout
        )
    except Exception:  # noqa: BLE001
        return []
    out = []
    for line in text.splitlines():
        try:
            v = json.loads(line)
        except ValueError:
            continue
        vid, dur = v.get("id"), float(v.get("duration") or 0)
        if not vid or (vertical and dur and dur > 180):
            continue
        thumbs = v.get("thumbnails") or []
        out.append({
            "plataforma": "YouTube", "url": v.get("url") or f"https://www.youtube.com/watch?v={vid}",
            "titulo": str(v.get("title") or "")[:160], "canal": str(v.get("channel") or v.get("uploader") or "")[:80],
            "vistas": int(v.get("view_count") or 0), "me_gusta": 0, "publicado": "", "segundos": dur,
            "miniatura": (thumbs[-1].get("url") if thumbs else "") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        })  # fmt: skip
    return out


# -- Instagram (his professional account) ---------------------------------------------------


def instagram(tag: str, get: Callable[..., Any], *, recent: bool = False) -> List[Dict[str, Any]]:
    try:
        from openjarvis.automatiza import canales

        acc = canales.account("instagram")
    except Exception:  # noqa: BLE001
        return []
    uid, token = acc.get("user_id"), acc.get("token")
    if not (uid and token and tag):
        return []
    found = get(
        f"{IG}/ig_hashtag_search",
        params={"user_id": uid, "q": tag, "access_token": token},
    ).json()
    hid = ((found.get("data") or [{}])[0]).get("id")
    if not hid:
        return []
    feed = "recent_media" if recent else "top_media"
    media = get(f"{IG}/{hid}/{feed}", params={
        "user_id": uid, "access_token": token, "limit": 25,
        "fields": IG_FIELDS}).json()  # fmt: skip
    out = []
    for m in media.get("data", []):
        if m.get("media_type") != "VIDEO":
            continue
        out.append({
            "plataforma": "Instagram", "url": m.get("permalink", ""), "titulo": str(m.get("caption") or "")[:160],
            "canal": "", "vistas": 0, "me_gusta": int(m.get("like_count") or 0), "publicado": m.get("timestamp", ""),
            "segundos": 0.0, "miniatura": m.get("thumbnail_url") or "",
        })  # fmt: skip
    return out


def tiktok_hashtags(
    check: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> List[str]:
    """Trending TikTok hashtags from the public Creative Center (a signal)."""
    try:
        if check is None:
            from openjarvis.asistente import navegador

            def check(url: str) -> Dict[str, Any]:
                return navegador.check(url)

        page = check(CREATIVE_CENTER)
    except Exception:  # noqa: BLE001 — no browser or the page did not load
        return []
    return list(
        dict.fromkeys(re.findall(r"#\s?([A-Za-z0-9_]{3,40})", page.get("texto", "")))
    )[:20]


# -- choosing three ------------------------------------------------------------------------


def _days(published: str) -> float:
    try:
        when = datetime.fromisoformat(published.replace("Z", "+00:00"))
        return max(1.0, (datetime.now(timezone.utc) - when).total_seconds() / 86400)
    except (ValueError, AttributeError):
        return 0.0


def score(v: Dict[str, Any], want: set) -> float:
    fit = len(want & words(v.get("titulo", ""))) / max(1, min(len(want), 4))
    pop = v.get("vistas") or v.get("me_gusta", 0) * 30
    days = _days(v.get("publicado", ""))
    momentum = pop / days if days else pop / 60  # unknown date: as if two months old
    return round(1.5 * fit + math.log10(1 + momentum), 3)


def pick_three(cands: List[Dict[str, Any]], prompt: str) -> List[Dict[str, Any]]:
    want = words(prompt)
    ranked = sorted(cands, key=lambda v: -score(v, want))
    out: List[Dict[str, Any]] = []
    seen_creators, platforms = set(), set()
    for v in ranked:  # first pass: variety of creators and platforms
        who = plain(v.get("canal") or v.get("url"))
        if who in seen_creators or any(o["url"] == v["url"] for o in out):
            continue
        if (
            len(out) == 2
            and len(platforms) == 1
            and v["plataforma"] in platforms
            and any(c["plataforma"] not in platforms for c in ranked)
        ):
            continue  # keep one place for another platform if there is one
        out.append(v)
        seen_creators.add(who)
        platforms.add(v["plataforma"])
        if len(out) == 3:
            break
    for v in ranked:  # not enough variety: fill with the best left
        if len(out) == 3:
            break
        if all(o["url"] != v["url"] for o in out):
            out.append(v)
    return out


def why(v: Dict[str, Any], want: set) -> str:
    bits = []
    if v.get("vistas"):
        days = _days(v.get("publicado", ""))
        bits.append(
            f"{_human(v['vistas'])} vistas" + (f" en {int(days)} días" if days else "")
        )
    elif v.get("me_gusta"):
        bits.append(f"{_human(v['me_gusta'])} me gusta")
    shared = want & words(v.get("titulo", ""))
    if shared:
        bits.append("mismo tema (" + ", ".join(sorted(shared)[:3]) + ")")
    if v.get("segundos"):
        bits.append(f"{int(v['segundos'])} s")
    return "; ".join(bits)


def _human(n: int) -> str:
    return (
        f"{n / 1e6:.1f} M" if n >= 1e6 else f"{n / 1e3:.0f} k" if n >= 1e3 else str(n)
    )


def _thumb(url: str, dest: Path, get: Callable[..., Any]) -> bool:
    if not url.startswith("https://"):
        return False
    try:
        r = get(url, headers=UA)
        data = r.content
        if len(data) < 1000:
            return False
        dest.write_bytes(data)
        return True
    except Exception:  # noqa: BLE001
        return False


def search(prompt: str, *, vertical: bool = True, ask: Optional[Callable[..., str]] = None,
           get: Optional[Callable[..., Any]] = None, runner: Optional[Callable[[List[str]], str]] = None,
           tiktok: Optional[Callable[[str], Dict[str, Any]]] = None) -> Dict[str, Any]:  # fmt: skip
    """Three videos for *prompt*, saved under a random id for the chat card."""
    if get is None:
        import httpx

        def get(url: str, **kw: Any) -> Any:
            return httpx.get(url, timeout=25, follow_redirects=True, **kw)

    qs = queries(prompt, ask)
    cands: List[Dict[str, Any]] = []
    notes: List[str] = []
    auth = _yt_auth()
    for q in qs[:3]:
        try:
            cands += (
                youtube_api(q, vertical, get, auth)
                if auth
                else youtube_ytdlp(q, vertical, runner)
            )
        except Exception as exc:  # noqa: BLE001
            notes.append(f"YouTube: {str(exc)[:80]}")
    # a hashtag the way people write them: the English search, words joined
    tag = "".join(
        re.findall(r"[a-z0-9]+", plain(qs[-1] if len(qs) > 1 else qs[0]))[:3]
    )[:40]
    try:
        ig = instagram(tag, get)
        cands += ig
        if not ig:
            notes.append(
                "Instagram: conecte su cuenta profesional en Automatizar para buscar ahí"
            )
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Instagram: {str(exc)[:80]}")
    trends = tiktok_hashtags(tiktok)
    if not cands:
        return {
            "id": "",
            "opciones": [],
            "notas": notes or ["No encontré videos para ese tema."],
            "tiktok": trends,
        }
    three = pick_three(cands, prompt)
    rid = secrets.token_hex(12)
    folder = home() / rid
    folder.mkdir(parents=True, exist_ok=True)
    want = words(prompt)
    for i, v in enumerate(three):
        v["por_que"] = why(v, want)
        v["mini"] = (
            f"/v1/creator/inspiracion/{rid}/miniatura/{i}.jpg"
            if _thumb(v.get("miniatura", ""), folder / f"{i}.jpg", get)
            else ""
        )
    data = {"id": rid, "encargo": prompt, "vertical": vertical, "opciones": three, "notas": notes,
            "tiktok": trends, "elegida": None, "cuando": time.time()}  # fmt: skip
    (folder / "datos.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), "utf-8"
    )
    return data


def load(rid: str) -> Dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{24}", rid or ""):
        raise KeyError(rid)
    return json.loads((home() / rid / "datos.json").read_text("utf-8"))


def choose(rid: str, index: int) -> Dict[str, Any]:
    """The option the person chose: saved, and the message that asks Sergio to
    make the video with it as reference (or to plan it first)."""
    data = load(rid)
    if not 0 <= index < len(data["opciones"]):
        raise IndexError(index)
    data["elegida"] = index
    (home() / rid / "datos.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), "utf-8"
    )
    v = data["opciones"][index]
    data["mensaje"] = (
        f"Usa como estilo e inspiración «{v['titulo'][:80]}» ({v['url']}) para este video: {data['encargo']}. "
        "Primero planéalo conmigo: guion y animación de cómo debe quedar."
    )
    return data


def card(data: Dict[str, Any]) -> str:
    """What the tool answers: a short list and the mark the chat draws as a card."""
    if not data.get("opciones"):
        return "No encontré videos de inspiración. " + " ".join(data.get("notas", []))
    rows = [
        f"{i + 1}. {v['plataforma']}: «{v['titulo'][:70]}» — {v.get('por_que', '')}"
        for i, v in enumerate(data["opciones"])
    ]
    extra = (
        f"\nEn TikTok suben ahora: {', '.join('#' + t for t in data['tiktok'][:6])}."
        if data.get("tiktok")
        else ""
    )
    return "\n".join(rows) + extra + f"\n\n[[inspiracion:{data['id']}]]"


__all__ = [
    "card",
    "choose",
    "load",
    "pick_three",
    "queries",
    "score",
    "search",
    "tiktok_hashtags",
    "youtube_ytdlp",
]

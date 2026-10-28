"""What people are watching and searching now, and which videos to make of it.

The owner (28 Oct 2026): «mejora el análisis de mercado y de tendencias para
hacer videos». Sergio reads public signals (no account needed), puts them
side by side and asks a model for video ideas **only from those signals**:

* Google Trends, searches rising today in a country (its public RSS, with
  the approximate number of searches);
* Wikipedia, the most-read articles yesterday in a language (views);
* Reddit, the top posts of the day (votes);
* YouTube, the most popular videos in a country, when the owner connected
  his channel or set ``YOUTUBE_API_KEY`` (views, and what the top videos in
  the niche are called: the competition).

Each idea says which signal it comes from; an idea whose signal is not in
the list is dropped (nothing invented). A topic seen in two or more sources
counts more. Nothing is published: ideas are suggestions, and «Hacer este
video» only queues the video like the «+ → Video» button.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

UA = {"User-Agent": "Sergio/1.0 (trend reading for its owner's videos)"}
CACHE_SECONDS = 3 * 3600
LANG_OF = {"EC": "es", "MX": "es", "ES": "es", "CO": "es", "AR": "es", "PE": "es", "CL": "es",
           "US": "en", "GB": "en", "BR": "pt", "PT": "pt", "FR": "fr", "IT": "it", "DE": "de"}  # fmt: skip


def _get(url: str, **kw: Any) -> Any:
    import httpx

    r = httpx.get(url, headers=UA, timeout=25, follow_redirects=True, **kw)
    r.raise_for_status()
    return r


def plain(text: str) -> str:
    text = (
        unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    )
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text).split())


def _number(text: str) -> int:
    """«200K+» → 200000, «1M+» → 1000000, «5,000+» → 5000."""
    m = re.search(r"([\d.,]+)\s*([KkMm]?)", text or "")
    if not m:
        return 0
    value = float(
        m.group(1).replace(",", "").replace(".", "")
        if m.group(2) == ""
        else m.group(1).replace(",", ".")
    )
    return int(value * {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1))


# -- the sources (each returns signals, never raises) ----------------------------------------


def google_trends(country: str, get: Callable[..., Any] = _get) -> List[Dict[str, Any]]:
    try:
        from openjarvis.security.safe_xml import fromstring

        root = fromstring(
            get("https://trends.google.com/trending/rss", params={"geo": country}).text
        )
    except Exception:  # noqa: BLE001
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        traffic = ""
        news = []
        for child in item:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "approx_traffic":
                traffic = child.text or ""
            elif tag == "news_item":
                headline = next(
                    (
                        c.text
                        for c in child
                        if c.tag.rsplit("}", 1)[-1] == "news_item_title"
                    ),
                    "",
                )
                if headline:
                    news.append(headline.strip())
        out.append({"tema": title, "fuente": "Google Trends", "cifra": _number(traffic),
                    "unidad": "búsquedas", "detalle": "; ".join(news[:2])})  # fmt: skip
    return out


def wikipedia(
    lang: str, get: Callable[..., Any] = _get, day: Optional[date] = None
) -> List[Dict[str, Any]]:
    day = day or date.today() - timedelta(days=1)
    url = f"https://api.wikimedia.org/feed/v1/wikipedia/{lang}/featured/{day:%Y/%m/%d}"
    try:
        data = get(url).json()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for a in (data.get("mostread") or {}).get("articles", [])[:40]:
        title = (a.get("titles") or {}).get("normalized") or a.get("title") or ""
        if not title or ":" in title or title in ("Main Page", "Wikipedia"):
            continue
        out.append({"tema": title, "fuente": "Wikipedia", "cifra": int(a.get("views") or 0),
                    "unidad": "lecturas", "detalle": str(a.get("description") or "")[:120]})  # fmt: skip
    return out


def reddit(get: Callable[..., Any] = _get) -> List[Dict[str, Any]]:
    try:
        data = get(
            "https://www.reddit.com/r/popular/top.json",
            params={"t": "day", "limit": 50},
        ).json()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for child in (data.get("data") or {}).get("children", []):
        post = child.get("data") or {}
        if post.get("over_18") or not post.get("title"):
            continue
        out.append({"tema": post["title"][:140], "fuente": "Reddit", "cifra": int(post.get("ups") or 0),
                    "unidad": "votos", "detalle": f"r/{post.get('subreddit', '')}"})  # fmt: skip
    return out


def youtube(country: str, niche: str = "", get: Callable[..., Any] = _get,
            token: str = "", key: str = "") -> List[Dict[str, Any]]:  # fmt: skip
    """Most popular videos in the country, and the top of the niche (the
    competition), with the owner's connection or an API key."""
    import os

    key = key or os.environ.get("YOUTUBE_API_KEY", "")
    if not (token or key):
        try:
            from openjarvis.automatiza import canales

            acc = canales.account("youtube")
            if acc.get("refresh_token"):
                token = canales._yt_token(acc, canales._http(), None)
        except Exception:  # noqa: BLE001 — no connection: the other sources
            return []
    if not (token or key):
        return []
    auth = {"headers": {**UA, "Authorization": f"Bearer {token}"}} if token else {}
    base = {"key": key} if key and not token else {}
    out: List[Dict[str, Any]] = []
    try:
        data = get("https://www.googleapis.com/youtube/v3/videos", params={
            **base, "part": "snippet,statistics", "chart": "mostPopular",
            "regionCode": country, "maxResults": 30}, **auth).json()  # fmt: skip
        for v in data.get("items", []):
            out.append({"tema": v["snippet"]["title"][:140], "fuente": "YouTube",
                        "cifra": int((v.get("statistics") or {}).get("viewCount") or 0), "unidad": "vistas",
                        "detalle": v["snippet"].get("channelTitle", "")})  # fmt: skip
        if niche:
            found = get("https://www.googleapis.com/youtube/v3/search", params={
                **base, "part": "snippet", "q": niche, "type": "video", "order": "viewCount",
                "publishedAfter": f"{date.today() - timedelta(days=30)}T00:00:00Z",
                "regionCode": country, "maxResults": 10}, **auth).json()  # fmt: skip
            for v in found.get("items", []):
                out.append({"tema": v["snippet"]["title"][:140], "fuente": "YouTube (competencia)",
                            "cifra": 0, "unidad": "", "detalle": v["snippet"].get("channelTitle", "")})  # fmt: skip
    except Exception:  # noqa: BLE001
        return out
    return out


# -- putting them together ------------------------------------------------------------------


def _words(text: str) -> set:
    return {w for w in plain(text).split() if len(w) > 3}


def rank(signals: List[Dict[str, Any]], niche: str = "") -> List[Dict[str, Any]]:
    """Each signal's weight: its size within its own source (0–1), plus a
    bonus when other sources share its words (the same topic everywhere)
    and when it touches the owner's niche."""
    by_source: Dict[str, int] = {}
    for s in signals:
        by_source[s["fuente"]] = max(
            by_source.get(s["fuente"], 0), int(s.get("cifra") or 0)
        )
    want = _words(niche)
    for s in signals:
        top = by_source.get(s["fuente"]) or 0
        size = (s.get("cifra") or 0) / top if top else 0.3
        mine = _words(s["tema"] + " " + s.get("detalle", ""))
        echoes = {o["fuente"] for o in signals if o is not s and o["fuente"] != s["fuente"]
                  and len(mine & _words(o["tema"])) >= 1}  # fmt: skip
        s["fuentes"] = sorted({s["fuente"], *echoes})
        s["peso"] = round(
            size + 0.6 * len(echoes) + (0.8 if want and mine & want else 0.0), 3
        )
    return sorted(signals, key=lambda s: -s["peso"])


def _cache(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = Path(get_config_dir())
    return Path(home) / "tendencias.json"


def read(country: str = "EC", niche: str = "", *, get: Callable[..., Any] = _get,
         home: Optional[Path] = None, fresh: bool = False) -> Dict[str, Any]:  # fmt: skip
    """The signals of now (cached 3 h per country and niche)."""
    country = (country or "EC").upper()[:2]
    path = _cache(home)
    key = f"{country}|{plain(niche)}"
    try:
        cached = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        cached = {}
    entry = cached.get(key) or {}
    if not fresh and time.time() - float(entry.get("at") or 0) < CACHE_SECONDS:
        return entry
    lang = LANG_OF.get(country, "en")
    signals = (google_trends(country, get) + wikipedia(lang, get) + reddit(get)
               + youtube(country, niche, get))  # fmt: skip
    entry = {"at": time.time(), "pais": country, "nicho": niche,
             "fuentes": sorted({s["fuente"] for s in signals}), "senales": rank(signals, niche)[:80]}  # fmt: skip
    cached[key] = entry
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cached, ensure_ascii=False), "utf-8")
    except OSError:
        pass
    return entry


def _line(s: Dict[str, Any]) -> str:
    text = f"- [{s['fuente']}] {s['tema']}"
    if s.get("cifra"):
        text += f" — {s['cifra']:,} {s['unidad']}"
    if s.get("detalle"):
        text += f" ({s['detalle']})"
    if len(s.get("fuentes") or []) > 1:
        text += " ·varias fuentes"
    return text


IDEAS_PROMPT = """You plan videos for a creator (country {country}, niche: {niche}). Below are \
REAL signals of what people search, read and watch right now (source, size). Propose up to \
{n} videos that ride these signals. Rules: every idea is built on one signal from the list and \
quotes its exact topic in "signal"; never invent a trend, a number or a fact; prefer topics \
that appear in several sources and that fit the niche; skip tragedies, deaths, crimes against \
people and politics unless the niche is news (never mock them); a topic that will be old in two \
days only works as a Short. Formats: "short" (under 60 s) or "long" (3-12 min). Genres: \
{genres}. The "hook" is the first spoken line (under 15 words), the "title" under 60 \
characters, "why" one sentence that cites the source and its number.

SIGNALS:
{signals}

Answer ONLY JSON: {{"ideas": [{{"title": "...", "hook": "...", "signal": "exact topic", \
"genre": "...", "format": "short|long", "why": "..."}}]}}. Write title, hook and why in {language}."""


def ideas(country: str = "EC", niche: str = "", *, n: int = 6, ask: Optional[Callable[..., str]] = None,
          get: Callable[..., Any] = _get, home: Optional[Path] = None,
          language: str = "Spanish") -> Dict[str, Any]:  # fmt: skip
    """Video ideas from the signals of now; each one tied to a real signal."""
    from openjarvis.video_essay import genres

    data = read(country, niche, get=get, home=home)
    signals = data.get("senales") or []
    if not signals:
        return {
            **data,
            "ideas": [],
            "aviso": "No pude leer tendencias ahora (sin internet o las fuentes no respondieron).",
        }
    if ask is None:
        from openjarvis.creator import llm

        def ask(prompt: str, **kw: Any) -> str:
            return llm.ask(prompt, json_mode=True)

    lines = "\n".join(_line(s) for s in signals[:45])
    raw = ask(IDEAS_PROMPT.format(country=data.get("pais", country), niche=niche or "general", n=n,
                                  genres=", ".join(genres.GENRES), signals=lines, language=language))  # fmt: skip
    try:
        found = json.loads(re.search(r"\{.*\}", raw, re.S).group(0)).get("ideas") or []  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        found = []
    known = {plain(s["tema"]): s for s in signals}
    out = []
    for idea in found:
        if not isinstance(idea, dict):
            continue
        sig = plain(str(idea.get("signal") or ""))
        match = known.get(sig) or next(
            (s for k, s in known.items() if sig and (sig in k or k in sig)), None
        )
        if match is None:
            continue  # its signal is not in the list: invented
        genre = str(idea.get("genre") or "")
        out.append({
            "titulo": str(idea.get("title") or "")[:90], "gancho": str(idea.get("hook") or "")[:160],
            "genero": genre if genre in genres.GENRES else "",
            "formato": "long" if idea.get("format") == "long" else "short",
            "por_que": str(idea.get("why") or "")[:240], "senal": match,
        })  # fmt: skip
        if len(out) >= n:
            break
    return {**data, "ideas": out}


__all__ = ["google_trends", "ideas", "rank", "read", "reddit", "wikipedia", "youtube"]

"""Only one job: what is trending, how each platform says it ranks, and who watches.

The most thorough of the four. Everything runs at once (threads) and every
line of the answer comes from something read now:

1. **Trends** — :func:`automatiza.tendencias.read`: Google Trends, Wikipedia,
   Reddit and YouTube, ranked (a topic in several sources weighs more).
2. **What people type** — the public YouTube and Google autocomplete for the
   niche and the niche + each letter (what people really search, today).
3. **The competition** — the top videos of the niche (yt-dlp search, or the
   YouTube API when connected): views, length, and the patterns of their
   titles measured by code (length, numbers, questions, common words).
4. **The algorithm** — :data:`ALGORITMO`: only what YouTube, Instagram and
   TikTok have said in public about how they rank, with the source. Never
   secret weights or invented percentages.
5. **The audience** — read from the signals: the words people use, the
   questions they ask (autocomplete), and the formats that win in the
   niche. Real hours and ages need the owner's own analytics; without them
   it is said, not guessed.
6. **Deep reading** (``profundo``) — :mod:`research.deep` on the audience
   of the niche, each finding with its quote.

A model then joins all of it into opportunities; an opportunity whose
signal is not in the data is dropped. Nothing is published.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

UA = {"User-Agent": "Sergio/1.0 (trend research for its owner's videos)"}

# What each platform has said in public about how it ranks. Kept short and
# with the source so nothing is presented as more than it is.
ALGORITMO: Dict[str, Dict[str, Any]] = {
    "youtube": {
        "senales": [
            "Si la gente hace clic y luego sigue viendo (los clics sin visionado no ayudan).",
            "Tiempo de visionado y satisfacción: encuestas a los espectadores, me gusta, no me gusta y compartidos.",
            "Lo que cada persona vio antes: recomienda por espectador, no por canal.",
            "En Shorts cuenta si la gente lo ve o lo desliza.",
        ],
        "fuente": "YouTube Official Blog, «On YouTube's recommendation system» (2021); canal Creator Insider",
    },
    "instagram": {
        "senales": [
            "Reels: tiempo de visionado, me gusta por alcance y envíos por mensaje por alcance "
            "son las señales principales.",
            "Lo original se recomienda antes que lo republicado de otros.",
            "Cada parte (Feed, Stories, Reels, Explorar) tiene su propia clasificación.",
        ],
        "fuente": "Adam Mosseri, «Instagram Ranking Explained» (2023) y sus videos de enero de 2025",
    },
    "tiktok": {
        "senales": [
            "Interacciones: me gusta, compartidos, comentarios y si lo ven hasta el final.",
            "Información del video: texto, sonidos y hashtags.",
            "Ajustes del equipo y la cuenta (idioma, país) pesan menos.",
        ],
        "fuente": "TikTok Newsroom, «How TikTok recommends videos #ForYou» (2020)",
    },
}
LIMITE = "Las plataformas no publican los pesos exactos: esto es lo que han dicho, no una fórmula."


def _get(url: str, **kw: Any) -> Any:
    import httpx

    kw.setdefault("timeout", 12)
    kw.setdefault("headers", UA)
    kw.setdefault("follow_redirects", True)
    return httpx.get(url, **kw)


def autocomplete(term: str, lang: str = "es", get: Callable[..., Any] = _get,
                 sites: tuple = ("yt", "")) -> List[Dict[str, str]]:  # fmt: skip
    """What people type after *term* on YouTube and Google (public suggest)."""
    out: List[Dict[str, str]] = []
    seen = set()
    for ds in sites:
        params = {"client": "firefox", "q": term, "hl": lang}
        if ds:
            params["ds"] = ds
        try:
            data = get(
                "https://suggestqueries.google.com/complete/search", params=params
            ).json()
        except Exception:  # noqa: BLE001
            continue
        for s in (data[1] if isinstance(data, list) and len(data) > 1 else [])[:10]:
            s = str(s).strip()
            if s and s.lower() not in seen and s.lower() != term.lower():
                seen.add(s.lower())
                out.append(
                    {"busqueda": s, "donde": "YouTube" if ds == "yt" else "Google"}
                )
    return out


def searches(
    niche: str, lang: str = "es", get: Callable[..., Any] = _get
) -> List[Dict[str, str]]:
    """The niche, the niche + a question word and + each of a few letters."""
    if not niche:
        return []
    seeds = (
        [niche]
        + [f"{q} {niche}" for q in ("como", "por que", "que")]
        + [f"{niche} {c}" for c in "abcmpst"]
    )
    with ThreadPoolExecutor(6) as pool:
        rows = list(
            pool.map(
                lambda s: autocomplete(
                    s, lang, get, ("yt",) if s != niche else ("yt", "")
                ),
                seeds,
            )
        )
    seen, out = set(), []
    for row in rows:
        for r in row:
            if r["busqueda"].lower() not in seen:
                seen.add(r["busqueda"].lower())
                out.append(r)
    return out[:60]


def competition(
    niche: str, runner: Optional[Callable[[List[str]], str]] = None, n: int = 20
) -> List[Dict[str, Any]]:
    """The top videos of the niche on YouTube (titles, views, length)."""
    import subprocess

    from openjarvis.video_essay import sources

    cmd = sources.ytdlp()
    if not niche or not (cmd or runner):
        return []
    args = cmd + [
        "--dump-json",
        "--flat-playlist",
        "--no-warnings",
        f"ytsearch{n}:{niche[:80]}",
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
        vid = v.get("id")
        url = v.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
        out.append(
            {
                "titulo": str(v.get("title") or "")[:140],
                "canal": str(v.get("channel") or v.get("uploader") or "")[:80],
                "vistas": int(v.get("view_count") or 0),
                "segundos": float(v.get("duration") or 0),
                "url": url,
            }
        )
    return out


def patterns(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """What the winning titles and lengths have in common, measured."""
    from openjarvis.estudio.titulos import words

    titles = [v["titulo"] for v in videos if v.get("titulo")]
    if not titles:
        return {}
    lens = [len(t) for t in titles]
    secs = [v["segundos"] for v in videos if v.get("segundos")]
    freq: Dict[str, int] = {}
    for t in titles:
        for w in set(words(t)):
            freq[w] = freq.get(w, 0) + 1
    common = [w for w, c in sorted(freq.items(), key=lambda kv: -kv[1]) if c >= 2][:12]
    views = [v["vistas"] for v in videos if v.get("vistas")]
    return {
        "videos": len(titles),
        "largo_titulo_mediana": int(statistics.median(lens)),
        "con_numero": round(
            sum(bool(re.search(r"\d", t)) for t in titles) / len(titles), 2
        ),
        "con_pregunta": round(sum("?" in t for t in titles) / len(titles), 2),
        "duracion_mediana_s": int(statistics.median(secs)) if secs else 0,
        "cortos": sum(1 for s in secs if s <= 60),
        "palabras_comunes": common,
        "vistas_mediana": int(statistics.median(views)) if views else 0,
    }


PROMPT = """You are a channel strategist. Below is REAL data read now for the niche «{niche}»
(country {pais}, platform {plataforma}): trend signals, what people type in search, the top
videos of the niche and the patterns of their titles, and what the platform has said publicly
about ranking. Using ONLY this data, write:
- "audiencia": 2-4 sentences on who searches this and what they want (from the searches and
  signals; no ages or hours, they are not in the data);
- "oportunidades": up to {n} videos to make now; each quotes in "signal" the EXACT text of one
  trend signal or one search from the data, "format" short|long, "hook" (first line, under 12
  words), "why" (one sentence citing that data);
- "formato": what length and style win in this niche according to the top videos;
- "evitar": 1-3 things the data says not to do.
Never invent a number, a trend or a fact. Write in {idioma}.

TRENDS:
{senales}
SEARCHES:
{busquedas}
TOP VIDEOS:
{videos}
TITLE PATTERNS: {patrones}
PLATFORM SAYS: {algoritmo}

Answer ONLY JSON: {{"audiencia": "...", "oportunidades": [{{"signal": "...", "format": "short|long",
"hook": "...", "why": "..."}}], "formato": "...", "evitar": ["..."]}}"""


def _norm(t: str) -> str:
    from openjarvis.automatiza.tendencias import plain

    return plain(t)


def analizar(
    nicho: str = "",
    pais: str = "EC",
    plataforma: str = "youtube",
    *,
    n: int = 6,
    profundo: bool = False,
    idioma: str = "Spanish",
    ask: Optional[Callable[[str], str]] = None,
    get: Callable[..., Any] = _get,
    runner: Optional[Callable[[List[str]], str]] = None,
    home: Optional[Path] = None,
) -> Dict[str, Any]:
    """The whole reading for *nicho*; every opportunity tied to real data.

    Kept one hour per niche, country and platform; when nothing can be read
    now, the last reading is given back saying how old it is."""

    key = f"{_norm(nicho)}|{(pais or 'EC').upper()[:2]}|{plataforma}|{int(profundo)}"
    cached = _cache_get(key, home)
    if cached and time.time() - float(cached.get("at") or 0) < CACHE_SECONDS:
        return cached
    fresh = _analizar(nicho, pais, plataforma, n=n, profundo=profundo, idioma=idioma,
                      ask=ask, get=get, runner=runner, home=home)  # fmt: skip
    if fresh.get("aviso") and cached:
        hours = max(1, round((time.time() - float(cached.get("at") or 0)) / 3600))
        return {
            **cached,
            "aviso_viejo": f"Sin datos nuevos ahora; esta lectura es de hace {hours} h.",
        }
    if not fresh.get("aviso"):
        _cache_put(key, {**fresh, "at": time.time()}, home)
    return fresh


CACHE_SECONDS = 3600


def _cache_file(home: Optional[Path]) -> Path:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = Path(get_config_dir())
    return Path(home) / "estudio" / "radar.json"


def _cache_get(key: str, home: Optional[Path]) -> Dict[str, Any]:
    try:
        return json.loads(_cache_file(home).read_text("utf-8")).get(key) or {}
    except (OSError, ValueError, AttributeError):
        return {}


def _cache_put(key: str, value: Dict[str, Any], home: Optional[Path]) -> None:
    path = _cache_file(home)
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    data[key] = value
    if len(data) > 40:  # the newest 40 readings
        data = dict(
            sorted(data.items(), key=lambda kv: -float(kv[1].get("at") or 0))[:40]
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    except OSError:
        pass


def _analizar(
    nicho: str,
    pais: str,
    plataforma: str,
    *,
    n: int,
    profundo: bool,
    idioma: str,
    ask: Optional[Callable[[str], str]],
    get: Callable[..., Any],
    runner: Optional[Callable[[List[str]], str]],
    home: Optional[Path],
) -> Dict[str, Any]:
    from openjarvis.automatiza import tendencias

    plataforma = plataforma if plataforma in ALGORITMO else "youtube"
    nicho = " ".join(str(nicho or "").split())[:80]
    lang = tendencias.LANG_OF.get((pais or "EC").upper()[:2], "en")
    started = time.time()
    with ThreadPoolExecutor(4) as pool:
        f_trends = pool.submit(tendencias.read, pais, nicho, get=get, home=home)
        f_search = pool.submit(searches, nicho, lang, get)
        f_comp = pool.submit(competition, nicho, runner)
        f_deep = pool.submit(_deep, nicho, ask) if profundo and nicho else None
        try:
            trend = f_trends.result() or {}
        except Exception:  # noqa: BLE001
            trend = {}
        busq = _safe(f_search)
        comp = _safe(f_comp)
        deep = _safe(f_deep, "") if f_deep else ""
    signals = trend.get("senales") or []
    comp.sort(key=lambda v: -v.get("vistas", 0))
    pats = patterns(comp)
    out: Dict[str, Any] = {
        "nicho": nicho, "pais": trend.get("pais", pais), "plataforma": plataforma,
        "fuentes": sorted(set(trend.get("fuentes") or []) | ({"Autocompletar"} if busq else set())
                          | ({"YouTube (búsqueda)"} if comp else set())),
        "tendencias": signals[:15], "busquedas": busq[:25], "competencia": comp[:10], "patrones": pats,
        "algoritmo": {**ALGORITMO[plataforma], "limite": LIMITE},
        "audiencia_real": "Horas, edades y países reales salen de las estadísticas de su propio canal; "
                          "sin ellas no se adivinan.",
        "investigacion": deep, "oportunidades": [], "segundos": 0.0,
    }  # fmt: skip
    if not (signals or busq or comp):
        out["aviso"] = (
            "No pude leer datos ahora (sin internet o las fuentes no respondieron)."
        )
        return out
    if ask is None:
        try:
            from openjarvis.creator import llm

            def ask(p: str) -> str:
                return llm.ask(p, json_mode=True)
        except Exception:  # noqa: BLE001
            ask = None
    data: Dict[str, Any] = {}
    if ask is not None:
        prompt = PROMPT.format(
            niche=nicho or "general", pais=out["pais"], plataforma=plataforma, n=n, idioma=idioma,
            senales="\n".join(tendencias._line(s) for s in signals[:30]) or "-",
            busquedas="\n".join(f"- [{b['donde']}] {b['busqueda']}" for b in busq[:30]) or "-",
            videos="\n".join(f"- {v['titulo']} — {v['vistas']:,} vistas, {int(v['segundos'])} s ({v['canal']})"
                             for v in comp[:12]) or "-",
            patrones=json.dumps(pats, ensure_ascii=False),
            algoritmo=" ".join(ALGORITMO[plataforma]["senales"]),
        )  # fmt: skip
        try:
            data = json.loads(re.search(r"\{.*\}", ask(prompt), re.S).group(0))  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            data = {}
    known = {_norm(s["tema"]): {"tipo": "tendencia", **s} for s in signals}
    known.update({_norm(b["busqueda"]): {"tipo": "búsqueda", **b} for b in busq})
    for o in data.get("oportunidades") or []:
        if not isinstance(o, dict):
            continue
        sig = _norm(str(o.get("signal") or ""))
        match = known.get(sig) or next(
            (v for k, v in known.items() if sig and (sig in k or k in sig)), None
        )
        if match is None:
            continue  # not in the data: invented
        out["oportunidades"].append({
            "gancho": str(o.get("hook") or "")[:120], "formato": "long" if o.get("format") == "long" else "short",
            "por_que": str(o.get("why") or "")[:240], "dato": match,
        })  # fmt: skip
        if len(out["oportunidades"]) >= n:
            break
    out["audiencia"] = str(data.get("audiencia") or "")[:700]
    out["formato"] = str(data.get("formato") or "")[:400]
    out["evitar"] = [str(e)[:160] for e in (data.get("evitar") or [])][:3]
    out["segundos"] = round(time.time() - started, 1)
    return out


def _safe(fut: Any, default: Any = None) -> Any:
    try:
        return fut.result()
    except Exception:  # noqa: BLE001
        return [] if default is None else default


def _deep(niche: str, ask: Optional[Callable[[str], str]]) -> str:
    from openjarvis.research import deep

    kw = {"ask": ask} if ask else {}
    report = deep.research(
        f"Quién ve videos de {niche} y qué buscan; qué formatos les funcionan",
        rounds=1,
        **kw,
    )
    return report.markdown()[:6000]


def texto(res: Dict[str, Any]) -> str:
    if res.get("aviso"):
        return res["aviso"]
    old = [res["aviso_viejo"]] if res.get("aviso_viejo") else []
    lines = [
        f"Radar de «{res['nicho'] or 'general'}» ({res['pais']}, {res['plataforma']}). "
        f"Fuentes: {', '.join(res['fuentes'])}."
    ]
    if res.get("audiencia"):
        lines.append(f"Público: {res['audiencia']}")
    for o in res["oportunidades"]:
        d = o["dato"]
        what = d.get("tema") or d.get("busqueda")
        lines.append(
            f"- [{o['formato']}] «{o['gancho']}» — {o['por_que']} (dato: {what})"
        )
    p = res.get("patrones") or {}
    if p:
        common = ", ".join(p["palabras_comunes"][:8])
        lines.append(
            f"En el nicho: títulos de ~{p['largo_titulo_mediana']} letras, "
            f"{int(p['con_numero'] * 100)} % con número, duración típica "
            f"{p['duracion_mediana_s']} s; palabras que se repiten: {common}."
        )
    if res.get("formato"):
        lines.append(f"Formato: {res['formato']}")
    for e in res.get("evitar") or []:
        lines.append(f"Evitar: {e}")
    a = res["algoritmo"]
    lines.append(
        f"Lo que dice {res['plataforma']}: "
        + " ".join(a["senales"])
        + f" ({a['fuente']}). {a['limite']}"
    )
    lines.append(res["audiencia_real"])
    return "\n".join(old + lines)


__all__ = [
    "ALGORITMO",
    "analizar",
    "autocomplete",
    "competition",
    "patterns",
    "searches",
    "texto",
]

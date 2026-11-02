"""Only one job: find and choose scenes of real films and series on the web.

1. **Which scene.** A model names real films or series and the exact scene
   that shows the idea («Rocky (1976) — running up the museum steps»). If
   no model answers, the famous scenes of :data:`films.KNOWN_SCENES` that
   share words with the idea. A film without a real year is dropped.
2. **Where it is.** Each scene is searched by name (``sources.search_scenes``,
   yt-dlp): only clips whose title names the film, never full movies or
   episodes (piracy), never reaction or commentary videos.
3. **Which clip.** Ranked by code: official studio and clip channels first,
   a real clip length, the words of the scene in the title.
4. **Public domain** as a reserve: films on the Internet Archive.

Nothing is downloaded unless asked (``descargar``), and then only a few
seconds of each clip. Every clip says it is «uso con cita (no libre)»: the
owner of the film can claim it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROMPT = """You are a film researcher for a video editor. The video is about: {tema}.
Name up to {n} scenes of REAL, well-known films or TV series that show exactly this idea
(same action, situation or emotion), so a viewer recognises the connection.
Rules: only films and series that exist, with original title and year; famous scenes that
are easy to find as official clips or trailers; vary decades and genres; never invent.
Answer ONLY JSON: {{"scenes": [{{"film": "Title", "year": 1976, "scene": "short English description",
"why": "one short sentence in Spanish: why it fits"}}]}}"""

AVISO = (
    "Escenas con derechos de sus estudios: use unos segundos, cite la película "
    "y sepa que pueden reclamarlas. Nada de películas completas."
)

_YEAR = re.compile(r"^(18[89]\d|19\d\d|20[0-3]\d)$")


def _ask_default() -> Optional[Callable[[str], str]]:
    try:
        from openjarvis.creator import llm
    except Exception:  # noqa: BLE001
        return None
    return lambda prompt: llm.ask(prompt, json_mode=True)


def scenes_for(
    tema: str, n: int = 5, ask: Optional[Callable[[str], str]] = None
) -> List[Dict[str, Any]]:
    """Real scenes that show *tema* (a model first, the known list after)."""
    from openjarvis.video_essay import films
    from openjarvis.video_essay.sources import _tokens

    out: List[Dict[str, Any]] = []
    ask = ask or _ask_default()
    if ask is not None:
        try:
            raw = ask(PROMPT.format(tema=tema[:300], n=n))
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))  # type: ignore[union-attr]
            for s in data.get("scenes") or []:
                name = " ".join(str(s.get("film") or "").split())[:80]
                year = str(s.get("year") or "")
                scene = " ".join(str(s.get("scene") or "").split())[:120]
                if name and scene and _YEAR.match(year):
                    out.append({"pelicula": name, "anio": int(year), "escena": scene,
                                "por_que": str(s.get("why") or "")[:160], "origen": "modelo"})  # fmt: skip
        except Exception:  # noqa: BLE001 — no model: the known scenes
            out = []
    if not out:
        have = _tokens(tema)
        scored = []
        for keys, name, year, scene in films.KNOWN_SCENES:
            hits = sum(any(h.startswith(k[:5]) for h in have) for k in _tokens(keys))
            if hits:
                scored.append((hits, name, year, scene))
        scored.sort(key=lambda r: -r[0])
        out = [{"pelicula": nm, "anio": yr, "escena": sc, "por_que": "Coincide con las palabras del tema.",
                "origen": "lista conocida"} for _, nm, yr, sc in scored[:n]]  # fmt: skip
    seen, unique = set(), []
    for s in out:  # never two scenes of the same film
        key = s["pelicula"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique[:n]


def _clip(c: Any, wanted: str) -> Dict[str, Any]:
    from openjarvis.video_essay import sources

    return {"titulo": c.title, "url": c.url, "canal": c.credit, "segundos": c.seconds,
            "inicio": c.start, "puntos": round(sources.score(c, wanted), 2), "licencia": c.licence}  # fmt: skip


def buscar(
    tema: str,
    n: int = 5,
    *,
    por_escena: int = 3,
    ask: Optional[Callable[[str], str]] = None,
    runner: Optional[Callable[[List[str]], str]] = None,
    dominio_publico: bool = True,
) -> Dict[str, Any]:
    """Scenes for *tema* and, for each, the best clips found, best first."""
    from openjarvis.video_essay import sources

    tema = " ".join(str(tema or "").split())
    if not tema:
        return {"escenas": [], "aviso": "Dígame de qué trata el video."}
    if not sources.web_allowed():
        return {
            "escenas": [],
            "aviso": "La búsqueda en internet está apagada (SERGIO_CLIPS_WEB=0).",
        }
    found = []
    used: set = set()  # one clip never serves two scenes
    for s in scenes_for(tema, n, ask):
        query = f"{s['pelicula']} ({s['anio']}) {s['escena']}"
        cands: List[Any] = []
        # the exact scene; then the film by name (its clips and trailer)
        for q in (query, f"{s['pelicula']} ({s['anio']})"):
            try:
                found_now = sources.search_scenes(q, por_escena * 2, runner)
            except Exception:  # noqa: BLE001
                found_now = []
            cands = [
                c
                for c in sources.rank(found_now, query)
                if c.url not in used and not (c.seconds and c.seconds < 8)
            ]
            if cands:
                break
        clips = [_clip(c, query) for c in cands[:por_escena]]
        used.update(c["url"] for c in clips)
        found.append({**s, "busqueda": query, "clips": clips})
    reserve: List[Dict[str, Any]] = []
    if dominio_publico:
        try:
            for c in sources.search_archive(f"{tema} film", 3):
                reserve.append(
                    {
                        **_clip(c, tema),
                        "licencia": c.licence or "Dominio público (Internet Archive)",
                    }
                )
        except Exception:  # noqa: BLE001
            reserve = []
    con_clip = sum(1 for s in found if s["clips"])
    return {
        "tema": tema,
        "escenas": found,
        "dominio_publico": reserve,
        "con_clip": con_clip,
        "aviso": AVISO,
    }


def descargar(
    url: str, dest: Path, segundos: float = 6.0, inicio: float = 0.0
) -> Optional[str]:
    """A few seconds of one clip (never the whole video)."""
    import shutil

    from openjarvis.video_essay import sources

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    c = sources.Candidate(url, "web", "", "Uso con cita (no libre)", inicio)
    return sources.fetch(c, Path(dest), min(float(segundos), 12.0), ffmpeg)


def texto(res: Dict[str, Any]) -> str:
    """The result in plain words for the chat."""
    if not res.get("escenas"):
        return res.get("aviso") or "No encontré escenas para ese tema."
    lines = [f"Escenas para «{res['tema']}»:"]
    for s in res["escenas"]:
        lines.append(
            f"- {s['pelicula']} ({s['anio']}): {s['escena']}. {s.get('por_que', '')}".rstrip()
        )
        if not s["clips"]:
            lines.append("  sin clip oficial encontrado ahora")
        for c in s["clips"]:
            lines.append(
                f"  {c['titulo'] or c['url']} · {c['canal'] or 'canal sin nombre'} · {c['url']}"
            )
    for c in res.get("dominio_publico") or []:
        lines.append(f"- Dominio público: {c['titulo'] or c['url']} · {c['url']}")
    lines.append(res["aviso"])
    return "\n".join(lines)


__all__ = ["AVISO", "buscar", "descargar", "scenes_for", "texto"]

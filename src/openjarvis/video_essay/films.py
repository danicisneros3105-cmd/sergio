"""Scenes of real films and series chosen for what is said, not by chance.

The owner (28 Oct 2026): «necesito que los videos, clips e imágenes sean
también de películas y tengan coherencia con el tema». Searching the words
of a shot («a man who never gives up») brings random clips. Instead, once
per video, the editor names, for each shot marked ``film``, a real film or
series and the exact scene that shows that moment («Rocky (1976) — running
up the museum steps»). The search then asks for that scene by name, and
``sources.search_scenes`` only keeps clips whose title names the film.

Rules given to the model: only films and series that exist (title and
year), the scene must show what is being said, no more than two shots from
the same film, and the mood must match the beat. A shot it cannot place
keeps its own search.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Sequence, Tuple

log = logging.getLogger(__name__)

SCENES_PROMPT = """You are a film-literate video editor. The video «{title}» is about: {logline}.
For each numbered shot below, choose ONE scene of a REAL, well-known film or TV series that shows
exactly what is being said at that moment (same action, situation or emotion), so a viewer
recognises the connection. Rules:
- Only films and series that really exist; give the original title and the year.
- The scene must be famous or easy to find as an official clip or trailer.
- At most 2 shots from the same film; vary genres and decades when it fits.
- Match the mood of the line (triumph, fear, loneliness, discovery…).
- If no real scene fits a shot, leave it out. Never invent a film or a scene.
Shots (index: what is said | what the editor wanted to show):
{shots}
Answer ONLY JSON: {{"scenes": [{{"shot": index, "film": "Title", "year": 1976,
"scene": "short description of the scene in English"}}]}}"""

_YEAR = re.compile(r"^(18[89]\d|19\d\d|20[0-3]\d)$")

RETRY_WAITS = (15.0, 45.0)  # a busy model (503/429) usually answers on a retry
sleep = time.sleep  # a seam for the tests

# When no model can answer at all, famous scenes of real films that show
# the most common ideas of these videos, so the film shots still get one.
# (words of the line, film, year, scene) — all real, all easy to find.
KNOWN_SCENES: Tuple[Tuple[str, str, int, str], ...] = (
    ("rendir rindas rendirse abandonar persist levant again otra vez", "Rocky", 1976,
     "running up the museum steps"),
    ("golpe golpea hit caer caída caídas suelo fuerte", "Rocky Balboa", 2006,
     "it ain't about how hard you hit speech"),
    ("caemos caer caig caída fall levantarse aprender", "Batman Begins", 2005,
     "why do we fall scene"),
    ("trabajo puerta rechaz entrevista oportunidad sueño no", "The Pursuit of Happyness", 2006,
     "getting the job scene"),
    ("solo sola soledad isla sobrevivir fuego aislado", "Cast Away", 2000,
     "making fire on the island"),
    ("esperanza escapar libertad prisión lluvia paciencia", "The Shawshank Redemption", 1994,
     "escape in the rain"),
    ("disciplina práctica entrenar ensayar repetir perfección", "Whiplash", 2014,
     "final drum solo"),
    ("lección enseñ maestro repetición paciencia", "The Karate Kid", 1984,
     "wax on wax off"),
    ("entrena entrenamiento esfuerzo correr sudor", "Creed", 2015,
     "training run through the streets"),
    ("decidir decisión elegir camino tiempo", "The Lord of the Rings: The Fellowship of the Ring", 2001,
     "all we have to decide is what to do with the time"),
    ("elegir elección verdad realidad despertar", "The Matrix", 1999,
     "red pill or blue pill"),
    ("imposible fallo fracaso opción problema solución", "Apollo 13", 1995,
     "failure is not an option"),
    ("ciencia problema resolver sobrevivir marte", "The Martian", 2015,
     "science the problem scene"),
    ("imposible tiempo arriesgar riesgo", "Interstellar", 2014,
     "docking scene"),
    ("cada día rutina repetir mismo día cambiar", "Groundhog Day", 1993,
     "waking up to the same day"),
    ("inventor invento idea crear código empresa", "The Social Network", 2010,
     "writing the code all night"),
    ("multitud público victoria ganar entretenidos", "Gladiator", 2000,
     "are you not entertained"),
    ("aprender torpe principiante creer", "Kung Fu Panda", 2008,
     "training with the dumplings"),
    ("dinero bolsa vender comprar mercado riqueza ambición", "The Wolf of Wall Street", 2013,
     "sell me this pen scene"),
    ("crisis banco hipoteca burbuja economía finanzas", "The Big Short", 2015,
     "Jenga tower mortgage explanation scene"),
    ("sueño mente subconsciente arquitectura doblar ciudad", "Inception", 2010,
     "Paris folding city scene"),
    ("inteligencia artificial máquina futuro robot humano", "Ex Machina", 2014,
     "Turing test interview scene"),
    ("velocidad carrera motor límite ganar", "Ford v Ferrari", 2019,
     "7000 RPM Le Mans night drive"),
    ("concentración ajedrez estrategia mente calcular", "The Queen's Gambit", 2020,
     "ceiling chess visualization scene"),
    ("química cocinar laboratorio precisión imperio", "Breaking Bad", 2008,
     "cooking montage in the lab"),
    ("física átomo bomba historia ciencia", "Oppenheimer", 2023,
     "Trinity test countdown scene"),
    ("correr maratón camino cruzar país sin parar", "Forrest Gump", 1994,
     "he starts running across America"),
    ("saltar fe ciudad rascacielos miedo", "Spider-Man: Into the Spider-Verse", 2018,
     "leap of faith scene"),
)  # fmt: skip


def find_scenes_for_text(text: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Return matching real film/series scenes and searched clip candidates for *text*."""
    from openjarvis.video_essay.sources import _tokens, search_scenes

    have = _tokens(text)
    scored = []
    for keys, name, year, scene in KNOWN_SCENES:
        hits = sum(any(h.startswith(k[:5]) for h in have) for k in _tokens(keys))
        if hits > 0 or not have:
            scored.append((hits, name, year, scene))
    if not scored:
        scored = [
            (1, name, year, scene)
            for _, name, year, scene in KNOWN_SCENES[:max_results]
        ]
    scored.sort(key=lambda r: -r[0])
    out: List[Dict[str, Any]] = []
    for _, name, year, scene in scored[:max_results]:
        query = f"{name} ({year}) {scene}"
        clips = []
        try:
            clips = [{"title": c.title, "url": c.url} for c in search_scenes(query, 3)]
        except Exception:  # noqa: BLE001
            clips = []
        out.append(
            {"film": name, "year": year, "scene": scene, "query": query, "clips": clips}
        )
    return out


def known_scenes(shots: Sequence[Any], words: Sequence[Any], film: List[int]) -> list:
    """Scenes for the film shots from :data:`KNOWN_SCENES`, by the words
    said in each shot (only when a line clearly matches)."""
    from openjarvis.video_essay.sources import _tokens

    out = []
    for i in film:
        s = shots[i]
        said = (
            " ".join(w.text for w in words[s.first : s.last]) + " " + (s.visual or "")
        )
        have = _tokens(said)
        best, score = None, 0
        for keys, name, year, scene in KNOWN_SCENES:
            hits = sum(any(h.startswith(k[:5]) for h in have) for k in _tokens(keys))
            if hits > score:
                best, score = (name, year, scene), hits
        if best and score >= 1:
            out.append({"shot": i, "film": best[0], "year": best[1], "scene": best[2]})
    return out


def plan_scenes(
    shots: Sequence[Any],
    words: Sequence[Any],
    title: str,
    logline: str,
    ask: Callable[[str], str],
    limit: int = 60,
) -> int:
    """Give the ``film`` shots a named scene; returns how many got one."""
    film = [i for i, s in enumerate(shots) if getattr(s, "source", "") == "film"][
        :limit
    ]
    if not film:
        return 0
    rows = []
    for i in film:
        s = shots[i]
        said = " ".join(w.text for w in words[s.first : s.last])[:160]
        rows.append(f"{i}: {said} | {(s.visual or '')[:120]}")
    prompt = SCENES_PROMPT.format(
        title=title[:120], logline=logline[:400], shots="\n".join(rows)
    )
    scenes = None
    for wait in (0.0, *RETRY_WAITS):  # Google busy: wait and ask again
        if wait:
            sleep(wait)
        try:
            data = json.loads(ask(prompt))
        except Exception as exc:  # noqa: BLE001
            log.warning("film scenes not chosen yet: %s", exc)
            continue
        scenes = data.get("scenes") if isinstance(data, dict) else None
        if scenes:
            break
    done = apply(shots, scenes, set(film))
    if done == 0:  # no model answered: famous real scenes that fit the words
        done = apply(shots, known_scenes(shots, words, film), set(film))
    return done


def apply(shots: Sequence[Any], scenes: Any, allowed: set) -> int:
    """Write the chosen scenes into the shots (checked, at most two per film)."""
    per_film: Dict[str, int] = {}
    done = 0
    for item in scenes if isinstance(scenes, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("shot"))
        except (TypeError, ValueError):
            continue
        name = " ".join(str(item.get("film") or "").split())[:80]
        year = str(item.get("year") or "").strip()
        scene = " ".join(str(item.get("scene") or "").split())[:100]
        if i not in allowed or not name or not scene or not _YEAR.match(year):
            continue
        key = name.lower()
        if per_film.get(key, 0) >= 2:
            continue
        per_film[key] = per_film.get(key, 0) + 1
        shots[i].search = f"{name} ({year}) {scene}"
        shots[i].notes = list(getattr(shots[i], "notes", []) or []) + [
            f"escena: {name} ({year})"
        ]
        done += 1
    return done


def films_in(shots: Sequence[Any]) -> List[str]:
    """The films and series the video quotes (for the credits)."""
    out: List[str] = []
    for s in shots:
        for n in getattr(s, "notes", []) or []:
            if n.startswith("escena: ") and n[8:] not in out:
                out.append(n[8:])
    return out


__all__ = [
    "KNOWN_SCENES",
    "SCENES_PROMPT",
    "apply",
    "films_in",
    "known_scenes",
    "plan_scenes",
]

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
from typing import Any, Callable, Dict, List, Sequence

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
    try:
        data = json.loads(
            ask(
                SCENES_PROMPT.format(
                    title=title[:120], logline=logline[:400], shots="\n".join(rows)
                )
            )
        )
    except Exception as exc:  # noqa: BLE001 — the shots keep their own search
        log.warning("no film scenes chosen: %s", exc)
        return 0
    return apply(
        shots, data.get("scenes") if isinstance(data, dict) else None, set(film)
    )


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


__all__ = ["SCENES_PROMPT", "apply", "films_in", "plan_scenes"]

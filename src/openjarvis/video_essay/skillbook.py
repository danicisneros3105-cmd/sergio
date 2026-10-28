"""Skills from GitHub for the script and for motion graphics.

The owner (27 Oct 2026): «agrega mínimo 20 skills reales de GitHub para la
creación de guiones (pausas, cambios de tono…) y 25 para motion graphics
profesionales (como Zack D. Films o MrBeast)». ``skills_catalog.json`` lists
the ones checked to exist (75: 37 for the script, 38 for motion, each with
its repository, file and licence): agent skills in the SKILL.md format
(Remotion's own, HeyGen's HyperFrames, GSAP, Manim, MrBeast-style hooks,
retention, Fountain screenplays, voice direction…) and the open tools they
build on (Motion Canvas, Revideo, Theatre.js, Lottie, gl-transitions…).

Like the prompt library, the files are **downloaded to the owner's computer**
(:func:`sync`, run by the update) and never copied into this repository:
several have no licence or a copyleft one. A skill whose licence forbids
commercial use is listed but never used (``usable: false``).

:func:`guidance` picks the skills that fit the video being made and gives
the director (script) or the editor (cuts and motion) their key parts, with
the delivery rules below always on: Sergio's narration has real pauses and
tone changes, written into the script and performed by the voice.
"""

from __future__ import annotations

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

CATALOG = Path(__file__).with_name("skills_catalog.json")
UA = {"User-Agent": "Sergio/1.0 (skills sync)"}

DELIVERY = """DELIVERY (how each beat is SAID, written by Sergio): give every beat a "delivery" \
with "tone" (one of: calm, warm, curious, urgent, excited, serious, whisper, ironic, \
triumphant) and "pause" (seconds of silence after it: 0 for a running line, 0.3 between \
ideas, 0.6-0.9 before a turn or a reveal, 1.0-1.4 after the strongest line). Change the tone \
when the story turns (problem → turn → payoff), never the same tone for more than three \
beats in a row; short punchy sentences get a pause after them; questions to the viewer get a \
beat of silence; the payoff is said slower and lower. Use «…» inside a line for a short \
held pause and a full stop for a breath."""


def catalog() -> Dict[str, List[Dict[str, Any]]]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def counts() -> Dict[str, int]:
    data = catalog()
    return {k: len(v) for k, v in data.items()}


def folder(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = get_config_dir()
    return Path(home) / "video_skills"


def _slug(entry: Dict[str, Any]) -> str:
    base = f"{entry['repo']}__{entry['path']}"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", base)[:180] + ".md"


def raw_url(entry: Dict[str, Any]) -> str:
    return f"https://raw.githubusercontent.com/{entry['repo']}/{entry.get('branch') or 'main'}/{entry['path']}"


def sync(home: Optional[Path] = None, get: Any = None) -> Dict[str, int]:
    """Download every skill file to this computer (kept if a download fails)."""
    if get is None:
        import httpx

        def get(url: str) -> str:
            r = httpx.get(url, headers=UA, timeout=30, follow_redirects=True)
            r.raise_for_status()
            return r.text

    out = {"bajadas": 0, "fallidas": 0}
    jobs = []
    for kind, entries in catalog().items():
        dest = folder(home) / kind
        dest.mkdir(parents=True, exist_ok=True)
        for e in entries:
            jobs.append((dest / _slug(e), raw_url(e)))

    def one(item: tuple) -> bool:
        path, url = item
        try:
            text = get(url)
        except Exception:  # noqa: BLE001 — the copy from last time stays
            return False
        path.write_text(text[:200_000], encoding="utf-8")
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        for ok in pool.map(one, jobs):
            out["bajadas" if ok else "fallidas"] += 1
    return out


def _plain(text: str) -> str:
    text = (
        unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9 ]+", " ", text)


_STOP = set(
    "the a an of and or to in for with on is are de la el los las y o en un una para con que".split()
)


def _words(text: str) -> set:
    return {w for w in _plain(text).split() if len(w) > 2 and w not in _STOP}


def _body(text: str) -> str:
    """The skill without its front matter, links, code blocks and long tables."""
    text = re.sub(r"\A---.*?---\s*", "", text, flags=re.S)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    lines = [
        ln.rstrip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("|")
    ]
    return "\n".join(lines)


def guidance(
    kind: str,
    about: str,
    *,
    home: Optional[Path] = None,
    budget: int = 4500,
    top: int = 3,
    genre: str = "",
) -> str:
    """The parts of the best-fitting skills of *kind* ("guion" or "motion")
    for a video *about* this, within *budget* characters.

    Few on purpose (owner, 28 Oct 2026: «usa más skills pero no amontones
    todas para confundir al modelo»): the genre's own picks when it has
    them, else the *top* that fit best; never a list of the rest."""
    entries = [e for e in catalog().get(kind, []) if e.get("usable", True)]
    if not entries:
        return ""
    if genre:
        from openjarvis.video_essay import genres

        picks = genres.skill_names(genre, kind)
        chosen = [e for name in picks for e in entries if e["name"] == name]
        if chosen:
            entries = chosen
    want = _words(about)
    base = folder(home) / kind
    scored = []
    for e in entries:
        path = base / _slug(e)
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        hay = _words(e["name"] + " " + e["what"] + " " + text[:3000])
        skill = 2 if e.get("kind") == "skill" else 0
        scored.append((len(want & hay) + skill + (1 if text else 0), e, text))
    scored.sort(key=lambda x: -x[0])
    head = (
        "SKILLS FROM GITHUB (proven practice of top creators; follow them where they fit, "
        "Sergio's rules win on conflict):\n"
    )
    parts: List[str] = []
    left = budget - len(head) - (len(DELIVERY) if kind == "guion" else 0)
    for _, e, text in scored[:top]:
        share = max(400, left // max(1, top))
        piece = _body(text)[:share] if text else e["what"]
        parts.append(f"- {e['name']} ({e['repo']}): {piece}")
    out = head + "\n".join(parts)
    if kind == "guion":
        out += "\n" + DELIVERY
    return out[:budget]


__all__ = [
    "CATALOG",
    "DELIVERY",
    "catalog",
    "counts",
    "folder",
    "guidance",
    "raw_url",
    "sync",
]

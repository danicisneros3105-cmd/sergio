"""Typography: several typefaces, each with a job, and words placed where the
picture leaves room.

The owner (27 Oct 2026): «subtítulos en diferentes partes con diferentes
tipografías, como el video demo de NextCore». The reference mixes a tall
condensed face for the punch lines, a heavy sans for the rest, numbers in a
technical face and the odd elegant italic, and moves the words around the
frame. Here each face has a role, and :func:`dress` gives every shot its face,
its place (a free third of the frame, never on a face, never twice in the
same place in a row), its accent colour and whether it needs a block behind
the words (:mod:`openjarvis.video_essay.color`).

The faces are free (SIL Open Font License, Permanent Marker under Apache
2.0); the licence of each is next to it in ``fonts/`` and in NOTICE.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import ImageFont

FONTS = Path(__file__).parent / "fonts"


@dataclass(frozen=True)
class Face:
    file: str
    family: str  # the name libass knows it by (ASS captions)
    caps: bool  # always in capitals
    track: float  # letter spacing, as a fraction of the size
    scale: float  # size against the house face (condensed faces go bigger)
    role: str


FACES: Dict[str, Face] = {
    "base": Face("InterDisplay-Black.ttf", "Inter Display Black", False, -0.045, 1.0,
                 "the voice of the video: most lines"),
    "impacto": Face("Anton-Regular.ttf", "Anton", True, 0.005, 1.32,
                    "one to three words that hit: tall, condensed, capitals"),
    "pesada": Face("ArchivoBlack-Regular.ttf", "Archivo Black", True, -0.03, 0.92,
                   "a short heading or a label on a block"),
    "elegante": Face("DMSerifDisplay-Italic.ttf", "DM Serif Display", False, -0.01, 1.12,
                     "a quote, a feeling, a turn of the story"),
    "tecnica": Face("SpaceMono-Bold.ttf", "Space Mono", True, 0.0, 0.82,
                    "numbers, dates, money, data"),
    "mano": Face("PermanentMarker-Regular.ttf", "Permanent Marker", False, 0.0, 1.0,
                 "an aside, a note in the margin"),
}  # fmt: skip
DEFAULT_SET = ("base", "impacto", "elegante", "tecnica")

_NUMBER = re.compile(r"\d|[$€%£¥]")
_FEELING = {
    "imagina", "imagine", "quizás", "quizas", "tal", "recuerda", "remember", "siempre",
    "nunca", "never", "always", "amor", "love", "vida", "life", "sueño", "dream",
    "alma", "corazón", "corazon", "heart", "silencio", "silence", "solo", "alone",
}  # fmt: skip
_ASIDE = {"ojo", "psst", "spoiler", "nota", "pd", "ps", "obvio", "spoiler:"}


@lru_cache(maxsize=128)
def font(face: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / FACES[face].file), size)


def pairing(profile: Optional[Dict[str, Any]] = None) -> Tuple[str, ...]:
    """The faces this video uses: the style's own leaning first. Four at
    most, so the mix reads as a design and not as a ransom note."""
    text = profile.get("text") if isinstance(profile, dict) else None
    words = " ".join(
        str(v)
        for v in ((text or {}).values() if isinstance(text, dict) else [text or ""])
    ).lower()
    look = str((profile or {}).get("look") or "").lower() + " " + words
    chosen: List[str] = ["base"]
    if any(k in look for k in ("serif", "elegant", "luxury", "lujo", "editorial")):
        chosen.append("elegante")
    if any(
        k in look for k in ("bold", "kinetic", "impact", "condensed", "caps", "viral")
    ):
        chosen.append("impacto")
    if any(k in look for k in ("hand", "marker", "scribble", "mano", "doodle")):
        chosen.append("mano")
    for name in DEFAULT_SET:
        if len(chosen) >= 4:
            break
        if name not in chosen:
            chosen.append(name)
    return tuple(chosen[:4])


def _clean(text: str) -> List[str]:
    return [w for w in re.sub(r"[^\w\s$€%£¥]", " ", text.lower()).split() if w]


def face_for(text: str, allowed: Sequence[str] = DEFAULT_SET, prev: str = "") -> str:
    """The face for an on-screen line, by what the line is."""
    words = _clean(text)
    want = "base"
    if _NUMBER.search(text):
        want = "tecnica"
    elif (
        text.strip()[:1] in "«\"“'"
        or text.rstrip().endswith("…")
        or _FEELING & set(words)
    ):
        want = "elegante"
    elif words and words[0] in _ASIDE or text.strip().startswith("("):
        want = "mano"
    elif len(words) <= 2 or text.rstrip().endswith("!"):
        want = "impacto"
    elif len(words) <= 4 and text.isupper():
        want = "pesada"
    if want not in allowed:
        want = (
            "impacto" if want in ("pesada", "mano") and "impacto" in allowed else "base"
        )
    if want == prev and want in ("base", "impacto") and len(allowed) > 1:
        # the same face twice in a row only when the line asks for it
        other = "impacto" if want == "base" else "base"
        if other in allowed and (other != "impacto" or len(words) <= 4):
            want = other
    return want


def dress(
    shots: Sequence[Any],
    words: Sequence[Any],
    still: Callable[[Any], Any],
    profile: Optional[Dict[str, Any]] = None,
) -> int:
    """Face, place, accent and block for every shot with words on it.

    *still(shot)* gives a small picture of the shot's background. Choices
    the editor already made (a face, a place other than the middle, an
    accent, a block) are kept; this only fills what was left open and is
    safe to run again. Returns how many shots it touched.

    Colour follows one rule for the whole video, as a colour script does:
    one accent (the style's own, or the complement of the footage's main
    colour), and a block behind the words where white would not read."""
    from openjarvis.video_essay import color

    faces = pairing(profile)
    text = (profile or {}).get("text") or {}
    text = text if isinstance(text, dict) else {}
    brand = color.rgb_of(str(text.get("accent") or ""))
    style = str(text.get("style") or "").lower()
    boxed_style = "box" in style or " on red" in style or "on black" in style
    todo = [s for s in shots if s.text_style != "none" and "tipo:auto" not in s.notes]
    stills: Dict[int, Any] = {}
    for shot in todo:
        if shot.kind != "card":
            try:
                stills[id(shot)] = still(shot)
            except Exception:  # noqa: BLE001 — a shot without a still keeps its place
                stills[id(shot)] = None
    accent = brand or _video_accent([v for v in stills.values() if v is not None])
    prev_face, prev_zone, touched = "", "", 0
    for shot in shots:
        if shot.text_style == "none":
            prev_face = prev_zone = ""
            continue
        if "tipo:auto" in shot.notes:
            prev_face, prev_zone = shot.font, shot.position
            continue
        line = shot.text or " ".join(w.text for w in words[shot.first : shot.last])
        if not shot.font:
            shot.font = face_for(line, faces, prev_face)
        img = stills.get(id(shot))
        if img is not None and shot.device == "none":
            if shot.position == "center":
                shot.position = color.best_zone(
                    img,
                    _zones_for(line, shot.font),
                    avoid=[prev_zone] if prev_zone else (),
                    prefer="lower",
                    readable=True,
                )
            if not shot.accent and accent is not None:
                shot.accent = color.hex_of(accent)
            if not shot.box:
                seen = color.legible(img, shot.position, accent or (232, 38, 42))
                if seen["box"]:
                    shot.box = "all"  # every word on a block: it would not read
                elif boxed_style and shot.highlight:
                    shot.box = "word"  # the reference's «white on red»
        elif shot.kind == "card" and not shot.accent and brand:
            shot.accent = color.hex_of(brand)
        shot.notes.append("tipo:auto")
        prev_face, prev_zone = shot.font, shot.position
        touched += 1
    return touched


def _video_accent(stills: Sequence[Any]) -> Optional[Tuple[int, int, int]]:
    """One accent for the whole video: the complement of what the footage
    is mostly made of (all its stills seen as one picture)."""
    if not stills:
        return None
    from PIL import Image

    from openjarvis.video_essay import color

    w, h = 96, 54
    board = Image.new("RGB", (w * len(stills), h))
    for i, img in enumerate(stills):
        board.paste(img.convert("RGB").resize((w, h)), (i * w, 0))
    return color.accent_for(board)


def _zones_for(line: str, face: str) -> Iterable[str]:
    """Long lines need the wide bands; up to eight words fit a side or a
    corner (they wrap to more lines there)."""
    every = (
        "lower",
        "upper",
        "center",
        "lower_left",
        "lower_right",
        "upper_left",
        "upper_right",
        "left",
        "right",
    )
    if len(_clean(line)) <= 8 or face == "impacto":
        return every
    return ("lower", "upper", "center", "left", "right")


__all__ = ["DEFAULT_SET", "FACES", "Face", "dress", "face_for", "font", "pairing"]

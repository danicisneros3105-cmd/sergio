"""What kind of video it is, and what that changes in the edit.

The owner (28 Oct 2026): «mejor elección de clips y videos según temática,
no solo videos inspiracionales, sino también cortos cinematográficos,
animaciones y edición pesada tipo videos de MrBeast». Each genre names its
style, the words that turn a clip search towards its look, how much of it
comes from films and series, and the motion-graphics pass that finishes the
plan (``finish``). The brief decides the genre (``detect``); a style the
owner chose by name always wins.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class Genre:
    key: str
    name: str
    style: str
    words: Tuple[str, ...]  # in the brief, these pick the genre
    search: str  # added to every clip search, so the footage has the look
    film_share: float  # scenes of films and series among the pictures
    sources: Tuple[str, ...] = ()  # preferred order, when it differs
    notes: str = ""  # what the director and the editor must do
    extra: Dict[str, str] = field(default_factory=dict)
    # The few GitHub skills that fit this genre (skills_catalog.json names),
    # per stage: three at most, so the model gets a method, not a pile.
    skills: Dict[str, Tuple[str, ...]] = field(default_factory=dict)


GENRES: Dict[str, Genre] = {
    "inspiracional": Genre(
        "inspiracional", "Inspiracional / ensayo", "metas-grandes",
        ("motivacion", "motivacional", "inspiracion", "inspiracional", "habitos", "disciplina",
         "exito", "superacion", "mentalidad", "ensayo", "reflexion"),
        "", 0.4,
        notes="Video essay: a thread of ideas, cards for the key phrases, archive in black and white for the past.",
        skills={
            "guion": ("YouTube hook writing", "kallaway-storytelling", "tts-director"),
            "motion": ("kinetic-cut-video", "video-typography", "captions-overlay"),
        },
    ),
    "cine": Genre(
        "cine", "Corto cinematográfico", "corto-cine",
        ("corto", "cortometraje", "cinematografico", "cinematica", "cinematic", "pelicula", "short film",
         "trailer", "historia", "drama", "thriller", "terror", "suspenso", "narrativo"),
        "cinematic film still, anamorphic, shallow depth of field, moody light", 0.5,
        sources=("film", "library", "stock", "archive", "web", "ai", "image"),
        notes=("A SHORT FILM, not an essay: scenes, not slides. Few words on screen (only a title and "
               "one or two lines that land), no cards, shots of 2-5 s that breathe, a story with a "
               "turn and an ending image. Picture source film or stock first. Silence and music matter."),
        skills={
            "guion": ("screenwriting-video", "storytelling-video", "ozu-screenplay-style"),
            "motion": ("motion-doctrine", "video-typography", "captions-overlay"),
        },
    ),
    "animacion": Genre(
        "animacion", "Animación", "animacion",
        ("animacion", "animado", "animada", "caricatura", "cartoon", "dibujos", "2d", "3d animado",
         "anime", "motion graphics", "infografia animada"),
        "animation cartoon animated 2D", 0.0,
        sources=("ai", "archive", "stock", "library", "image"),
        notes=("ANIMATION: every picture animated (2D/3D or classic cartoons), one consistent drawing "
               "style, characters that act; public-domain cartoons from the archive are welcome."),
        skills={
            "guion": ("storytelling (OpenMontage)", "youtube-shorts"),
            "motion": ("framer-motion (12 principios)", "motion-graphics (antigravity)", "motion-design"),
        },
    ),
    "pesada": Genre(
        "pesada", "Edición pesada (retención máxima)", "edicion-pesada",
        ("mrbeast", "reto", "challenge", "viral", "edicion pesada", "retencion", "youtuber",
         "sobrevivir", "ganar", "dolares", "millon", "24 horas", "100 dias", "vs"),
        "dramatic close-up reaction, action, bright saturated", 0.35,
        sources=("library", "web", "film", "stock", "archive", "ai", "image"),
        notes=("HEAVY EDIT for maximum retention (the method the biggest challenge channels wrote down "
               "for their own teams, in our words): 1) MATCH THE CLICK: the first 5 s show exactly what "
               "the title promises, then raise it; no intro, no logo, no «hola». 2) The first minute "
               "decides the video: stakes, rules and the goal are clear by second 20, and something big "
               "happens before minute 1. 3) Always progressing: every scene is bigger or harder than the "
               "last; a counter, timer or progress bar makes progress visible. 4) Re-engage at ~1:00, "
               "~3:00 and ~6:00 with a new twist, a reveal or a raised stake; never two calm minutes. "
               "5) One WOW moment per section that people would describe to a friend. 6) Cut every "
               "~1 s, a new visual every sentence, zoom punches on key words, arrows, circles and "
               "callouts on what matters, a sound on every cut, captions word by word. 7) After the "
               "payoff, end within seconds."),
        skills={
            "guion": ("viral-youtube-hook (MrBeast)", "kallaway-storytelling", "YouTube retention editing"),
            "motion": ("kinetic-cut-video", "motion-design", "video-typography"),
        },
    ),
    "explicado3d": Genre(
        "explicado3d", "Explicado en 3D (dato sorprendente)", "explicado-3d",
        ("que pasaria si", "que pasa si", "por dentro", "como funciona el cuerpo", "dato curioso",
         "sabias que", "explicado en 3d", "animacion 3d", "zack", "zack d", "cuerpo humano",
         "lo que pasa dentro", "rayos x", "3d explicado"),
        "3D render, stylized realistic, clean studio light, cross-section", 0.0,
        sources=("3d", "ai", "image", "stock", "library", "archive", "web"),
        notes=("3D EXPLAINER of one surprising fact (the short 3D-animation format of the big "
               "explainer channels, in our words): 1) Hook in the first second with the surprising "
               "claim or a POV («this is what happens to your body when…»), shown, not told. 2) One "
               "idea only, 30-60 s for a short: hook → the mechanism shown step by step → the "
               "consequence → a last surprising line that loops to the start. 3) SHOW THE INSIDE: "
               "cross-sections, x-ray views and cutaways of the body, the machine or the object; "
               "callout labels name each part as it appears. 4) Clean stylized-realistic 3D: one "
               "character or object, simple materials, soft studio light, a slow push-in on every "
               "shot and slow motion at the key moment. 5) Calm, clear narration, short sentences; "
               "a precise sound effect for every action (crack, squish, click); captions word by "
               "word. 6) No stock footage of people talking, no cards: every shot is the thing "
               "itself."),
        skills={
            "guion": ("explainer script-director", "youtube-shorts", "storytelling (OpenMontage)"),
            "motion": ("blender-mcp", "blender-animation", "motion-design"),
        },
    ),
    "corto3d": Genre(
        "corto3d", "Corto 3D con personajes", "corto-3d",
        ("corto 3d", "historia 3d", "personaje 3d", "cortometraje animado", "pixar", "historia animada 3d"),
        "cinematic 3D animation, stylized realistic characters", 0.0,
        sources=("3d", "ai", "image"),
        notes=("3D SHORT WITH CHARACTERS: a mystery or a power in the first shot, a character we "
               "understand in 5 s, escalation of funnier or bigger uses, it goes wrong, climax, a "
               "twist ending. Close-ups on faces and the key object; tracking, dolly and crane moves; "
               "one signature visual effect that comes back with its own sound."),
        skills={
            "guion": ("storytelling-video", "screenwriting-video", "youtube-shorts"),
            "motion": ("blender-animation", "blender-mcp", "motion-doctrine"),
        },
    ),
    "documental": Genre(
        "documental", "Documental / explicativo", "metas-grandes",
        ("documental", "explica", "explicacion", "como funciona", "historia de", "por que", "ciencia",
         "datos", "investigacion", "misterio", "caso"),
        "documentary footage, archival, real", 0.3,
        sources=("archive", "stock", "web", "film", "library", "image", "ai"),
        notes="Documentary: real footage and archive, dates and places on screen, maps and numbers as motion graphics.",
        skills={
            "guion": ("educational-video-creator", "storytelling (OpenMontage)", "youtube-scriptwriting"),
            "motion": ("manim motion-graphics", "video-typography", "motion-design"),
        },
    ),
}  # fmt: skip


def _plain(text: str) -> str:
    text = (
        unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9 ]+", " ", text)


def detect(brief: str) -> str:
    """The genre the brief asks for ("" when nothing points anywhere)."""
    words = f" {_plain(brief)} "
    best, score = "", 0
    for g in GENRES.values():
        hits = sum(2 if " " in w else 1 for w in g.words if f" {w} " in words)
        if hits > score:
            best, score = g.key, hits
    return best


def for_style(style_key: str) -> str:
    for g in GENRES.values():
        if g.style == style_key:
            return g.key
    return ""


def search_words(genre: str) -> str:
    g = GENRES.get(genre)
    return g.search if g else ""


# -- the motion-graphics pass ----------------------------------------------------------------

_NUM = re.compile(
    r"(?<![\w$])\$?\d[\d.,]*(?:\s*(?:%|k\b|m\b|mil\b|millones\b|dolares\b|dólares\b|días\b|dias\b|horas\b|kg\b))?(?![\w])",
    re.I,
)


def finish(shots: Sequence, words: Sequence, genre: str) -> int:
    """Dress the plan for its genre; returns how many shots it changed.

    * pesada: every cut gets a transition and a sound, key words a zoom
      punch, numbers a counter, goals a progress bar, highlights a circle,
      and every few shots an arrow to what matters.
    * cine: letterbox, slow fades, few words, natural or cold grade.
    * animacion: no archive frames or TV borders on drawings.
    Only what the editor left at its default is changed.
    """
    changed = 0
    if genre == "pesada":
        touched = set()
        for i, s in enumerate(shots):
            spoken = " ".join(w.text for w in words[s.first : s.last])
            before = (s.transition, s.effect, s.sfx, s.overlay)
            if s.transition == "cut":
                s.transition = ("whip", "flash", "cut")[i % 3]
            if s.effect == "none":
                s.effect = "punch" if s.highlight or i % 2 == 0 else "shake"
            if s.sfx == "none":
                s.sfx = ("whoosh", "pop", "impact")[i % 3]
            if not s.overlay:
                m = _NUM.search(spoken)
                if m and any(c.isdigit() for c in m.group(0)):
                    s.overlay = m.group(0).strip()[:24]
                elif s.highlight and i % 3 == 1:
                    s.overlay = "circle"
                elif i % 4 == 3:
                    s.overlay = f"arrow:{(s.highlight or '').upper()[:14]}".rstrip(":")
                elif s.highlight and i % 6 == 5:
                    s.overlay = "spot"  # the rest of the frame dims on what matters
            if (s.transition, s.effect, s.sfx, s.overlay) != before:
                touched.add(i)
        for i, s in enumerate(shots):  # a progress bar every ~20 s of video
            if i and i % 15 == 0 and not s.overlay:
                s.overlay = f"bar:{min(95, round(100 * i / max(1, len(shots))))}"
                touched.add(i)
        changed = len(touched)
    elif genre == "cine":
        for i, s in enumerate(shots):
            before = (s.frame, s.transition, s.text_style, s.grade)
            if s.frame == "none":
                s.frame = "letterbox"
            if s.transition == "cut" and i % 4 == 0:
                s.transition = "fade"
            if s.kind != "card" and s.text_style != "none" and i % 3:
                s.text_style = "none"  # a film breathes: words only now and then
            if s.grade == "natural":
                s.grade = "cold" if i % 2 else "warm"
            if (s.frame, s.transition, s.text_style, s.grade) != before:
                changed += 1
    elif genre in ("explicado3d", "corto3d"):
        inside = re.compile(
            r"\b(dentro|interior|por dentro|huesos?|organos?|órganos?|sangre|"
            r"cerebro|coraz[oó]n|pulm[oó]n|motor|piezas?|capas?|c[eé]lulas?)\b",
            re.I,
        )
        for i, s in enumerate(shots):
            spoken = " ".join(w.text for w in words[s.first : s.last])
            before = (s.effect, s.sfx, s.overlay, s.text_style)
            if s.effect == "none":
                s.effect = "push"  # every 3D shot creeps in
            if genre == "explicado3d":
                if s.sfx == "none" and i % 2 == 0:
                    s.sfx = ("click", "impact", "pop")[i % 3]
                if not s.overlay:
                    part = inside.search(spoken)
                    if part:
                        name = (s.highlight or part.group(0)).upper()[:18]
                        s.overlay = "xray" if i % 3 == 0 else f"callout:{name}"
                    elif s.highlight and i % 3 == 1:
                        s.overlay = f"callout:{s.highlight.upper()[:18]}"
            elif s.kind != "card" and s.text_style != "none" and i % 2:
                s.text_style = "none"  # a story breathes
            if (s.effect, s.sfx, s.overlay, s.text_style) != before:
                changed += 1
    elif genre == "animacion":
        for s in shots:
            if s.frame in ("crt", "film") or s.grade == "bw":
                s.frame, s.grade = "none", "natural"
                changed += 1
    return changed


def skill_names(genre: str, kind: str) -> Tuple[str, ...]:
    """The genre's own skills for a stage («guion» or «motion»)."""
    g = GENRES.get(genre)
    return tuple(g.skills.get(kind, ())) if g else ()


def notes(genre: str) -> str:
    g = GENRES.get(genre)
    return f"GENRE: {g.name}. {g.notes}" if g else ""


def sources(genre: str, allowed: List[str]) -> List[str]:
    """The allowed sources in the genre's order (the rest after)."""
    g = GENRES.get(genre)
    if not g or not g.sources:
        return list(allowed)
    first = [s for s in g.sources if s in allowed]
    return first + [s for s in allowed if s not in first]


__all__ = [
    "GENRES",
    "Genre",
    "detect",
    "finish",
    "for_style",
    "notes",
    "search_words",
    "skill_names",
    "sources",
]

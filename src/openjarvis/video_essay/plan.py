"""The plan of a video essay: words with their times, and shots built on them.

Every shot is a run of spoken words (a cut never falls inside a word), and
what shows on screen is those words appearing as they are said. The model
proposes the shots; the code here makes them valid and keeps them inside the
style's rhythm (no shot shorter or longer than the reference allows).
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

KINDS = ("card", "broll", "archive", "device")
CARDS = ("cream", "red", "navy", "black")
TEXT_STYLES = ("pop", "grey_to_white", "big_caps", "italic", "none")
POSITIONS = (
    "center",
    "lower",
    "upper",
    "left",
    "right",
    "upper_left",
    "upper_right",
    "lower_left",
    "lower_right",
)
# the typefaces of typo.FACES ("" lets the text style choose, as before)
FONTS = ("", "base", "impacto", "pesada", "elegante", "tecnica", "mano")
EFFECTS = ("none", "punch", "push", "shake", "glitch", "parallax")
GRADES = ("natural", "bw", "warm", "cold")
FRAMES = ("none", "crt", "film", "letterbox")
DEVICES = ("none", "computer", "phone")
TRANSITIONS = ("cut", "flash", "whip", "fade")
SFX = (
    "none",
    "whoosh",
    "click",
    "impact",
    "typewriter",
    "riser",
    "pop",
    "sizzle",
    "ding",
)
# where a shot's picture comes from ("auto": the first that has one)
SOURCES = ("auto", "library", "stock", "web", "film", "archive", "ai", "3d", "image")


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Shot:
    first: int  # index of its first word
    last: int  # index after its last word
    kind: str = "broll"
    card: str = "black"
    visual: str = ""  # what to show (English, for search or generation)
    text: str = ""  # on-screen words (the spoken ones by default)
    highlight: str = ""
    text_style: str = "pop"
    position: str = "center"
    effect: str = "none"
    grade: str = "natural"
    frame: str = "none"
    device: str = "none"
    transition: str = "cut"
    sfx: str = "none"
    start: float = 0.0
    end: float = 0.0
    asset: str = ""  # file chosen for it (filled by assets.py)
    notes: List[str] = field(default_factory=list)
    source: str = "auto"
    overlay: str = ""  # a counter or stamp on top ("DÍA 1", "$1.000.000")
    camera: str = ""  # camera direction for AI and 3D shots
    font: str = ""  # a face of typo.FACES ("" = by text_style)
    accent: str = ""  # highlight colour, "#RRGGBB" (colour theory, color.py)
    # words on blocks of colour: "word" (the highlight on the accent, the
    # reference's «white on red»), "all" (every word: picture too busy or
    # too bright for white), "" none
    box: str = ""
    # colour match to the rest of the video: per channel (gain, offset) for
    # red, green and blue (color.unify); empty = as shot
    tone: List[float] = field(default_factory=list)
    # an exact search for its picture («Rocky 1976 training montage scene»):
    # a scene of a named film or series chosen for this moment (films.py)
    search: str = ""

    @property
    def dur(self) -> float:
        return max(0.0, self.end - self.start)


def _pick(value: Any, allowed: tuple, default: str) -> str:
    value = str(value or "").strip().lower()
    return value if value in allowed else default


def _box(value: Any) -> str:
    if value is True:
        return "word"
    value = str(value or "").strip().lower()
    return value if value in ("word", "all") else ""


def _hex(value: Any) -> str:
    text = str(value or "").strip()
    return text.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", text) else ""


# -- word timings ------------------------------------------------------------------


def estimate_words(text: str, voiced: List[tuple], total: float) -> List[Word]:
    """Word times without a recogniser: words spread over the voiced parts of
    the narration (*voiced*: [(start, end)] from the audio's energy), each in
    proportion to its length."""
    words = text.split()
    if not words:
        return []
    spans = [(a, b) for a, b in voiced if b > a] or [(0.0, max(total, 0.1))]
    span_total = sum(b - a for a, b in spans)
    weights = [len(re.sub(r"\W", "", w)) + 1.5 for w in words]
    scale = span_total / sum(weights)

    def at(x: float, *, ending: bool = False) -> float:
        """Position *x* along the voiced time -> seconds in the narration."""
        for a, b in spans:
            room = b - a
            if x < room or (ending and x <= room + 1e-9):
                return a + x
            x -= room
        return spans[-1][1]

    out: List[Word] = []
    done = 0.0
    for w, wt in zip(words, weights):
        start = at(done * scale)
        done += wt
        end = at(done * scale, ending=True)
        out.append(Word(w, round(start, 3), round(max(end, start + 0.05), 3)))
    return out


# -- shots -------------------------------------------------------------------------


def _items(raw: Any) -> List[Any]:
    data = json.loads(raw) if isinstance(raw, str) else raw
    items = data.get("shots", data) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


def pace(style: Dict[str, Any]) -> Dict[str, float]:
    """The shortest and longest shot the style allows (the reference holds a
    shot about two and a half times its median at most)."""
    median = float(style.get("median_shot_s") or 1.6)
    return {
        "min_s": max(0.35, min(0.6, float(style.get("min_shot_s") or 0.45))),
        "max_s": max(2.5, min(6.0, median * 2.4)),
    }


def from_model(raw: Any, words: List[Word], **limits: float) -> List[Shot]:
    """The model's shots ({"from": i, "to": j, ...}) as valid Shot objects."""
    shots: List[Shot] = []
    for item in _items(raw):
        try:
            first, last = int(item["from"]), int(item["to"])
        except (KeyError, TypeError, ValueError):
            continue
        shots.append(
            Shot(
                first=first,
                last=last,
                kind=_pick(item.get("kind"), KINDS, "broll"),
                card=_pick(item.get("card"), CARDS, "black"),
                visual=str(item.get("visual") or "")[:400],
                text=str(item.get("text") or "")[:200],
                highlight=str(item.get("highlight") or "")[:40],
                text_style=_pick(item.get("text_style"), TEXT_STYLES, "pop"),
                position=_pick(item.get("position"), POSITIONS, "center"),
                effect=_pick(item.get("effect"), EFFECTS, "none"),
                grade=_pick(item.get("grade"), GRADES, "natural"),
                frame=_pick(item.get("frame"), FRAMES, "none"),
                device=_pick(item.get("device"), DEVICES, "none"),
                transition=_pick(item.get("transition"), TRANSITIONS, "cut"),
                sfx=_pick(item.get("sfx"), SFX, "none"),
                source=_pick(item.get("source"), SOURCES, "auto"),
                overlay=str(item.get("overlay") or "")[:24],
                camera=str(item.get("camera") or "")[:160],
                font=_pick(item.get("font"), FONTS, ""),
                accent=_hex(item.get("accent")),
                box=_box(item.get("box")),
            )
        )
    if not shots:
        raise ValueError("el modelo no propuso tomas")
    return normalise(shots, words, **limits)


def normalise(
    shots: List[Shot],
    words: List[Word],
    *,
    min_s: float = 0.45,
    max_s: float = 6.0,
    end_pad: float = 0.35,
) -> List[Shot]:
    """Shots that cover every word once, in order, cut between words, within
    the style's lengths (short ones merged, long ones split)."""
    n = len(words)
    if not n:
        return []
    shots = sorted((s for s in shots if 0 <= s.first < s.last), key=lambda s: s.first)
    fixed: List[Shot] = []
    nxt = 0
    for s in shots:
        if s.first > nxt:  # a gap the model skipped: give it its own shot
            fixed.append(Shot(first=nxt, last=s.first))
        s.first = max(s.first, nxt)
        s.last = min(max(s.last, s.first + 1), n)
        if s.first >= n:
            break
        if s.first < s.last:
            fixed.append(s)
            nxt = s.last
    if nxt < n:
        fixed.append(Shot(first=nxt, last=n))
    # split the long ones at the word closest to their middle
    out: List[Shot] = []
    for s in fixed:
        out.extend(_split(s, words, max_s))
    # merge the too-short ones into their neighbour
    merged: List[Shot] = []
    for s in out:
        _times(s, words)
        if merged and s.dur < min_s and merged[-1].dur + s.dur <= max_s:
            prev = merged[-1]
            prev.last = s.last
            _times(prev, words)
            continue
        merged.append(s)
    for i, s in enumerate(merged):  # no gaps: each shot lasts until the next
        s.start = words[s.first].start if i else 0.0
        s.end = (
            words[merged[i + 1].first].start
            if i + 1 < len(merged)
            else words[-1].end + end_pad
        )
        spoken = " ".join(w.text for w in words[s.first : s.last])
        if not s.text.strip() or not _same_words(s.text, spoken):
            s.text = spoken
    return merged


def _norm(text: str) -> List[str]:
    return [w for w in re.sub(r"[^\w\s]", " ", text.lower()).split() if w]


def _same_words(shown: str, spoken: str) -> bool:
    """On-screen text may drop words or change case, never add new ones."""
    said = set(_norm(spoken))
    return bool(_norm(shown)) and all(w in said for w in _norm(shown))


def _times(s: Shot, words: List[Word]) -> None:
    s.start, s.end = words[s.first].start, words[s.last - 1].end


def _split(s: Shot, words: List[Word], max_s: float) -> List[Shot]:
    _times(s, words)
    if s.dur <= max_s or s.last - s.first < 2:
        return [s]
    mid = (s.start + s.end) / 2
    cut = min(range(s.first + 1, s.last), key=lambda i: abs(words[i].start - mid))
    a = Shot(**{**asdict(s), "last": cut, "text": ""})
    b = Shot(**{**asdict(s), "first": cut, "text": "", "transition": "cut"})
    return _split(a, words, max_s) + _split(b, words, max_s)


def fallback(
    words: List[Word], style: Dict[str, Any], sources: Optional[List[str]] = None
) -> List[Shot]:
    """A plan without the model: phrases cut at punctuation and every few
    words, alternating cards and pictures in the style's proportions."""
    target = float(style.get("median_shot_s") or 1.6)
    shots: List[Shot] = []
    first = 0
    for i, w in enumerate(words):
        long_enough = words[i].end - words[first].start >= target
        if re.search(r"[.,;:!?]$", w.text) or long_enough or i == len(words) - 1:
            shots.append(Shot(first=first, last=i + 1))
            first = i + 1
    mix = style.get("mix") or {"card": 0.2, "broll": 0.5, "archive": 0.2, "device": 0.1}
    card_every = max(2, round(1 / max(0.05, float(mix.get("card", 0.2)))))
    for i, s in enumerate(shots):
        spoken = " ".join(w.text for w in words[s.first : s.last])
        if i % card_every == 0:
            s.kind, s.card = "card", CARDS[(i // card_every) % len(CARDS)]
            s.text_style = "big_caps" if len(spoken.split()) <= 3 else "pop"
        else:
            s.kind = "archive" if i % 5 == 2 else "broll"
            s.visual = spoken
            if s.kind == "archive":
                s.grade, s.frame = "bw", "crt"
            s.effect = "punch" if i % 3 == 0 else "push"
        s.sfx = "whoosh" if s.kind == "card" else "none"
    film = style.get("production") in ("3d", "ai", "animation")
    for s in shots:
        if film and s.kind == "card":  # a film, not an essay: no cards in it
            s.kind = "broll"
            s.visual = " ".join(w.text for w in words[s.first : s.last])
        if s.kind != "card" and sources:
            s.source = sources[0] if sources[0] in SOURCES else "auto"
        if style.get("narration_mode") in ("none", "song") and s.kind != "card":
            s.text_style = "none"
    return normalise(shots, words, **pace(style))


FILM_SHARE = 0.4  # of the pictures, scenes of films and series (owner, 28 Oct 2026)


def add_film(
    shots: List[Shot], share: float = FILM_SHARE, allowed: Sequence[str] = ()
) -> int:
    """Turn about *share* of the picture shots into scenes of films and series,
    spread evenly (never two in a row), when the editor left them to chance.
    A shot the editor chose a source for (library, stock, 3d, ai…) stays.
    Returns how many it changed."""
    if allowed and "film" not in allowed:
        return 0
    free = [
        s
        for s in shots
        if s.kind in ("broll", "archive") and s.source in ("", "auto", "web", "stock")
    ]
    want = round(len([s for s in shots if s.kind != "card"]) * share)
    have = sum(1 for s in shots if s.source == "film")
    if want <= have or not free:
        return 0
    step = max(2, round(len(free) / max(1, want - have)))
    done = 0
    for i, s in enumerate(free):
        if i % step == step - 1 and done < want - have:
            s.source, s.grade = "film", (s.grade if s.grade != "bw" else "natural")
            done += 1
    return done


PLAN_PROMPT = """You are a top video essay editor. Plan the edit of this narration \
to the level of the reference style below: a cut every ~{median}s on average, \
text on screen in every shot (the spoken words appearing as they are said), \
cards, archive-looking shots, device mock-ups, b-roll that SHOWS each idea \
literally or as a strong visual metaphor.

REFERENCE STYLE:
{style}

NARRATION, word by word with their index:
{words}

Answer ONLY JSON: {{"shots": [{{"from": first word index, "to": index after the last word,
"kind": "card|broll|archive|device", "card": "cream|red|navy|black (cards only)",
"visual": "for non-cards: one concrete, filmable picture in English (subject, place, light, camera)",
"text": "the words to show (a subset of the spoken ones, in order)",
"highlight": "one word to emphasise or empty",
"text_style": "pop|grey_to_white|big_caps|italic",
"position": "center|lower|upper|left|right|upper_left|upper_right|lower_left|lower_right",
"font": "impacto (1-3 punch words)|base|pesada (short label)|elegante (quote, feeling)|
tecnica (numbers, data)|mano (an aside) or empty",
"accent": "#RRGGBB highlight colour that goes with the picture, or empty",
"box": "word" (the highlight on a block of the accent colour) | "all" (every word on blocks) | "",
"effect": "none|punch|push|shake|glitch", "grade": "natural|bw|warm|cold",
"frame": "none|crt|film", "device": "none|computer|phone",
"transition": "cut|flash|whip|fade", "sfx": "none|whoosh|click|impact|typewriter|riser|pop|sizzle|ding",
"source": "where the picture comes from: {sources} (film: a scene of a movie or series that shows the idea)",
"overlay": "optional counter or stamp shown on top, max 3 words (e.g. DAY 1, $1,000,000) or empty",
"camera": "for ai/3d shots: lens and move (e.g. 35mm slow dolly-in, low angle)"}}]}}
Rules: cover every word exactly once and in order; cut only between words; \
short punchy words (1-3) on cards; problems and the past in bw with a crt or \
film frame; the payoff in natural colour; the last shot a red-on-cream card. \
Use only the sources listed; text_style "none" when the style shows no text. \
Move the words around the frame (thirds, never over a face) and vary the \
typeface by what the words are, as a motion designer would. Pictures are REAL \
footage: clips from the web, scenes of films and series, stock and archive \
(source web|film|stock|archive); an AI-made picture only when nothing real \
could ever show it.
{extra}"""


SEGMENT_WORDS = 220  # a long narration is planned in stretches this size


def segments(words: List[Word], size: int = SEGMENT_WORDS) -> List[tuple]:
    """(start, end) word ranges of about *size* words, cut after a sentence."""
    out: List[tuple] = []
    start, n = 0, len(words)
    while start < n:
        end = min(n, start + size)
        if end < n:
            for k in range(end, start + int(size * 0.6), -1):
                if re.search(r"[.!?…]$", words[k - 1].text):
                    end = k
                    break
            if n - end < size * 0.3:  # no tiny last stretch
                end = n
        out.append((start, end))
        start = end
    return out


def plan_shots(
    words: List[Word],
    style: Dict[str, Any],
    ask: Optional[Callable[..., str]] = None,
    *,
    sources: Optional[List[str]] = None,
    extra: str = "",
) -> List[Shot]:
    """Shots from the model (checked); the fallback plan where it fails.

    A long narration goes to the editor in stretches of ~220 words (a model
    asked for 300 shots at once gets lazy and repetitive); each stretch sees
    how the one before ended, so places, characters and motif carry on."""
    if not words:
        return []
    if ask is None:
        return fallback(words, style, sources)
    style_json = json.dumps(
        {
            k: style.get(k)
            for k in (
                "mix",
                "palette",
                "effects",
                "structure",
                "grade",
                "look",
                "overlays",
            )
        },
        ensure_ascii=False,
    )
    median = float(style.get("median_shot_s") or 1.6)
    items: List[Dict[str, Any]] = []
    context = ""
    for a, b in segments(words):
        seg = words[a:b]
        prompt = PLAN_PROMPT.format(
            median=style.get("median_shot_s", 1.6),
            style=style_json,
            words=" ".join(f"{i}:{w.text}" for i, w in enumerate(seg, a)),
            sources="|".join(sources or ["auto"]),
            extra=extra + context,
        )
        span = seg[-1].end - seg[0].start
        # models plan lazily (one shot every 5-6 s) unless told the count
        prompt += (
            f"\nThis stretch lasts {span:.0f} seconds: plan about {max(2, round(span / median))} shots "
            f"(one every ~{median:g} s, as the style cuts), each with its own picture."
        )
        got: List[Dict[str, Any]] = []
        try:
            for item in _items(ask(prompt)):
                try:
                    first, last = int(item["from"]), int(item["to"])
                except (KeyError, TypeError, ValueError):
                    continue
                if a <= first < last <= b:
                    got.append(item)
            # a plan far slower than the style is not the style (counted
            # before long shots are split, which would hide it); a bit slow
            # is kept: its pictures are worth far more than the fallback's
            wanted = max(2, math.ceil(span / (median * 2)))
            if len(got) < wanted * 0.5:
                log.warning(
                    "plan stretch %d-%d: %d shots, %d wanted", a, b, len(got), wanted
                )
                got = []
        except Exception as exc:  # noqa: BLE001 — the fallback still cuts it well
            log.warning("plan stretch %d-%d failed: %s", a, b, exc)
            got = []
        if not got:
            for s in fallback(seg, style, sources):
                got.append({**asdict(s), "from": s.first + a, "to": s.last + a})
        items += got
        last_visuals = [str(i.get("visual") or "") for i in got[-3:] if i.get("visual")]
        context = (
            "\nThe stretch before ended with these shots; keep the same world "
            "(places, characters, motif) and do not repeat a picture: "
            + "; ".join(last_visuals)
            if last_visuals
            else ""
        )
    return from_model({"shots": items}, words, **pace(style))


def to_json(shots: List[Shot]) -> List[Dict[str, Any]]:
    return [asdict(s) for s in shots]


def from_json(items: List[Dict[str, Any]]) -> List[Shot]:
    known = set(Shot.__dataclass_fields__)
    return [Shot(**{k: v for k, v in item.items() if k in known}) for item in items]


__all__ = [
    "PLAN_PROMPT",
    "SOURCES",
    "Shot",
    "Word",
    "estimate_words",
    "fallback",
    "from_json",
    "from_model",
    "normalise",
    "pace",
    "plan_shots",
    "segments",
    "to_json",
]

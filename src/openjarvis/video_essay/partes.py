"""A video made in parts, each one worked until it is interesting.

The owner (4 Nov 2026): «que Sergio le ponga más esfuerzo a los videos y que
en verdad sean más interesantes, que divida la creación de videos por
partes». The director writes the whole script in one go, and one go leaves
the usual faults: a hook that explains instead of grabbing, stretches with
nothing new, the same sentence rhythm for a minute, stock phrases («en este
video…», «hoy en día…»).

What this does, after the director's treatment and before the voice:

1. **Splits** the script into parts (the hook, the development in one or
   more parts, the payoff) at the director's own beats.
2. **Measures** each part with plain rules (no model): hook strength, stretches
   without a concrete fact, stock phrases, rhythm, open loops. The measures are
   the same every time, so they can be tested and so Sergio can say what he
   found.
3. **Rewrites only the weak parts**, one at a time, with the neighbours in
   view (so it still flows), and keeps a rewrite **only if its measured score
   rises** and the length stays close. A model that makes it worse changes
   nothing.

The effort follows the mode (Test none, Basic one pass, Post two, Absolut
Cinema three) and every call counts against the job's budget. Nothing here
invents a fact: the rewrite is told to keep every name, number and claim
that is in the part.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# Stock phrases that make a script sound written by a machine.
STOCK = (
    "en este video", "en este vídeo", "hoy vamos a", "hoy en día", "en el mundo de hoy",
    "sin duda alguna", "como todos sabemos", "es importante destacar", "en conclusión",
    "no es ningún secreto", "en la era de", "te has preguntado alguna vez",
    "alguna vez te has preguntado", "sumérgete", "sumergirnos", "descubre cómo",
    "in this video", "today we are going to", "in today's world", "it is important to note",
    "in conclusion", "have you ever wondered", "let's dive",
)  # fmt: skip
HOOK_WORDS = (
    "nadie", "jamás", "nunca", "secreto", "error", "verdad", "mentira", "peor", "mejor",
    "único", "pero", "hasta que", "dejó", "perdió", "ganó", "descubrió",
    "nobody", "never", "secret", "mistake", "truth", "lie", "worst", "best", "only",
    "but", "until", "lost", "won", "found",
)  # fmt: skip
LOOP_WORDS = (
    "pero", "hasta que", "más adelante", "luego verás", "y entonces", "lo que pasó",
    "pero antes", "la razón", "but", "until", "later", "and then", "what happened", "the reason",
)  # fmt: skip
MAX_HOOK_WORDS = 16
MAX_DRY_RUN = 3  # sentences in a row with nothing concrete
MAX_SENTENCE_WORDS = 28
WEAK_BELOW = 72  # a part scoring under this is rewritten
KEEP_LENGTH = (0.75, 1.3)  # a rewrite stays within this share of the words
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_NAME = re.compile(r"(?<![.!?¿¡]\s)(?<!^)\b[A-ZÁÉÍÓÚÑ][\wáéíóúñ]{2,}")


@dataclass
class Part:
    name: str
    beats: List[int]  # indices into script["beats"]
    words: int = 0
    score: int = 0
    problems: List[str] = field(default_factory=list)


def sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE.split(text or "") if s.strip()]


def concrete(sentence: str) -> bool:
    """Has something a viewer can hold on to: a number, a quote or a name."""
    return bool(
        re.search(r"\d", sentence)
        or '"' in sentence
        or "«" in sentence
        or _NAME.search(sentence)
    )


def hook_problems(text: str) -> List[str]:
    first = (sentences(text) or [""])[0]
    low = first.lower()
    out = []
    if len(first.split()) > MAX_HOOK_WORDS:
        out.append(
            f"el gancho tiene {len(first.split())} palabras: debe caber en un aliento"
        )
    if not (
        concrete(first)
        or "?" in first
        or "¿" in first
        or any(w in low for w in HOOK_WORDS)
    ):
        out.append("el gancho no promete nada concreto ni abre una duda")
    return out


def part_problems(text: str, hook: bool = False) -> List[str]:
    """What is weak in *text*, in plain words (empty when it is fine)."""
    out: List[str] = hook_problems(text) if hook else []
    sents = sentences(text)
    low = (text or "").lower()
    found = [p for p in STOCK if p in low]
    if found:
        out.append("frases de relleno: «" + "», «".join(found[:3]) + "»")
    run = worst = 0
    for s in sents:
        run = 0 if concrete(s) else run + 1
        worst = max(worst, run)
    if worst > MAX_DRY_RUN:
        out.append(f"{worst} frases seguidas sin un dato, número, nombre o cita")
    lengths = [len(s.split()) for s in sents]
    if lengths and max(lengths) > MAX_SENTENCE_WORDS:
        out.append(f"una frase de {max(lengths)} palabras: córtela")
    if len(lengths) >= 4:
        mean = sum(lengths) / len(lengths)
        spread = (sum((n - mean) ** 2 for n in lengths) / len(lengths)) ** 0.5
        if spread < 0.25 * mean:
            out.append(
                "todas las frases miden casi lo mismo: falta ritmo (mezcle cortas y largas)"
            )
    if len(sents) >= 5 and not any(w in low for w in LOOP_WORDS) and "?" not in low:
        out.append("no abre ninguna duda que se cierre después")
    return out


def score(text: str, hook: bool = False) -> int:
    """0-100: 100 minus what the rules find (the same text always scores the same)."""
    weight = {
        "gancho": 22,
        "frases de relleno": 12,
        "seguidas": 14,
        "palabras: córtela": 8,
    }
    total = 100
    for p in part_problems(text, hook):
        total -= next((v for k, v in weight.items() if k in p), 10)
    return max(0, total)


def split(sc: Dict[str, Any], seconds: float = 0.0) -> List[Part]:
    """The parts of the script: the first beat(s) up to ~12 words are the hook
    part; the rest is cut at the director's beats into parts of about 220
    words (a chapter in a long video); the last beat stands as the payoff."""
    beats = sc.get("beats") or []
    if not beats:
        return []
    counts = [len(str(b.get("text") or "").split()) for b in beats]
    target = 220 if seconds >= 150 else max(60, round(sum(counts) / 3))
    parts: List[Part] = [Part("Gancho", [0], counts[0])]
    body: List[int] = []
    body_words = 0
    for i in range(1, len(beats) - (1 if len(beats) > 2 else 0)):
        body.append(i)
        body_words += counts[i]
        if body_words >= target:
            parts.append(Part(f"Desarrollo {len(parts)}", body, body_words))
            body, body_words = [], 0
    if body:
        if parts and len(parts) > 1 and body_words < target * 0.4:
            parts[-1].beats += body
            parts[-1].words += body_words
        else:
            parts.append(Part(f"Desarrollo {len(parts)}", body, body_words))
    if len(beats) > 2:
        parts.append(Part("Remate", [len(beats) - 1], counts[-1]))
    return parts


def _text(sc: Dict[str, Any], part: Part) -> str:
    return " ".join(str(sc["beats"][i].get("text") or "") for i in part.beats)


def measure(sc: Dict[str, Any], seconds: float = 0.0) -> List[Part]:
    parts = split(sc, seconds)
    for k, part in enumerate(parts):
        text = _text(sc, part)
        part.problems = part_problems(text, hook=(k == 0))
        part.score = score(text, hook=(k == 0))
    return parts


def overall(parts: List[Part]) -> int:
    total = sum(max(1, p.words) for p in parts)
    return round(sum(p.score * max(1, p.words) for p in parts) / total) if total else 0


REWRITE = """You are the script doctor of a video studio. Rewrite ONE part of a video script
so a stranger keeps watching. Language: {language}.

Part: «{name}» ({words} words, spoken in about {seconds:.0f} seconds).
{role}

What is weak in it (fix exactly this):
{problems}

Before it: {before}
After it: {after}

Rules:
- Keep EVERY name, number, date and claim that is in the part; invent nothing.
  If it lacks a concrete fact, make the point sharper with what is already there.
- The same number of beats ({count}), the same order, about the same length
  ({low}-{high} words in total).
- Spoken language: short sentences mixed with a longer one, one idea each.
  No stock phrases («en este video», «hoy en día», «descubre cómo»).
- Keep each beat's job (its «beat» label) and open the next one with a reason
  to keep listening.

The part, as JSON beats:
{beats}

Answer ONLY JSON: {{"beats": [{{"text": "..."}}]}} with exactly {count} beats."""

ROLE = {
    "Gancho": (
        "This is the HOOK: the first sentence must fit in one breath (at most "
        f"{MAX_HOOK_WORDS} words) and promise something concrete or open a question "
        "the viewer needs answered. Never start by explaining the topic."
    ),
    "Remate": (
        "This is the PAYOFF: close the loop the video opened, land one clear "
        "line the viewer will remember, and end on it."
    ),
}


def _validate(text: str, count: int) -> List[str]:
    data = json.loads(text)
    beats = data.get("beats") if isinstance(data, dict) else None
    if not isinstance(beats, list) or len(beats) != count:
        raise ValueError("número de partes distinto")
    out = [" ".join(str((b or {}).get("text") or "").split()) for b in beats]
    if any(not t for t in out):
        raise ValueError("una parte vacía")
    return out


def _anchors(text: str) -> Tuple[Counter, Counter]:
    """Conservative integrity check, not a fact-check of the claims themselves.

    A rewrite cannot add/remove numerical facts or names found by the existing
    detector. Keeping anchors is necessary, but does not prove semantic truth.
    """
    numbers = Counter(re.findall(r"\b\d+(?:[.,:/-]\d+)*\b", text))
    names = Counter(n.casefold() for n in _NAME.findall(text))
    return numbers, names


def improve(
    sc: Dict[str, Any],
    ask: Callable[..., str],
    *,
    passes: int,
    seconds: float = 60.0,
    language: str = "Spanish",
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """The script with its weak parts rewritten (a new dict; the input is not
    touched) and a report: {"before", "after", "parts": [...], "rewritten"}."""
    out = json.loads(json.dumps(sc))
    parts = measure(out, seconds)
    before = overall(parts)
    report: Dict[str, Any] = {
        "before": before,
        "after": before,
        "rewritten": 0,
        "rejected_facts": 0,
        "parts": [],
    }
    for _ in range(min(3, max(0, passes))):
        weak = [p for p in measure(out, seconds) if p.score < WEAK_BELOW and p.problems]
        if not weak:
            break
        for part in weak:
            k = weak.index(part)
            if progress:
                progress(k + 1, len(weak), part.name)
            current = measure(out, seconds)
            here = next((p for p in current if p.beats == part.beats), None)
            if here is None or here.score >= WEAK_BELOW:
                continue
            idx = current.index(here)
            before_txt = (
                _text(out, current[idx - 1])[-400:] if idx else "(it opens the video)"
            )
            after_txt = (
                _text(out, current[idx + 1])[:400]
                if idx + 1 < len(current)
                else "(it ends the video)"
            )
            prompt = REWRITE.format(
                language=language,
                name=here.name,
                words=here.words,
                seconds=here.words / 1.9,
                role=ROLE.get(here.name, ""),
                problems="\n".join(f"- {p}" for p in here.problems),
                before=before_txt,
                after=after_txt,
                count=len(here.beats),
                low=round(here.words * KEEP_LENGTH[0]),
                high=round(here.words * KEEP_LENGTH[1]),
                beats=json.dumps(
                    [
                        {
                            "beat": out["beats"][i].get("beat"),
                            "text": out["beats"][i]["text"],
                        }
                        for i in here.beats
                    ],
                    ensure_ascii=False,
                ),
            )
            try:
                new = _validate(ask(prompt, json_mode=True), len(here.beats))
            except Exception:  # noqa: BLE001 — a failed rewrite changes nothing
                continue
            words = sum(len(t.split()) for t in new)
            if _anchors(_text(out, here)) != _anchors(" ".join(new)):
                report["rejected_facts"] += 1
                continue
            if not KEEP_LENGTH[0] * here.words <= words <= KEEP_LENGTH[1] * here.words:
                continue
            if score(" ".join(new), hook=(idx == 0)) <= here.score:
                continue  # not better by the rules: keep the director's
            for i, t in zip(here.beats, new):
                out["beats"][i]["text"] = t
            report["rewritten"] += 1
    final = measure(out, seconds)
    out["text"] = " ".join(str(b.get("text") or "") for b in out["beats"])
    report["after"] = overall(final)
    report["parts"] = [
        {"name": p.name, "score": p.score, "problems": p.problems} for p in final
    ]
    return out, report


def line(report: Dict[str, Any]) -> str:
    """One honest line about it (empty when nothing was done)."""
    if not report or not report.get("parts"):
        return ""
    n = len(report["parts"])
    done = int(report.get("rewritten") or 0)
    if not done:
        return f"Guion revisado en {n} partes: interés {report['before']}/100, sin cambios."
    return (
        f"Guion trabajado en {n} partes: reescribí {done} y el interés medido "
        f"pasó de {report['before']} a {report['after']} sobre 100."
    )


__all__ = [
    "Part",
    "concrete",
    "improve",
    "line",
    "measure",
    "overall",
    "part_problems",
    "score",
    "split",
]

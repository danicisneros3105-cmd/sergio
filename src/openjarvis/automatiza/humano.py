"""Automations that read like a careful person made them.

The owner (4 Nov 2026): «mejora las automatizaciones para que parezcan hechas
por un humano de lo perfectas que son». A machine's work gives itself away by
the same few things, and each one is measurable:

* **Stock phrases** («espero que este mensaje le encuentre bien», «no dude en
  contactarme», «as an AI», «delve»).
* **The same opening every time** (ten replies that all start «¡Gracias por tu
  comentario!»).
* **Padding**: exclamations, emojis, a wall of hashtags, links nobody asked for.
* **Clockwork timing**: a video every 3.000 hours exactly, always at :00.

:func:`review` finds them with plain rules; :func:`polish` asks the model to
fix a text **once** and keeps the rewrite only if it has fewer problems;
:func:`stagger` moves a due time by a small, reproducible amount, the way a
person's day drifts, and avoids the small hours.

What this is not: it never hides that Sergio is an AI. A call to a third party
still starts by saying so, and nothing here sends anything: drafts still wait
for the owner's yes (AGENTS.md §3). The point is quality, not disguise.
"""

from __future__ import annotations

import random
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

# What gives a text away. Lower case; matched as substrings.
STOCK = (
    "espero que este mensaje le encuentre bien", "espero que estés bien", "espero que te encuentres bien",
    "no dude en contactarme", "no dudes en contactarme", "no dudes en escribirme",
    "me complace informarle", "me complace informarte", "estimado/a", "estimado equipo",
    "como modelo de lenguaje", "como inteligencia artificial", "en el dinámico mundo",
    "en el vertiginoso mundo", "sumérgete", "un sinfín de", "es un placer", "gracias por tu valioso comentario",
    "gracias por compartir tu opinión", "agradezco enormemente",
    "i hope this message finds you well", "feel free to reach out", "as an ai", "delve",
    "tapestry", "in today's fast-paced", "thank you for your valuable", "i am thrilled",
)  # fmt: skip
EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿⭐⬆✅❌️]", re.UNICODE)
MAX_HASHTAGS = 4
MAX_EXCLAMATIONS = 1
OPENING_WORDS = 3


def opening(text: str, n: int = OPENING_WORDS) -> str:
    words = re.findall(r"[\wáéíóúñü]+", (text or "").lower())
    return " ".join(words[:n])


def review(text: str, recent: Sequence[str] = ()) -> List[str]:
    """What is robotic in *text*, in plain words (empty = reads naturally).

    *recent* are the last texts of the same kind; opening like one of them is a
    problem."""
    out: List[str] = []
    low = (text or "").lower()
    found = [p for p in STOCK if p in low]
    if found:
        out.append("frases de plantilla: «" + "», «".join(found[:3]) + "»")
    if EMOJI.search(text or ""):
        out.append("tiene emojis (Sergio no los usa)")
    if (text or "").count("!") + (text or "").count("¡") > 2 * MAX_EXCLAMATIONS:
        out.append("demasiadas exclamaciones")
    if len(re.findall(r"#\w+", text or "")) > MAX_HASHTAGS:
        out.append(f"más de {MAX_HASHTAGS} etiquetas")
    mine = opening(text)
    if mine and any(opening(r) == mine for r in recent if r):
        out.append("empieza igual que uno de los últimos: «" + mine + "…»")
    if re.search(r"(\b\w+\b)(\s+\1\b)", low):
        out.append("repite una palabra seguida")
    return out


FIX = """Rewrite this text so it reads like one careful person wrote it, not a template.
Keep every fact, name, number and the same meaning, the same language and about the same length.
Fix exactly this:
{problems}
Do not add emojis. Do not add anything the text did not say. Open differently from these openings: {openings}
Answer ONLY the rewritten text.

TEXT:
{text}"""


def polish(
    text: str,
    ask: Optional[Callable[..., str]] = None,
    recent: Sequence[str] = (),
) -> str:
    """*text*, fixed once if it reads robotic; unchanged when it is fine, when
    the model fails or when the rewrite is not better by :func:`review`."""
    problems = review(text, recent)
    if not problems or ask is None:
        return text
    prompt = FIX.format(
        problems="\n".join(f"- {p}" for p in problems),
        openings=", ".join(f"«{opening(r)}»" for r in recent[-6:] if r) or "(none)",
        text=text,
    )
    try:
        new = str(ask(prompt)).strip()
    except Exception:  # noqa: BLE001 — a failed polish leaves the draft as it was
        return text
    if (
        not new
        or new.startswith(("{", "["))
        or not 0.5 * len(text) <= len(new) <= 1.6 * len(text)
    ):
        return text
    return new if len(review(new, recent)) < len(problems) else text


def distinct_openings(drafts: List[Dict[str, Any]], key: str) -> List[str]:
    """What to avoid next: the openings already used by *drafts*."""
    return [str(d.get(key) or "") for d in drafts]


def stagger(
    due: float,
    every_hours: float,
    seed: str = "",
    *,
    spread: float = 0.12,
    cap_s: float = 45 * 60,
) -> float:
    """*due* moved by a small reproducible amount (up to *spread* of the
    interval, at most *cap_s*) and never to a round minute. The caller counts
    the next interval from the real start, so a schedule never drifts away."""
    rng = random.Random(f"{seed}:{int(due) // 60}")
    limit = min(cap_s, spread * every_hours * 3600)
    moved = due + rng.uniform(-limit, limit)
    moved = round(moved / 60) * 60 + rng.choice((7, 13, 19, 23, 31, 41, 47, 53))
    return float(moved)


__all__ = ["distinct_openings", "opening", "polish", "review", "stagger"]

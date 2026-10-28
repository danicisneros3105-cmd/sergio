"""The review: an editor looks at the whole cut and says what to change.

The strongest model gets one sheet with a frame of every shot (numbered in
order), the plan and the reference's profile, and answers with changes to
specific shots. Only fields of the plan can change (what a shot shows, its
words, its look, its cut and sound), so a review can never break the edit:
:func:`apply` checks each change against the allowed values, and the plan is
made valid again afterwards. A shot whose picture changes gets a new one.
"""

from __future__ import annotations

import io
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from openjarvis.video_essay import plan as P
from openjarvis.video_essay.plan import Shot, Word

FIELDS = {
    "kind": P.KINDS,
    "card": P.CARDS,
    "text_style": P.TEXT_STYLES,
    "position": P.POSITIONS,
    "effect": P.EFFECTS,
    "grade": P.GRADES,
    "frame": P.FRAMES,
    "device": P.DEVICES,
    "transition": P.TRANSITIONS,
    "sfx": P.SFX,
    "source": P.SOURCES,
}
FREE = {"visual": 400, "text": 200, "highlight": 40, "overlay": 24, "camera": 160}

REVIEW_PROMPT = """You are the senior editor reviewing a cut of a video essay before it \
goes out. The sheet shows one frame of every shot, numbered in order (#0 first). \
It must reach the level of the reference style below: a cut every ~{median}s, \
kinetic text in every shot, the right mix of cards / archive / device / b-roll, \
strong literal visuals, readable text, rhythm that builds to the payoff.

REFERENCE STYLE: {style}
PLAN (index, kind, words, visual, look): {plan}

SAY = SHOW: the picture of a shot must show what is said at that very moment. \
When the words name a thing, a place or an action, the picture IS that thing; \
when they speak of a feeling or a human situation, prefer a scene of a film or \
series (source film) over a stock clip. A generic picture over a precise phrase \
is the worst fault: fix those first.

Find what most hurts the edit: unreadable or crowded text, a picture that does \
not match its words, too many similar shots in a row, wrong mix, weak payoff, \
no contrast between past (bw) and future (colour), missing sound on key cuts.
Answer ONLY JSON: {{"score": 1-10, "verdict": "one sentence", \
"changes": [{{"shot": index, "set": {{"field": "value"}}, "why": "..."}}]}}
Fields you may set: kind, card, visual (English, one filmable picture), text \
(a subset of that shot's spoken words), highlight, text_style, position, \
effect, grade, frame, device, transition, sfx, source (library|stock|web|film|archive|ai|3d|image), \
overlay (a counter or stamp) and camera. At most {limit} changes."""


def contact_sheet(
    stills: List[Image.Image], cols: int = 6, width: int = 1800
) -> Image.Image:
    """The frames numbered, side by side."""
    from openjarvis.video_essay.render import sheet

    numbered = []
    for i, img in enumerate(stills):
        img = img.convert("RGB").copy()
        d = ImageDraw.Draw(img)
        s = max(14, img.size[1] // 9)
        d.rectangle((0, 0, s * 2.4, s * 1.3), fill=(0, 0, 0))
        d.text((s * 0.3, s * 0.15), f"#{i}", fill=(255, 255, 255), font_size=s)
        numbered.append(img)
    return sheet(numbered, cols=cols, width=width)


def plan_summary(shots: List[Shot]) -> str:
    rows = []
    for i, s in enumerate(shots):
        look = "/".join(
            v
            for v in (
                s.card if s.kind == "card" else "",
                s.grade,
                s.frame,
                s.device,
                s.effect,
            )
            if v and v not in ("none", "natural")
        )
        rows.append(
            f"{i}|{s.kind}|{s.text[:60]}|{s.visual[:70]}|{look}|{s.transition}|{s.sfx}"
        )
    return "\n".join(rows)


def _check(text: str) -> Dict[str, Any]:
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("changes", []), list):
        raise ValueError("sin cambios")
    return data


def ask_review(
    sheet_img: Image.Image,
    shots: List[Shot],
    style: Dict[str, Any],
    *,
    limit: int = 20,
    ask: Optional[Callable[..., str]] = None,
) -> Dict[str, Any]:
    """The editor's notes on this cut ({"score", "verdict", "changes"})."""
    prompt = REVIEW_PROMPT.format(
        median=style.get("median_shot_s", 1.6),
        style=json.dumps(
            {
                k: style.get(k)
                for k in ("mix", "effects", "structure", "grade", "typography")
            },
            ensure_ascii=False,
        )[:2500],
        plan=plan_summary(shots),
        limit=limit,
    )
    buf = io.BytesIO()
    sheet_img.save(buf, "JPEG", quality=80)
    if ask is None:
        from google.genai import types

        from openjarvis.creator.llm import ask as gemini_ask
        from openjarvis.video_essay.style import models

        part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
        raw = gemini_ask(
            [part, prompt],
            json_mode=True,
            check=_check,
            models=models(),
            effort="high",
            max_tokens=16000,
        )
    else:
        raw = ask([buf.getvalue(), prompt], json_mode=True, check=_check)
    return _check(raw)


def apply(
    shots: List[Shot],
    words: List[Word],
    notes: Dict[str, Any],
    style: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Shot], int]:
    """Shots with the editor's valid changes; how many were applied."""
    applied = 0
    for change in notes.get("changes") or []:
        try:
            shot = shots[int(change.get("shot"))]
        except (TypeError, ValueError, IndexError):
            continue
        sets = change.get("set") if isinstance(change.get("set"), dict) else {}
        for key, value in sets.items():
            if key in FIELDS:
                value = str(value or "").strip().lower()
                if value not in FIELDS[key] or getattr(shot, key) == value:
                    continue
            elif key in FREE:
                value = str(value or "").strip()[: FREE[key]]
                if getattr(shot, key) == value:
                    continue
            else:
                continue
            setattr(shot, key, value)
            if key in ("visual", "kind", "source"):
                shot.asset = ""  # a new picture for it
            applied += 1
        if applied and change.get("why"):
            shot.notes.append(f"revisión: {str(change['why'])[:120]}")
    return P.normalise(shots, words, **P.pace(style or {})), applied


__all__ = ["apply", "ask_review", "contact_sheet", "plan_summary"]

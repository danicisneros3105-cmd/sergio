"""Two AIs make each video, like a film crew:

* the **director** (the strongest model) reads the order — a topic, the
  owner's script or a free prompt, as one would brief a studio — chooses the
  style among the references Sergio knows, and writes the treatment: title,
  idea, narration (or none, or a song), the characters with a fixed look for
  AI and 3D shots, the look, the music and where the pictures should come
  from. At the end it gives the cut its last notes (the director's pass);
* the **editor** (a fast model) does the rest of the work: cuts the shots on
  the words, chooses clips, and the first review passes.

``SERGIO_VIDEO_DIRECTOR_MODELS`` and ``SERGIO_VIDEO_EDITOR_MODELS`` choose
the models (comma-separated); by default the strongest Gemini directs and a
fast one edits. In Test mode the fast one does both.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional

EDITOR_MODELS = ("gemini-3.6-flash", "gemini-3.8-flash", "gemini-2.5-flash")

TREATMENT_PROMPT = """You are an award-winning director planning a video that people remember \
and share. Brief from the client: «{brief}»
Language of everything spoken or written on screen: {language}. Length: about {seconds} seconds.

Styles you can direct (pick the one that fits the brief best{fixed}):
{styles}

Write the treatment. Narration: "voice" (Sergio, a male narrator, reads it), "none" (no \
voice: the pictures and sound carry it; then "beats" are the on-screen moments, 1-5 words \
each, or empty strings) or "song" (music carries it; beats as for none). For "voice", \
about {words} words in total, short spoken sentences, a hook in the first 3 seconds, no \
invented quotes or statistics, no brand names.
Answer ONLY JSON: {{"style": "style key", "title": "max 7 words", "logline": "one sentence",
"narration": "voice|none|song",
"beats": [{{"beat": "hook|setup|problem|turn|story|contrast|escalation|climax|payoff|reveal|cta",
            "text": "what is said (or shown)", "seconds": n, "visual": "what we see, concrete, in English",
            "delivery": {{"tone": "calm|warm|curious|urgent|excited|serious|whisper|ironic|triumphant",
                          "pause": seconds}}}}],
"characters": [{{"name": "...", "look": "fixed description: age, face, hair, skin, clothes, build"}}],
"look": "the visual language in one paragraph (light, lenses, grade, textures)",
"music": "mood and build of the music",
"sources": ["the picture sources in order of preference, from: library, stock, web, film, archive, ai, 3d, image"]}}
Coherence: one clear through-line from the hook to the payoff; every beat follows from the \
one before (because / but / so), never a list of loose facts. The visuals live in one world: \
the same places, characters and objects come back, and a visual motif ties the video together.{long}"""

LONG_FORM = """
This is a LONG video ({minutes} minutes): plan it in chapters of 45-90 seconds (about \
{chapters} chapters). Each chapter opens with a mini-hook, builds, and ends with an open loop \
that pulls into the next; the hook's question is answered only near the end, with a \
callback to the opening image. Keep the narration dense and concrete for the whole length: \
write the full {words} words, not a summary."""


def _models(env: str, default: tuple) -> tuple:
    chosen = os.environ.get(env, "").strip()
    return tuple(m.strip() for m in chosen.split(",") if m.strip()) or default


def director_models() -> tuple:
    from openjarvis.video_essay.style import models

    return _models("SERGIO_VIDEO_DIRECTOR_MODELS", models())


def editor_models() -> tuple:
    return _models("SERGIO_VIDEO_EDITOR_MODELS", EDITOR_MODELS)


def asker(
    strong: bool, budget: Any = None, *, effort: str = "high", max_tokens: int = 32000
) -> Callable[..., str]:
    """A model call that counts against the job's budget."""

    def ask(prompt: Any, **kw: Any) -> str:
        from openjarvis.creator.llm import ask as gemini_ask

        if budget is not None:
            budget.spend("llm")
        return gemini_ask(
            prompt,
            models=director_models() if strong else editor_models(),
            effort=effort if strong else "low",
            max_tokens=max_tokens,
            **kw,
        )

    return ask


def vision_asker(strong: bool, budget: Any = None) -> Callable[..., str]:
    """Like :func:`asker`, for prompts that carry pictures (JPEG/PNG bytes)."""

    def ask(parts: List[Any], prompt: str = "", **kw: Any) -> str:
        from google.genai import types

        from openjarvis.creator.llm import ask as gemini_ask

        if budget is not None:
            budget.spend("llm")
        items: List[Any] = []
        for p in list(parts) + ([prompt] if prompt else []):
            if isinstance(p, (bytes, bytearray)):
                mime = "image/png" if bytes(p[:4]) == b"\x89PNG" else "image/jpeg"
                items.append(types.Part.from_bytes(data=bytes(p), mime_type=mime))
            else:
                items.append(p)
        kw.setdefault("json_mode", True)
        return gemini_ask(
            items,
            models=director_models() if strong else editor_models(),
            effort="high" if strong else "low",
            max_tokens=16000,
            **kw,
        )

    return ask


def style_menu(profiles: List[Dict[str, Any]]) -> str:
    rows = []
    for p in profiles:
        rows.append(
            f"- {p['key']}: {p.get('name', '')}. Production: {p.get('production', 'edit')}; "
            f"narration: {p.get('narration_mode', 'voice')}; cut every ~{p.get('median_shot_s', 1.6)} s; "
            f"look: {str(p.get('look') or p.get('grade') or '')[:220]}"
        )
    return "\n".join(rows)


TONES = (
    "calm",
    "warm",
    "curious",
    "urgent",
    "excited",
    "serious",
    "whisper",
    "ironic",
    "triumphant",
)


def _delivery(raw: Any) -> Dict[str, Any]:
    """How a beat is said: a tone and the silence after it (seconds)."""
    raw = raw if isinstance(raw, dict) else {}
    tone = str(raw.get("tone") or "").strip().lower()
    try:
        pause = float(raw.get("pause") or 0)
    except (TypeError, ValueError):
        pause = 0.0
    return {
        "tone": tone if tone in TONES else "",
        "pause": round(min(1.6, max(0.0, pause)), 2),
    }


def _check(text: str) -> Dict[str, Any]:
    data = json.loads(text)
    beats = [b for b in data.get("beats") or [] if isinstance(b, dict)]
    if not beats:
        raise ValueError("sin tratamiento")
    data["beats"] = [
        {
            "beat": str(b.get("beat") or ""),
            "text": " ".join(str(b.get("text") or "").split()),
            "seconds": float(b.get("seconds") or 0)
            if str(b.get("seconds") or "").replace(".", "", 1).isdigit()
            else 0.0,
            "visual": str(b.get("visual") or "")[:400],
            "delivery": _delivery(b.get("delivery")),
        }
        for b in beats
    ]
    narration = str(data.get("narration") or "voice").lower()
    data["narration"] = narration if narration in ("voice", "none", "song") else "voice"
    if (
        data["narration"] == "voice"
        and sum(len(b["text"].split()) for b in data["beats"]) < 12
    ):
        raise ValueError("guion demasiado corto")
    data["characters"] = [
        c for c in data.get("characters") or [] if isinstance(c, dict)
    ][:8]
    data["sources"] = [
        str(s)
        for s in data.get("sources") or []
        if str(s) in ("library", "stock", "web", "film", "archive", "ai", "3d", "image")
    ]
    return data


def treatment(
    brief: str,
    profiles: List[Dict[str, Any]],
    seconds: float,
    ask: Callable[..., str],
    *,
    language: str = "Spanish",
    fixed_style: str = "",
    words_per_second: float = 1.9,
    advice: str = "",
) -> Dict[str, Any]:
    """The director's plan for the whole video (*advice*: the specialist's)."""
    words = round(seconds * words_per_second)
    long = (
        LONG_FORM.format(
            minutes=round(seconds / 60, 1),
            chapters=max(3, round(seconds / 70)),
            words=words,
        )
        if seconds >= 180
        else ""
    )
    prompt = TREATMENT_PROMPT.format(
        brief=brief[:3000],
        language=language,
        seconds=round(seconds),
        words=words,
        styles=style_menu(profiles),
        fixed=f"; the client asked for «{fixed_style}», use it" if fixed_style else "",
        long=long,
    ) + (advice or "")
    data = _check(ask(prompt, json_mode=True, check=_check))
    said = sum(len(b["text"].split()) for b in data["beats"])
    if (
        data.get("narration", "voice") == "voice"
        and seconds >= 120
        and said < words * 0.7
    ):
        # models shorten long scripts: once more, asking for the full length
        again = (
            f"{prompt}\n\nYour last draft had only {said} words. Write the whole "
            f"treatment again with about {words} words of narration."
        )
        try:
            longer = _check(ask(again, json_mode=True, check=_check))
            if sum(len(b["text"].split()) for b in longer["beats"]) > said:
                data = longer
        except Exception:  # noqa: BLE001 — the shorter draft still makes a video
            pass
    keys = {p["key"] for p in profiles}
    if fixed_style in keys:
        data["style"] = fixed_style
    elif data.get("style") not in keys:
        data["style"] = profiles[0]["key"] if profiles else ""
    data["title"] = str(data.get("title") or brief[:60])[:70]
    data["text"] = " ".join(b["text"] for b in data["beats"] if b["text"])
    return data


PACKAGE_PROMPT = """Write the posting package for this video (YouTube / TikTok / Reels), in \
{language}. Title of the film: «{title}». What it is: {logline}
Chapters (time: beat): {chapters}
Answer ONLY JSON: {{"title": "max 70 characters, curiosity without lying", \
"description": "3-6 short lines, no hashtags spam", "tags": ["8-15 tags"], \
"hashtags": ["3-5"], "thumbnail_text": "2-4 punchy words"}}"""


def package(
    title: str,
    logline: str,
    chapters: List[tuple],
    credits: str,
    ask: Optional[Callable[..., str]],
    *,
    language: str = "Spanish",
) -> Dict[str, Any]:
    """Title, description (with chapters and credits), tags and cover text."""
    lines = [f"{int(t // 60)}:{int(t % 60):02d} {name}" for t, name in chapters]
    data: Dict[str, Any] = {}
    if ask is not None:
        try:
            data = json.loads(
                ask(
                    PACKAGE_PROMPT.format(
                        language=language,
                        title=title,
                        logline=logline,
                        chapters="; ".join(lines),
                    ),
                    json_mode=True,
                )
            )
        except Exception:  # noqa: BLE001 — a plain package instead
            data = {}
    description = str(data.get("description") or logline)
    if len(lines) >= 3:
        description += "\n\n" + "\n".join(lines)
    if credits:
        description += "\n\nCréditos de imágenes, clips y música:\n" + credits
    return {
        "title": str(data.get("title") or title)[:100],
        "description": description[:4900],
        "tags": [str(t) for t in data.get("tags") or []][:20],
        "hashtags": [str(t) for t in data.get("hashtags") or []][:5],
        "thumbnail_text": str(data.get("thumbnail_text") or title)[:40],
        "note": (
            "Lleva clips o música de terceros: las plataformas pueden reclamarlos o quitarles la monetización."
            if credits and "no libre" in credits
            else ""
        ),
    }


__all__ = [
    "vision_asker",
    "asker",
    "director_models",
    "editor_models",
    "package",
    "style_menu",
    "treatment",
]

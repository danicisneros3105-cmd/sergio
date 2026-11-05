"""Video Pro: an editor that watches your clips before cutting them.

The companion sends, for every clip, a contact sheet (frames every few
seconds, each stamped with its time) and its length. The configured vision model plays editor:
picks the best moments in a strong order (hook first), writes short
captions, a title for the video and the YouTube metadata (title,
description, tags). The companion renders it with ffmpeg (smooth cross
fades, captions, loudness normalised, music under the voices).
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Callable

PLAN_PROMPT = """You are a senior video editor (YouTube, Reels, TikTok). The \
user asks (Spanish): «{request}».
Attached: one contact sheet per clip, in order (clip 1, clip 2, ...). Each \
tile is stamped with its time in seconds. Clip lengths (seconds): {lengths}.
Make a {target} edit:
- Choose the best, sharpest, most interesting moments; cut dead time; start \
with a hook in the first 3 seconds; keep a rhythm (segments 2-6 s for short \
formats, longer for documentary style); never repeat a moment.
- Each segment: clip number (1-based), start and end in seconds inside that \
clip, and an optional short on-screen caption in Spanish (max 6 words, only \
when it helps).
- Format: "9:16" for Shorts/Reels/TikTok, "16:9" otherwise (follow the request).
- YouTube metadata in Spanish: catchy honest title (max 70 characters), a \
description of 2-4 sentences, 5-10 tags.
- Per segment you may also set: "transition" INTO it (cut, flash, whip, zoom, \
fade or glitch), "zoom" (none, punch = a sudden 1.2x punch-in, push = a slow \
push-in) and "speed" (0.5 slow motion .. 2.0 sped up; 1.0 normal).
{style}Answer ONLY JSON: {{"aspect": "9:16" or "16:9", "title_overlay": "short title \
shown at the start or empty", "segments": [{{"clip": 1, "start": 0.0, "end": \
3.5, "caption": "", "transition": "cut", "zoom": "none", "speed": 1.0}}], \
"youtube": {{"title": "...", "description": "...", "tags": ["..."]}}}}"""
TRANSITIONS = ("cut", "flash", "whip", "zoom", "fade", "glitch")
ZOOMS = ("none", "punch", "push")


def parse_plan(text: str, lengths: list[float]) -> dict[str, Any]:
    """The model's plan, checked: real clips, times inside each clip."""
    found = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(found.group(0)) if found else {}
    except ValueError:
        data = {}
    segments = []
    for seg in data.get("segments") or []:
        try:
            clip = int(seg.get("clip")) - 1
            start, end = float(seg.get("start")), float(seg.get("end"))
        except (TypeError, ValueError, AttributeError):
            continue
        if not 0 <= clip < len(lengths) or not all(map(math.isfinite, (start, end))):
            continue
        length = lengths[clip]
        if not math.isfinite(length) or length <= 0:
            continue
        start, end = max(0.0, start), min(end, length)
        if end - start < 0.5:
            continue
        caption = " ".join(str(seg.get("caption") or "").split())[:60]
        transition = str(seg.get("transition") or "fade").lower()
        zoom = str(seg.get("zoom") or "none").lower()
        try:
            speed = max(0.5, min(2.0, float(seg.get("speed") or 1.0)))
        except (TypeError, ValueError):
            speed = 1.0
        segments.append(
            {
                "clip": clip,
                "start": round(start, 2),
                "end": round(end, 2),
                "caption": caption,
                "transition": transition if transition in TRANSITIONS else "fade",
                "zoom": zoom if zoom in ZOOMS else "none",
                "speed": round(speed, 2),
            }
        )
    if not segments:
        raise RuntimeError("El editor no propuso cortes válidos.")
    yt = data.get("youtube")
    yt = yt if isinstance(yt, dict) else {}
    tags = [str(t)[:30] for t in (yt.get("tags") or []) if str(t).strip()][:12]
    return {
        "aspect": "9:16" if str(data.get("aspect")) == "9:16" else "16:9",
        "title_overlay": " ".join(str(data.get("title_overlay") or "").split())[:50],
        "segments": segments,
        "youtube": {
            "title": str(yt.get("title") or "")[:100],
            "description": str(yt.get("description") or "")[:4000],
            "tags": tags,
        },
    }


def plan(
    request: str,
    sheets: list[bytes],
    lengths: list[float],
    ask: Callable[[list[bytes], str], str] | None = None,
    style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The edit plan; with *style* (video_style) the cut follows a style
    learned from real videos, and the render gets its look and captions."""
    target = (
        "short vertical (under 60 s)"
        if re.search(r"short|reel|tiktok|vertical|corto", request.lower())
        else "well-paced"
    )
    brief = ""
    if style:
        from openjarvis.tools.video_style import style_brief

        brief = style_brief(style)
    prompt = PLAN_PROMPT.format(
        request=request,
        lengths=", ".join(f"{x:.1f}" for x in lengths),
        target=target,
        style=brief,
    )
    try:  # what the user said about earlier edits (long-term memory)
        from openjarvis.evolution.memory import lessons

        prompt += "\n" + lessons(request, ("feedback", "video"))
    except Exception:  # noqa: BLE001 — memory is a bonus
        pass
    result = parse_plan((ask or _ask)(sheets, prompt), lengths)
    if style:
        result["style"] = {
            "name": style.get("name", ""),
            "grade": style.get("grade", {}),
            "text": style.get("text", {}),
        }
    return result


def _ask(sheets: list[bytes], prompt: str) -> str:
    from openjarvis.tools.vision_look import ask_images

    return ask_images(sheets, prompt)


__all__ = ["parse_plan", "plan"]

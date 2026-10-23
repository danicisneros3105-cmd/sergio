"""Shots made with an AI video model, directed like a film crew.

The director writes a **character bible** (each person or creature with a
fixed description: age, face, hair, clothes) and every shot's prompt carries
it, so the same people appear in every shot. Each prompt is a camera
direction, not a wish: subject and action, lens and move, light, look of the
reference, and the realism rules for people (real skin, five-finger hands,
natural motion). Animation styles get their own rules instead.

Providers, the first available:

* **Veo** through the owner's Gemini key (needs a paid key with Veo;
  ``SERGIO_VEO_MODEL`` picks the model);
* **fal.ai** (``FAL_KEY``; ``SERGIO_FAL_VIDEO_MODEL`` picks Kling, Veo,
  Hailuo or any video model it serves).

Without either, the shot becomes a picture Sergio makes, kept moving by the
renderer. Seconds are counted against the job's budget before each call.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

VEO_MODELS = (
    "veo-3.1-generate-preview",
    "veo-3.1-fast-generate-preview",
    "veo-3.0-fast-generate-001",
)
FAL_DEFAULT = "fal-ai/kling-video/v2.1/master/text-to-video"

REALISM = (
    "photorealistic live-action footage, real people with natural skin texture and pores, "
    "real human proportions, anatomically correct hands with five fingers, natural believable "
    "motion and expressions, physically correct light and shadows, shot on a cinema camera, "
    "shallow depth of field, no text, no subtitles, no logos, no watermark"
)
ANIMATION = (
    "high-end animated film, consistent character design across shots, clean silhouettes, "
    "expressive poses, smooth animation, rich lighting, no text, no logos, no watermark"
)
NEGATIVE = (
    "text, subtitles, watermark, logo, extra fingers, deformed hands, distorted face, "
    "plastic skin, uncanny, morphing, flicker, low quality, blurry"
)


def bible_text(characters: List[Dict[str, str]]) -> str:
    rows = [
        f"{c.get('name', '').strip()}: {c.get('look', '').strip()}"
        for c in characters
        if c.get("look")
    ]
    return ("Characters (always identical): " + "; ".join(rows) + ". ") if rows else ""


def shot_prompt(
    visual: str,
    style: Dict[str, Any],
    characters: List[Dict[str, str]],
    camera: str = "",
) -> str:
    """The full direction for one shot."""
    animated = style.get("production") == "animation"
    look = str(style.get("look") or style.get("grade") or "")[:400]
    parts = [
        bible_text(characters),
        f"Shot: {visual.strip()}.",
        f"Camera: {camera.strip()}." if camera.strip() else "",
        f"Look: {look}." if look else "",
        ANIMATION if animated else REALISM,
    ]
    return " ".join(p for p in parts if p)


def available() -> str:
    """The provider that would be used ("" when none)."""
    if os.environ.get("FAL_KEY", "").strip():
        return "fal"
    if os.environ.get("SERGIO_VEO", "1") != "0" and (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    ):
        return "veo"
    return ""


def veo(
    prompt: str,
    out: Path,
    seconds: int,
    aspect: str,
    client: Any = None,
    poll: float = 10.0,
) -> str:
    from google.genai import types

    from openjarvis.creator.llm import gemini_key
    from openjarvis.engine.google_client import SwitchingClient

    client = client or SwitchingClient(gemini_key())
    wanted = os.environ.get("SERGIO_VEO_MODEL", "").strip()
    errors = []
    for model in (wanted,) if wanted else VEO_MODELS:
        try:
            op = client.models.generate_videos(
                model=model,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    aspect_ratio="9:16" if aspect == "9:16" else "16:9",
                    number_of_videos=1,
                    duration_seconds=max(4, min(8, seconds)),
                    negative_prompt=NEGATIVE,
                ),
            )
            for _ in range(int(900 / poll)):  # at most 15 minutes per shot
                if op.done:
                    break
                time.sleep(poll)
                op = client.operations.get(op)
            videos = (
                getattr(getattr(op, "response", None), "generated_videos", None) or []
            )
            if not videos:
                raise RuntimeError("sin video")
            client.files.download(file=videos[0].video)
            videos[0].video.save(str(out))
            return str(out)
        except Exception as exc:  # noqa: BLE001 — the next model
            errors.append(f"{model}: {str(exc)[:120]}")
    raise RuntimeError("Veo no pudo: " + " | ".join(errors))


def fal(prompt: str, out: Path, seconds: int, aspect: str, poll: float = 6.0) -> str:
    import httpx

    key = os.environ["FAL_KEY"].strip()
    model = os.environ.get("SERGIO_FAL_VIDEO_MODEL", FAL_DEFAULT).strip()
    head = {"Authorization": f"Key {key}"}
    r = httpx.post(
        f"https://queue.fal.run/{model}",
        json={
            "prompt": prompt,
            "duration": "5" if seconds <= 5 else "10",
            "aspect_ratio": aspect,
            "negative_prompt": NEGATIVE,
        },
        headers=head,
        timeout=60,
    )
    r.raise_for_status()
    job = r.json()
    status_url, result_url = job.get("status_url"), job.get("response_url")
    for _ in range(int(1200 / poll)):
        s = httpx.get(status_url, headers=head, timeout=30).json()
        if s.get("status") == "COMPLETED":
            break
        if s.get("status") in ("FAILED", "ERROR"):
            raise RuntimeError(f"fal: {s}")
        time.sleep(poll)
    data = httpx.get(result_url, headers=head, timeout=60).json()
    url = ((data.get("video") or {}).get("url")) or (
        (data.get("videos") or [{}])[0].get("url")
    )
    if not url:
        raise RuntimeError("fal no devolvió video")
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as resp:
        resp.raise_for_status()
        with out.open("wb") as f:
            for chunk in resp.iter_bytes(1 << 16):
                f.write(chunk)
    return str(out)


def generate(
    prompt: str,
    out: Path,
    seconds: float,
    aspect: str = "16:9",
    *,
    provider: Optional[Callable[[str, Path, int, str], str]] = None,
) -> str:
    """A clip for *prompt* (raises when no provider can make it)."""
    secs = int(max(4, min(10, round(seconds + 0.5))))
    out.parent.mkdir(parents=True, exist_ok=True)
    if provider is not None:
        return provider(prompt, out, secs, aspect)
    which = available()
    if which == "fal":
        return fal(prompt, out, secs, aspect)
    if which == "veo":
        return veo(prompt, out, secs, aspect)
    raise RuntimeError(
        "No hay modelo de video con IA (Veo en una clave de pago o FAL_KEY)."
    )


__all__ = [
    "NEGATIVE",
    "REALISM",
    "available",
    "bible_text",
    "fal",
    "generate",
    "shot_prompt",
    "veo",
]

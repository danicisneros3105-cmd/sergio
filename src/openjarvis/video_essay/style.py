"""The style of a reference video, studied shot by shot.

The owner gives a video (a file or a YouTube link) and says «edit like
this». The strongest model available watches the whole thing with its sound
and writes down every shot: what is said, what is on screen, how the words
appear, what is shown and how (archive in an old TV, a clip inside an old
computer, a colour card), the effect, the cut and the sound. From that list
code measures the style: shot length, how many cards, archive and device
shots, colours, effects. That profile drives the plan and the render.

Only how it is edited is kept, never the reference's footage or its words.
Profiles live in ``~/.openjarvis/video_styles/ensayo/``; the one built from
the owner's first reference ships with Sergio (``styles/metas-grandes.json``).
"""

from __future__ import annotations

import json
import os
import re
import statistics
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

BUILT_IN = Path(__file__).parent / "styles"
DEFAULT = "metas-grandes"
YOUTUBE = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com/|youtu\.be/)\S+")

# The deepest watcher first; the owner accepts that it takes long.
MODELS = (
    "gemini-3.1-pro-preview",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
)

WATCH_PROMPT = """You are a senior video editor reverse-engineering this edit so another \
editor can reproduce its LEVEL (not copy its content). Watch it all, with sound.
Return JSON only:
{"summary": "...", "narration_style": "...", "music_and_sound": "...",
 "typography": {"fonts": "...", "animation": "...", "colors": "...", "placement": "..."},
 "color_grade": "...", "recurring_effects": ["..."], "transitions": ["..."], "pacing": "...",
 "structure": [{"start": s, "end": s, "beat": "hook|problem|turn|story|contrast|payoff|cta"}],
 "palette": ["#rrggbb", "..."],
 "shots": [{"t": seconds, "dur": seconds, "narration": "words spoken", "on_screen_text": "...",
   "text_style": "...", "visual": "what is shown and its source type (film clip / archive / stock / \
generated / screen capture / solid card)", "effect": "zoom/mask/3D text/CRT frame/PiP/device/glitch/\
speed ramp/none", "transition_in": "...", "sfx": "..."}]}
List EVERY shot. Be precise with times."""


def models() -> tuple:
    chosen = os.environ.get("SERGIO_VIDEO_MODELS", "").strip()
    return tuple(m.strip() for m in chosen.split(",") if m.strip()) or MODELS


def learned_dir() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "video_styles" / "ensayo"


def slug(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "estilo"


def kind_of(shot: Dict[str, Any]) -> str:
    v = str(shot.get("visual") or "").lower()
    e = str(shot.get("effect") or "").lower()
    if "solid" in v or "card" in v:
        return "card"
    if any(k in e for k in ("crt", "film", "grain", "vhs")) or "black and white" in v:
        return "archive"
    if any(
        k in e + v
        for k in ("pip", "computer", "phone", "iphone", "screen", "device", "monitor")
    ):
        return "device"
    return "broll"


def profile_from(
    analysis: Dict[str, Any], key: str, name: str, source: str
) -> Dict[str, Any]:
    """Measure the style from the shot list (numbers by code, not by guess)."""
    shots = [s for s in analysis.get("shots") or [] if isinstance(s, dict)]
    durs = sorted(
        float(s.get("dur") or 0) for s in shots if float(s.get("dur") or 0) > 0
    )
    kinds = Counter(kind_of(s) for s in shots)
    total = max(1, len(shots))
    sfx = Counter(
        str(s.get("sfx") or "none").split(",")[0].strip().lower() or "none"
        for s in shots
    )
    palette = [
        c
        for c in analysis.get("palette") or []
        if re.fullmatch(r"#[0-9a-fA-F]{6}", str(c))
    ]
    return {
        "key": key,
        "name": name,
        "source": source,
        "shots_measured": len(shots),
        "length_s": round(sum(durs), 1),
        "median_shot_s": round(statistics.median(durs), 2) if durs else 1.6,
        "min_shot_s": round(durs[0], 2) if durs else 0.4,
        "max_shot_s": round(durs[-1], 2) if durs else 6.0,
        "mix": {k: round(v / total, 2) for k, v in kinds.items()},
        "text_share": round(
            sum(1 for s in shots if s.get("on_screen_text")) / total, 2
        ),
        "palette_seen": palette[:8],
        "grade": analysis.get("color_grade", ""),
        "typography": analysis.get("typography", {}),
        "narration": analysis.get("narration_style", ""),
        "music": analysis.get("music_and_sound", ""),
        "effects": analysis.get("recurring_effects", []),
        "transitions_seen": analysis.get("transitions", []),
        "sfx": {k: round(v / total, 2) for k, v in sfx.most_common(8)},
        "structure": [
            str(b.get("beat"))
            for b in analysis.get("structure") or []
            if isinstance(b, dict)
        ],
        "pacing": analysis.get("pacing", ""),
    }


def _client() -> Any:
    from openjarvis.tools.video_style import _client as client

    return client()


def watch(source: str, client: Any = None) -> Dict[str, Any]:
    """The deep shot-by-shot study of a file or a YouTube link."""
    from google.genai import types

    client = client or _client()
    if YOUTUBE.match(source.strip()):
        part: Any = types.Part(file_data=types.FileData(file_uri=source.strip()))
    else:
        path = Path(source).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"No encuentro el video: {source}")
        part = client.files.upload(file=str(path))
        for _ in range(120):
            state = getattr(getattr(part, "state", None), "name", "")
            if state != "PROCESSING":
                break
            time.sleep(3)
            part = client.files.get(name=part.name)
    errors: List[str] = []
    for model in models() + models()[:2]:  # busy models often answer a moment later
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[part, WATCH_PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=60000,
                    temperature=0.2,
                ),
            )
            data = json.loads(resp.text or "{}")
            if isinstance(data, dict) and data.get("shots"):
                data["_model"] = model
                return data
            errors.append(f"{model}: sin tomas")
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {str(exc)[:100]}")
    raise RuntimeError("No pude estudiar el video: " + " | ".join(errors[-4:]))


def learn(
    source: str,
    name: str = "",
    client: Any = None,
    folder: Optional[Path] = None,
    watcher: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Study *source* and keep its profile; returns the profile."""
    analysis = (watcher or (lambda s: watch(s, client)))(source)
    label = name or str(analysis.get("summary") or "Estilo de referencia")[:60]
    key = slug(name or (label if YOUTUBE.match(source) else Path(source).stem))
    profile = profile_from(analysis, key, label, source)
    folder = folder or learned_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=1), "utf-8"
    )
    (folder / f"{key}.tomas.json").write_text(
        json.dumps(analysis, ensure_ascii=False), "utf-8"
    )
    return profile


def load(name: str = "", folder: Optional[Path] = None) -> Dict[str, Any]:
    """A saved profile by name (learned first, then built-in); the default."""
    wanted = slug(name) if name else DEFAULT
    for root in (folder or learned_dir(), BUILT_IN):
        path = root / f"{wanted}.json"
        if path.is_file():
            return json.loads(path.read_text("utf-8"))
    return json.loads((BUILT_IN / f"{DEFAULT}.json").read_text("utf-8"))


def available(folder: Optional[Path] = None) -> List[Dict[str, str]]:
    out = []
    for root in (folder or learned_dir(), BUILT_IN):
        if root.is_dir():
            for p in sorted(root.glob("*.json")):
                if p.name.endswith(".tomas.json"):
                    continue
                try:
                    d = json.loads(p.read_text("utf-8"))
                except ValueError:
                    continue
                out.append({"key": d.get("key", p.stem), "name": d.get("name", p.stem)})
    return out


__all__ = ["DEFAULT", "available", "learn", "load", "models", "profile_from", "watch"]

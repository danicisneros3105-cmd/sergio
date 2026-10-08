"""Video Pro learns an editing style by watching real videos.

"Show it many videos so it copies the style": Gemini watches YouTube videos
directly (by URL, the whole video with sound) and writes down how they are
edited — shot length and rhythm, how they open, transitions, zooms and speed
ramps, on-screen text, colour, music and sound effects. Several videos of the
same channel or ad are merged into one style profile that the editor then
follows when it cuts your clips, and that the renderer applies (cut rhythm,
punch-ins, flashes, whips, kinetic captions, colour grade).

* ``learn("NextCore")``: finds the channel's videos (Google Search inside
  Gemini), watches several and saves ``~/.openjarvis/video_styles/nextcore.json``.
* ``learn("https://youtu.be/...")``: watches exactly those videos.
* Styles that ship with Sergio (``video_styles/*.json``) were made the same
  way from real videos.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

BUILT_IN = Path(__file__).parent / "video_styles"
LEARNED = Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis") / "video_styles"
YOUTUBE = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
TRANSITIONS = ("cut", "flash", "whip", "zoom", "fade", "glitch")
MODELS = ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-2.5-flash", "gemini-3.1-pro-preview", "gemini-flash-lite-latest")

WATCH_PROMPT = """You are a senior video editor studying a reference video so \
you can copy its EDITING STYLE exactly (not its content). Watch the whole video \
with its sound. Measure, do not guess: count the cuts. If the video is a \
tutorial or breakdown ABOUT another channel's style, describe that channel's \
style as its examples show it (and name that channel in "channel").
Answer ONLY JSON:
{"title": "the video's title or topic", "channel": "the channel or brand the video shows \
(logo, watermark, intro, outro) or empty", "length_s": 0, "cuts": 0,
"avg_shot_s": 0.0, "pace": "very fast | fast | medium | slow",
"hook": "what happens in the first 3 seconds and why it grabs attention",
"structure": ["beat 1 (e.g. hook question)", "beat 2", "..."],
"transitions": {"cut": 0.0, "flash": 0.0, "whip": 0.0, "zoom": 0.0, "fade": 0.0, "glitch": 0.0},
"punch_in": 0.0, "speed_ramps": 0.0, "slow_motion": 0.0,
"camera": "how the camera moves (macro, orbit, static, handheld, slow push)",
"text": {"style": "font look, e.g. bold white sans caps", "position": "center | lower third | top",
 "words_per_caption": 0, "kinetic": true, "color": "#FFFFFF", "accent": "#FFD400", "frequency": "every shot | key moments | rare"},
"grade": {"look": "e.g. clean clinical white, teal and orange, dark moody", "contrast": 1.0,
 "saturation": 1.0, "warmth": 0.0, "brightness": 0.0, "vignette": false, "grain": false, "letterbox": false},
"audio": {"music": "genre and energy", "beat_synced_cuts": true, "sfx": ["whoosh", "click"], "voiceover": "none | narrator | creator"},
"aspect": "9:16 | 16:9 | 1:1",
"signature": ["the 3-6 techniques that make this style recognisable, concrete enough to reproduce"]}
Fractions in "transitions" sum to 1. punch_in / speed_ramps / slow_motion are \
the fraction of shots using them (0..1). contrast/saturation are multipliers \
around 1.0, warmth -1..1 (negative = cooler), brightness -0.2..0.2."""

FIND_PROMPT = """Use Google Search to find {n} recent, popular videos from the \
YouTube channel or campaign «{source}» (videos by that channel or brand, not \
reactions or re-uploads). Prefer its most typical videos. Answer ONLY with the \
video URLs, one per line (https://www.youtube.com/watch?v=... or \
https://www.youtube.com/shorts/...)."""


def slug(name: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", name.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:40] or "estilo"


def youtube_urls(text: str) -> list[str]:
    """The YouTube videos named in *text* (canonical URLs, no repeats)."""
    seen: list[str] = []
    for vid in YOUTUBE.findall(text or ""):
        url = f"https://www.youtube.com/watch?v={vid}"
        if url not in seen:
            seen.append(url)
    return seen


def _num(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def parse_watch(text: str) -> dict[str, Any]:
    """One video's analysis, checked and clamped."""
    found = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(found.group(0)) if found else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict) or not data.get("avg_shot_s"):
        raise RuntimeError("El análisis del video no midió los planos.")
    trans = data.get("transitions") if isinstance(data.get("transitions"), dict) else {}
    weights = {k: _num(trans.get(k), 0.0, 0.0, 1e6) for k in TRANSITIONS}  # fractions or counts: normalised below
    total = sum(weights.values()) or 1.0
    text_raw = data.get("text") if isinstance(data.get("text"), dict) else {}
    grade_raw = data.get("grade") if isinstance(data.get("grade"), dict) else {}
    audio_raw = data.get("audio") if isinstance(data.get("audio"), dict) else {}
    return {
        "title": str(data.get("title") or "")[:120],
        "channel": str(data.get("channel") or "")[:80],
        "length_s": _num(data.get("length_s"), 0.0, 0.0, 36000.0),
        "avg_shot_s": _num(data.get("avg_shot_s"), 3.0, 0.2, 30.0),
        "pace": str(data.get("pace") or "medium")[:20],
        "hook": str(data.get("hook") or "")[:300],
        "structure": [str(x)[:120] for x in (data.get("structure") or [])][:10],
        "transitions": {k: round(v / total, 3) for k, v in weights.items()},
        "punch_in": _num(data.get("punch_in"), 0.0, 0.0, 1.0),
        "speed_ramps": _num(data.get("speed_ramps"), 0.0, 0.0, 1.0),
        "slow_motion": _num(data.get("slow_motion"), 0.0, 0.0, 1.0),
        "camera": str(data.get("camera") or "")[:200],
        "text": {
            "style": str(text_raw.get("style") or "bold white sans")[:80],
            "position": next((p for p in ("center", "lower third", "top")
                              if p in str(text_raw.get("position") or "").lower()), "center"),
            "words_per_caption": int(_num(text_raw.get("words_per_caption"), 4, 1, 12)),
            "kinetic": bool(text_raw.get("kinetic")),
            "color": _hex(text_raw.get("color"), "#FFFFFF"),
            "accent": _hex(text_raw.get("accent"), "#FFD400"),
            "frequency": str(text_raw.get("frequency") or "key moments")[:30],
        },
        "grade": {
            "look": str(grade_raw.get("look") or "")[:120],
            "contrast": _num(grade_raw.get("contrast"), 1.0, 0.7, 1.5),
            "saturation": _num(grade_raw.get("saturation"), 1.0, 0.0, 1.8),
            "warmth": _num(grade_raw.get("warmth"), 0.0, -1.0, 1.0),
            "brightness": _num(grade_raw.get("brightness"), 0.0, -0.2, 0.2),
            "vignette": bool(grade_raw.get("vignette")),
            "grain": bool(grade_raw.get("grain")),
            "letterbox": bool(grade_raw.get("letterbox")),
        },
        "audio": {
            "music": str(audio_raw.get("music") or "")[:120],
            "beat_synced_cuts": bool(audio_raw.get("beat_synced_cuts")),
            "sfx": [str(x)[:30] for x in (audio_raw.get("sfx") or [])][:8],
            "voiceover": str(audio_raw.get("voiceover") or "")[:30],
        },
        "aspect": "9:16" if "9:16" in str(data.get("aspect")) else ("1:1" if "1:1" in str(data.get("aspect")) else "16:9"),
        "signature": [str(x)[:200] for x in (data.get("signature") or [])][:6],
    }


def _hex(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text.upper() if re.fullmatch(r"#[0-9a-fA-F]{6}", text) else default


def merge(name: str, analyses: list[dict[str, Any]], sources: list[str]) -> dict[str, Any]:
    """Several videos -> one style: numbers averaged, the most common
    choices kept, every signature technique listed once."""
    if not analyses:
        raise RuntimeError("No pude ver ningún video de referencia.")
    n = len(analyses)

    def avg(get: Callable[[dict[str, Any]], float]) -> float:
        return round(sum(get(a) for a in analyses) / n, 3)

    def common(get: Callable[[dict[str, Any]], Any]) -> Any:
        values = [get(a) for a in analyses]
        return max(values, key=values.count)

    signature: list[str] = []
    for a in analyses:
        for s in a["signature"]:
            if s not in signature:
                signature.append(s)
    first = analyses[0]
    return {
        "name": name,
        "slug": slug(name),
        "sources": sources,
        "videos": [a["title"] for a in analyses],
        "learned": time.strftime("%Y-%m-%d"),
        "avg_shot_s": avg(lambda a: a["avg_shot_s"]),
        "pace": common(lambda a: a["pace"]),
        "hook": first["hook"],
        "structure": first["structure"],
        "transitions": {k: avg(lambda a, k=k: a["transitions"][k]) for k in TRANSITIONS},
        "punch_in": avg(lambda a: a["punch_in"]),
        "speed_ramps": avg(lambda a: a["speed_ramps"]),
        "slow_motion": avg(lambda a: a["slow_motion"]),
        "camera": first["camera"],
        "text": {
            "style": common(lambda a: a["text"]["style"]),
            "position": common(lambda a: a["text"]["position"]),
            "words_per_caption": round(avg(lambda a: a["text"]["words_per_caption"])),
            "kinetic": common(lambda a: a["text"]["kinetic"]),
            "color": common(lambda a: a["text"]["color"]),
            "accent": common(lambda a: a["text"]["accent"]),
            "frequency": common(lambda a: a["text"]["frequency"]),
        },
        "grade": {
            "look": first["grade"]["look"],
            "contrast": avg(lambda a: a["grade"]["contrast"]),
            "saturation": avg(lambda a: a["grade"]["saturation"]),
            "warmth": avg(lambda a: a["grade"]["warmth"]),
            "brightness": avg(lambda a: a["grade"]["brightness"]),
            "vignette": common(lambda a: a["grade"]["vignette"]),
            "grain": common(lambda a: a["grade"]["grain"]),
            "letterbox": common(lambda a: a["grade"]["letterbox"]),
        },
        "audio": {
            "music": first["audio"]["music"],
            "beat_synced_cuts": common(lambda a: a["audio"]["beat_synced_cuts"]),
            "sfx": sorted({s for a in analyses for s in a["audio"]["sfx"]})[:8],
            "voiceover": common(lambda a: a["audio"]["voiceover"]),
        },
        "aspect": common(lambda a: a["aspect"]),
        "signature": signature[:10],
    }


def _client() -> Any:
    import os

    from openjarvis.engine.google_client import SwitchingClient

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY")
    return SwitchingClient(key)


def _watch_gemini(url: str) -> str:
    """Gemini watches one YouTube video (by URL) and describes its editing."""
    from google.genai import types

    client = _client()
    errors = []
    for model in (*MODELS, *MODELS[:2]):  # a second pass: busy models (503) often answer a moment later
        try:
            resp = client.models.generate_content(
                model=model,
                contents=types.Content(parts=[
                    types.Part(file_data=types.FileData(file_uri=url)),
                    types.Part(text=WATCH_PROMPT),
                ]),
                config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
            )
            text = str(resp.text or "")
            parse_watch(text)
            return text
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {str(exc)[:100]}")
    raise RuntimeError(f"No pude ver {url}: " + " | ".join(errors))


def _find_gemini(source: str, n: int) -> str:
    """Gemini with Google Search: the channel's / campaign's video URLs."""
    from google.genai import types

    client = _client()
    errors = []
    for model in MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[FIND_PROMPT.format(source=source, n=n)],
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
            )
            text = str(resp.text or "")
            meta = getattr(resp.candidates[0], "grounding_metadata", None) if resp.candidates else None
            for chunk in getattr(meta, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                if web is not None:
                    text += "\n" + str(getattr(web, "uri", "") or "")
            if youtube_urls(text):
                return text
            errors.append(f"{model}: sin enlaces de YouTube")
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {str(exc)[:100]}")
    raise RuntimeError(f"No encontré videos de «{source}»: " + " | ".join(errors))


def learn(
    source: str,
    name: str = "",
    n: int = 4,
    watch: Callable[[str], str] | None = None,
    find: Callable[[str, int], str] | None = None,
    folder: Path | None = None,
    author: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Watch *source* (YouTube URLs, or a channel / ad to search for) and save
    its editing style. Returns the style."""
    urls = youtube_urls(source)
    if not urls:
        urls = youtube_urls((find or _find_gemini)(source, n))[:n]
    if not urls:
        raise RuntimeError(f"No encontré videos de «{source}».")
    if name.strip():
        label = name.strip()
    else:  # the words around the links, or the channel searched for
        label = " ".join(re.sub(r"https?://\S+", " ", source).split()).strip(" ,;:") or "estilo"
    searched = not youtube_urls(source)
    if searched:  # found by search: only videos really from that channel / brand
        urls = [u for u in urls if belongs(source, (author or _author)(u))]
        if not urls:
            raise RuntimeError(f"Los videos que encontré no son de «{source}». Pásame enlaces de YouTube.")
    watcher = watch or _watch_gemini
    analyses, used = [], []
    with ThreadPoolExecutor(3) as pool:
        for url, result in zip(urls, pool.map(lambda u: _try(watcher, u), urls)):
            if result is None:
                continue
            if searched and result.get("channel") and not belongs(source, result["channel"]):
                continue  # Gemini saw another channel's branding in it
            analyses.append(result)
            used.append(url)
    style = merge(label, analyses, used)
    folder = folder or LEARNED
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{style['slug']}.json").write_text(json.dumps(style, ensure_ascii=False, indent=1), encoding="utf-8")
    return style


def _author(url: str) -> str:
    """The video's channel from YouTube's oEmbed ("" if it can't be asked)."""
    try:
        import httpx

        resp = httpx.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=8)
        if resp.status_code in (400, 401, 403, 404):
            return "-"  # no such public video
        return str(resp.json().get("author_name") or "") if resp.status_code == 200 else ""
    except Exception:  # noqa: BLE001 — offline: no check
        return ""


def belongs(source: str, channel: str) -> bool:
    """Is *channel* the channel / brand named in *source*? Unknown ("") is
    given the benefit of the doubt; "-" is a video that does not exist."""
    if not channel:
        return True
    if channel == "-":
        return False
    want = {w for w in slug(source).split("-") if len(w) > 2 and w not in ("canal", "youtube", "videos", "video", "the",
                                                                              "anuncio", "estilo", "del", "los", "las")}
    have = slug(channel).replace("-", "")
    return not want or any(w in have for w in want)


def _try(watcher: Callable[[str], str], url: str) -> dict[str, Any] | None:
    try:
        return parse_watch(watcher(url))
    except Exception:  # noqa: BLE001 — one video failing does not stop the rest
        return None


def available(folder: Path | None = None) -> list[dict[str, Any]]:
    """Every known style (learned ones override the built-in with the same name)."""
    found: dict[str, dict[str, Any]] = {}
    for base in (BUILT_IN, folder or LEARNED):
        if base.is_dir():
            for path in sorted(base.glob("*.json")):
                try:
                    style = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                found[style.get("slug") or path.stem] = style
    return list(found.values())


def find_style(name: str, folder: Path | None = None) -> dict[str, Any] | None:
    """The style called *name* ("dyson", "NextCore", "el de dyson camerajet")."""
    want = slug(name)
    if not want:
        return None
    styles = available(folder)
    for style in styles:
        if style.get("slug") == want:
            return style
    words = [w for w in want.split("-") if len(w) > 2 and w not in ("estilo", "del", "los", "las", "video", "videos")]
    best, hits = None, 0
    for style in styles:
        key = style.get("slug", "") + "-" + slug(" ".join(style.get("aliases", [])))
        score = sum(w in key for w in words)
        if score > hits:
            best, hits = style, score
    return best


def describe(style: dict[str, Any]) -> str:
    """A short Spanish summary for the user."""
    t = style.get("transitions", {})
    main = max(t, key=t.get) if t else "cut"
    names = {"cut": "cortes secos", "flash": "flashes", "whip": "barridos", "zoom": "zooms",
             "fade": "fundidos", "glitch": "glitches"}
    return (
        f"{style.get('name')}: planos de {style.get('avg_shot_s', 0):.1f} s de media ({style.get('pace')}), "
        f"sobre todo {names.get(main, main)}, punch-ins en el {style.get('punch_in', 0) * 100:.0f} % de los planos, "
        f"texto {style.get('text', {}).get('style', '')}, color «{style.get('grade', {}).get('look', '')}». "
        f"Aprendido de {len(style.get('sources', []))} videos."
    )


def style_brief(style: dict[str, Any]) -> str:
    """The style as instructions for the editor (Gemini) planning the cut."""
    t = style.get("transitions", {})
    text = style.get("text", {})
    grade = style.get("grade", {})
    audio = style.get("audio", {})
    return (
        f"EDIT IN THIS STYLE («{style.get('name')}», learned from real videos):\n"
        f"- Rhythm: average shot {style.get('avg_shot_s')} s ({style.get('pace')}); cut on the beat: "
        f"{audio.get('beat_synced_cuts')}.\n"
        f"- Hook: {style.get('hook')}\n"
        f"- Structure: {' -> '.join(style.get('structure', []))}\n"
        f"- Transitions mix: " + ", ".join(f"{k} {v:.0%}" for k, v in t.items() if v) + "\n"
        f"- Punch-in zoom on {style.get('punch_in', 0):.0%} of shots; speed ramps on {style.get('speed_ramps', 0):.0%}; "
        f"slow motion on {style.get('slow_motion', 0):.0%}. Camera: {style.get('camera')}\n"
        f"- Captions: {text.get('style')}, {text.get('position')}, about {text.get('words_per_caption')} words, "
        f"{'kinetic word by word' if text.get('kinetic') else 'static'}, {text.get('frequency')}.\n"
        f"- Look: {grade.get('look')}. Music: {audio.get('music')}. SFX: {', '.join(audio.get('sfx', []))}.\n"
        f"- Signature techniques to reproduce: " + " | ".join(style.get("signature", [])) + "\n"
    )


__all__ = ["available", "describe", "find_style", "learn", "merge", "parse_watch", "style_brief", "youtube_urls"]

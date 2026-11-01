"""Cine con IA en Creator: historias cinematográficas a la medida, toma por toma.

The owner (1 Nov 2026): «integrate a specialized generative video marketplace
and creation engine focused on empowering social media content creators,
directors and animators to design hyper-personalized, cinematic-quality
storytelling content (in creator)».

That is Higgsfield. Sergio does not copy it: it **uses the owner's own
Higgsfield account** through the official connector (MCP, ``mcp/directory.py``,
«Conectores → Higgsfield → Conectar»), so its marketplace of presets and its
video models work with his credits. Without the connector the same shot list
goes to Sergio's own AI video (``video_essay/aivideo.py``: Veo or fal.ai).

What Sergio adds is the director's part:

* ``brief`` turns an idea into a short film: hook, rise, turn, payoff, each
  shot with a camera move from ``CAMERA``, a lens, light and one action, made
  for the owner's audience, platform and brand (hyper-personalized);
* ``catalog`` searches the Higgsfield marketplace (presets, effects, motion);
* ``cost`` asks Higgsfield what the shots cost **before** spending;
* ``render`` makes every shot, waits, downloads and joins them with ffmpeg.

Generating spends the owner's credits: each Higgsfield call goes through the
connector's own permission (it asks him unless he allowed it), and the price
is shown first. Nothing is published: the film lands in
``~/.openjarvis/cine_ia/<id>/``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

SERVER = "higgsfield"
DEFAULT_MODEL = "seedance_2_5"  # Higgsfield's general video model
MULTI_SHOT_MODEL = "kling3_0"
MAX_SHOTS = 8
WAIT_LIMIT = 1200.0
LIGHT = "soft cinematic key light, gentle contrast"

# Sergio's own vocabulary of camera moves (the words directors use).
CAMERA: Dict[str, str] = {
    "dolly_in": "slow dolly-in toward the subject",
    "dolly_out": "slow dolly-out revealing the place",
    "crane_up": "crane up from ground level to a high wide view",
    "orbit": "smooth 180-degree orbit around the subject",
    "whip_pan": "fast whip pan with motion blur into the next beat",
    "fpv": "FPV drone dive through the scene",
    "handheld": "close handheld camera, light natural shake",
    "rack_focus": "rack focus from foreground detail to the subject",
    "bullet_time": "frozen-moment bullet-time move around the action",
    "top_down": "locked top-down overhead shot",
    "push_low": "low-angle push-in, hero framing",
    "tracking": "side tracking shot keeping pace with the subject",
}

BEATS = ("gancho", "subida", "giro", "remate")


class CineError(RuntimeError):
    """Plain words for the owner."""


@dataclass
class Shot:
    beat: str
    action: str
    camera: str = "dolly_in"
    lens: str = "35mm"
    light: str = LIGHT
    seconds: int = 5

    def prompt(self, look: str = "") -> str:
        move = CAMERA.get(self.camera, self.camera)
        parts = [
            self.action.strip().rstrip("."),
            f"camera: {move}",
            f"{self.lens} lens",
            self.light,
            look or "cinematic color grade, film grain, shallow depth of field",
            "no text, no logos, no watermark",
        ]
        return ". ".join(p for p in parts if p) + "."


@dataclass
class Film:
    id: str
    idea: str
    aspect: str
    look: str
    shots: List[Shot] = field(default_factory=list)
    engine: str = ""
    files: List[str] = field(default_factory=list)
    output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["shots"] = [asdict(s) for s in self.shots]
        return out


def home() -> Path:
    base = os.environ.get("OPENJARVIS_HOME") or str(Path.home() / ".openjarvis")
    return Path(base) / "cine_ia"


# -- the director --------------------------------------------------------------------


def _aspect(platform: str) -> str:
    p = (platform or "").lower()
    if any(w in p for w in ("youtube largo", "cine", "16:9", "horizontal", "pelicula")):
        return "16:9"
    if any(w in p for w in ("cuadrado", "1:1", "feed")):
        return "1:1"
    return "9:16"  # Reels, TikTok, Shorts, stories


def _fallback_shots(idea: str, n: int) -> List[Shot]:
    """A sound four-beat film when no model answers (never empty)."""
    moves = ["push_low", "tracking", "whip_pan", "crane_up", "orbit", "dolly_in"]
    actions = {
        "gancho": f"Striking opening image that sets up: {idea}",
        "subida": f"The stakes rise: the key moment of {idea}",
        "giro": f"An unexpected turn in {idea}",
        "remate": f"The payoff, a memorable final image of {idea}",
    }
    shots = []
    for i in range(n):
        beat = BEATS[min(i, len(BEATS) - 1)] if i < n - 1 else "remate"
        shots.append(
            Shot(beat=beat, action=actions[beat], camera=moves[i % len(moves)])
        )
    return shots


def brief(
    idea: str,
    *,
    audience: str = "",
    platform: str = "reels",
    brand: str = "",
    shots: int = 4,
    ask: Optional[Callable[[str], str]] = None,
) -> Film:
    """The shot list for *idea*, made for this audience, platform and brand."""
    if not idea.strip():
        raise CineError("Dígame la idea o la historia del video.")
    n = max(1, min(MAX_SHOTS, int(shots or 4)))
    film = Film(
        id=uuid.uuid4().hex[:10], idea=idea.strip(), aspect=_aspect(platform), look=""
    )
    moves = ", ".join(CAMERA)
    prompt = (
        "You are a film director for social media. Turn the idea into a short "
        f"film of exactly {n} shots with a hook, a rise, a turn and a payoff. "
        f"Audience: {audience or 'general'}. Platform: {platform}. "
        f"Brand or personal style: {brand or 'none'}. "
        "Each shot shows ONE clear action a video model can film (no text on "
        f"screen). Pick camera from: {moves}. Answer only JSON: "
        '{"look": "one line color and mood", "shots": [{"beat": "gancho|subida|'
        'giro|remate", "action": "...", "camera": "...", "lens": "24mm|35mm|50mm|'
        '85mm", "light": "...", "seconds": 4-8}]}\n'
        f"Idea: {idea.strip()}"
    )
    raw = ""
    try:
        if ask is None:
            from openjarvis.creator.llm import ask as ask_model

            raw = ask_model(prompt)
        else:
            raw = ask(prompt)
    except Exception:  # noqa: BLE001 — no model: the four-beat fallback
        raw = ""
    data = _json(raw)
    made: List[Shot] = []
    for s in (data.get("shots") if isinstance(data, dict) else None) or []:
        if not isinstance(s, dict) or not str(s.get("action") or "").strip():
            continue
        cam = str(s.get("camera") or "dolly_in")
        try:
            secs = int(s.get("seconds") or 5)
        except (TypeError, ValueError):
            secs = 5
        made.append(
            Shot(
                beat=str(s.get("beat") or "subida"),
                action=str(s["action"])[:400],
                camera=cam if cam in CAMERA else "dolly_in",
                lens=str(s.get("lens") or "35mm")[:12],
                light=str(s.get("light") or LIGHT)[:160],
                seconds=max(4, min(8, secs)),
            )
        )
    film.shots = made[:n] or _fallback_shots(idea.strip(), n)
    if isinstance(data, dict):
        film.look = str(data.get("look") or "")[:200]
    return film


def _json(text: str) -> Any:
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0) if m else text)
    except (ValueError, TypeError):
        return {}


# -- the Higgsfield connector -------------------------------------------------------------


def _hub() -> Any:
    from openjarvis.mcp.hub import get_hub

    return get_hub()


def connector(hub: Any = None) -> str:
    """The id of the owner's connected Higgsfield connector, or ""."""
    try:
        hub = hub or _hub()
        servers = hub.list()
    except Exception:  # noqa: BLE001 — no hub: no connector
        return ""
    for s in servers:
        name = f"{s.get('directory_id', '')} {s.get('name', '')} {s.get('id', '')}"
        if SERVER in name.lower() and s.get("connected") and s.get("enabled", True):
            return str(s["id"])
    return ""


def _result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, default=str)
    parts = []
    if result.get("structuredContent"):
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("text"):
            parts.append(str(item["text"]))
    return "\n".join(parts) or json.dumps(result, ensure_ascii=False, default=str)


_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
_VIDEO_URL = re.compile(
    r"https://[^\s\"'<>]+?\.(?:mp4|mov|webm)(?:\?[^\s\"'<>]*)?", re.I
)


def _job_ids(text: str) -> List[str]:
    data = _json(text)
    ids: List[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if (
                    k in ("job_id", "jobId", "id")
                    and isinstance(v, str)
                    and _UUID.fullmatch(v)
                ):
                    ids.append(v)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)
    if not ids and "job" in text.lower():
        ids = _UUID.findall(text)
    seen: List[str] = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    return seen


def _connect_hint() -> str:
    return (
        "Para usar el mercado de Higgsfield con sus créditos, conecte su cuenta: "
        "Conectores → Higgsfield → Conectar (inicia sesión en su página)."
    )


def catalog(
    query: str = "", *, hub: Any = None, limit: int = 12
) -> List[Dict[str, str]]:
    """Presets, effects and motion from the Higgsfield marketplace."""
    hub = hub or _hub()
    sid = connector(hub)
    if not sid:
        raise CineError(_connect_hint())
    args: Dict[str, Any] = {"limit": max(1, min(50, limit))}
    if query.strip():
        args["query"] = query.strip()[:200]
    data = _json(_result_text(hub.call(sid, "get_presets", args)))
    items: List[Any] = []
    if isinstance(data, dict):
        for key in ("presets", "items", "results", "data"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
    out = []
    for it in items:
        if isinstance(it, dict):
            out.append({
                "id": str(it.get("id") or it.get("slug") or ""),
                "nombre": str(it.get("name") or it.get("title") or ""),
                "tipo": str(it.get("type") or it.get("category") or ""),
            })  # fmt: skip
    return [o for o in out if o["id"] or o["nombre"]]


def _params(
    shot: Shot, film: Film, model: str, *, cost: bool = False
) -> Dict[str, Any]:
    p: Dict[str, Any] = {
        "model": model,
        "prompt": shot.prompt(film.look),
        "aspect_ratio": film.aspect,
        "duration": shot.seconds,
    }
    if cost:
        p["get_cost"] = True
    return {"params": p, "context": "short cinematic social video, one shot"}


def _model(film: Film) -> str:
    chosen = os.environ.get("SERGIO_CINE_MODELO", "").strip()
    if chosen:
        return chosen
    return MULTI_SHOT_MODEL if len(film.shots) > 4 else DEFAULT_MODEL


def cost(film: Film, *, hub: Any = None, model: str = "") -> str:
    """What Higgsfield says the shots cost, before anything is spent."""
    hub = hub or _hub()
    sid = connector(hub)
    if not sid:
        return (
            "Sin Higgsfield conectado: se usará el video IA de Sergio (Veo o fal.ai)."
        )
    model = model or _model(film)
    lines = []
    for i, shot in enumerate(film.shots, 1):
        text = _result_text(
            hub.call(sid, "generate_video", _params(shot, film, model, cost=True))
        )
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:credits|créditos)", text, re.I)
        nums = re.findall(r'"(?:cost|credits|price)"\s*:\s*(\d+(?:\.\d+)?)', text)
        val = m.group(1) if m else (nums[0] if nums else "?")
        lines.append(f"Toma {i}: {val} créditos")
    return "\n".join(lines)


def _download(url: str, out: Path) -> str:
    import httpx

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            with out.open("wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
    return str(out)


def _higgsfield_shot(
    hub: Any,
    sid: str,
    shot: Shot,
    film: Film,
    out: Path,
    *,
    model: str,
    sleep: Callable[[float], None],
    download: Callable[[str, Path], str],
) -> str:
    text = _result_text(hub.call(sid, "generate_video", _params(shot, film, model)))
    urls = _VIDEO_URL.findall(text)
    if urls:
        return download(urls[0], out)
    jobs = _job_ids(text)
    if not jobs:
        raise CineError(f"Higgsfield no inició la toma: {text[:200]}")
    start = time.monotonic()
    while time.monotonic() - start < WAIT_LIMIT:
        waited = _result_text(hub.call(
            sid, "jobs_wait",
            {"jobs": [{"index": 0, "job_id": jobs[0]}], "timeout_seconds": 15},
            approved=True,  # waiting only reads; it spends nothing
        ))  # fmt: skip
        if re.search(r'"status"\s*:\s*"(failed|error|nsfw|canceled)"', waited, re.I):
            raise CineError("Higgsfield no pudo hacer esa toma.")
        urls = _VIDEO_URL.findall(waited)
        if urls:
            return download(urls[0], out)
        sleep(3.0)
    raise CineError("Higgsfield tardó demasiado en una toma.")


def _join(files: List[str], out: Path) -> str:
    if len(files) == 1:
        shutil.copyfile(files[0], out)
        return str(out)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return files[0]
    listing = out.with_suffix(".txt")
    listing.write_text(
        "".join(f"file '{Path(f).as_posix()}'\n" for f in files), "utf-8"
    )
    cmd = [
        ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(listing), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264",
        "-preset", "medium", "-crf", "18", "-an", str(out),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, timeout=600)
    return str(out)


def _save(film: Film, folder: Path) -> None:
    (folder / "plan.json").write_text(
        json.dumps(film.to_dict(), ensure_ascii=False, indent=2), "utf-8"
    )


def render(
    film: Film,
    *,
    hub: Any = None,
    root: Optional[Path] = None,
    model: str = "",
    provider: Optional[Callable[[str, Path, int, str], str]] = None,
    sleep: Callable[[float], None] = time.sleep,
    download: Optional[Callable[[str, Path], str]] = None,
    join: Callable[[List[str], Path], str] = _join,
) -> Film:
    """Make every shot, join them, and save the plan next to the film."""
    if not film.shots:
        raise CineError("La película no tiene tomas.")
    folder = (root or home()) / film.id
    folder.mkdir(parents=True, exist_ok=True)
    sid = ""
    if provider is None:
        try:
            hub = hub or _hub()
            sid = connector(hub)
        except Exception:  # noqa: BLE001 — no hub: Sergio's own AI video
            sid = ""
    film.engine = "Higgsfield" if sid else "video IA de Sergio"
    model = model or _model(film)
    download = download or _download
    problems = []
    for i, shot in enumerate(film.shots, 1):
        out = folder / f"toma_{i:02d}.mp4"
        try:
            if sid:
                path = _higgsfield_shot(
                    hub,
                    sid,
                    shot,
                    film,
                    out,
                    model=model,
                    sleep=sleep,
                    download=download,
                )
            else:
                from openjarvis.video_essay import aivideo

                path = aivideo.generate(
                    shot.prompt(film.look), out, shot.seconds, film.aspect,
                    provider=provider,
                )  # fmt: skip
            film.files.append(str(path))
        except Exception as exc:  # noqa: BLE001 — keep the other shots
            problems.append(f"toma {i}: {str(exc)[:120]}")
    _save(film, folder)
    if not film.files:
        raise CineError("No salió ninguna toma. " + "; ".join(problems))
    film.output = join(film.files, folder / "pelicula.mp4")
    _save(film, folder)
    return film


__all__ = [
    "CAMERA",
    "CineError",
    "Film",
    "Shot",
    "brief",
    "catalog",
    "connector",
    "cost",
    "render",
]

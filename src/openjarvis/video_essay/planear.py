"""Planning a video with a creator: the script, an animatic and the shot list.

The owner (3 Nov 2026): «Sergio ayudará al usuario a planear videos: creará una
animación y un guion de cómo debería ser el video; el usuario simplemente lo
convierte a videos reales y Sergio lo edita».

1. **The plan** (a model, from the idea and, when chosen, the inspiration video
   studied by the school): hook, beats and every shot with its length, kind
   (to camera, b-roll, product, screen, text), framing, camera move, what is
   seen, what is said, words on screen, sound and how to film it.
2. **The animatic**: one storyboard frame per shot (drawn by the image model as
   a pencil storyboard, or drawn here when there is none), each held for its
   real length with its camera move, the line under it and a click on each
   cut, so the creator sees and hears the rhythm before filming.
3. **The shot list**, in the chat card: what to film, in order, with tips.
4. **The edit** (``montaje.py``): the creator uploads the takes and Sergio cuts
   them to the plan.
"""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

KINDS = ("cara", "broll", "producto", "pantalla", "texto")
KIND_NAMES = {"cara": "A cámara", "broll": "Recurso (b-roll)", "producto": "Producto", "pantalla": "Pantalla",
              "texto": "Texto en pantalla"}  # fmt: skip
MAX_SHOTS = 24
FONTS = Path(__file__).parent / "fonts"

PLAN_PROMPT = """You are a senior content director planning a {fmt} video for a professional creator \
who will FILM it themselves. Idea: {idea}
Length: about {seconds} seconds. {inspiration}
Write the plan as a director's shot list that a creator can film with a phone. Rules:
- A hook in the first 1.5 seconds (a result, a contradiction or a question shown, not explained).
- Shots of 0.8-4 s for vertical shorts, 2-8 s for horizontal; vary framing every cut.
- Each shot: kind (one of {kinds}), framing (extreme close-up, close-up, medium, wide), camera move \
(static, push in, pull out, pan, handheld follow, top shot), what is seen, the exact words said in it (may be \
empty), words on screen (max 5 words, may be empty), sound (whoosh, hit, riser, boom, \
reverse swell, glitch, shutter, swipe, silence, music up…) and one \
practical filming tip (light, angle, where to stand).
- The words said across shots form a tight script ({wps:.1f} words per second at most).
Answer ONLY JSON:
{{"titulo": "...", "gancho": "...", "musica": "mood and tempo", "notas": ["edit note", "..."],
 "tomas": [{{"segundos": 2.0, "tipo": "cara", "encuadre": "...", "movimiento": "...", "que_se_ve": "...",
 "dice": "...", "texto": "...", "sonido": "...", "consejo": "..."}}]}}"""


def home() -> Path:
    from openjarvis.core.config import get_config_dir

    path = Path(get_config_dir()) / "planes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def folder(pid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{24}", pid or ""):
        raise KeyError(pid)
    return home() / pid


def load(pid: str) -> Dict[str, Any]:
    return json.loads((folder(pid) / "plan.json").read_text("utf-8"))


def save(pid: str, data: Dict[str, Any]) -> None:
    (folder(pid) / "plan.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), "utf-8"
    )


def clean_plan(raw: Dict[str, Any], seconds: float) -> Dict[str, Any]:
    """The model's plan, checked: known kinds, sane lengths, at most 24 shots,
    and the lengths scaled to the asked total."""
    shots = []
    for t in (raw.get("tomas") or [])[:MAX_SHOTS]:
        kind = str(t.get("tipo") or "broll").lower()
        kind = next((k for k in KINDS if k in kind), "broll")
        try:
            secs = float(t.get("segundos") or 2)
        except (TypeError, ValueError):
            secs = 2.0
        shots.append({
            "n": len(shots) + 1, "segundos": max(0.6, min(12.0, secs)), "tipo": kind,
            "encuadre": str(t.get("encuadre") or "")[:60], "movimiento": str(t.get("movimiento") or "fija")[:60],
            "que_se_ve": str(t.get("que_se_ve") or "")[:300], "dice": str(t.get("dice") or "")[:400],
            "texto": str(t.get("texto") or "")[:60], "sonido": str(t.get("sonido") or "")[:60],
            "consejo": str(t.get("consejo") or "")[:200], "archivo": "",
        })  # fmt: skip
    if not shots:
        raise ValueError("el plan no trae tomas")
    total = sum(s["segundos"] for s in shots)
    if seconds and abs(total - seconds) / seconds > 0.25:
        k = seconds / total
        for s in shots:
            s["segundos"] = round(max(0.6, s["segundos"] * k), 2)
    return {
        "titulo": str(raw.get("titulo") or "Video")[:120],
        "gancho": str(raw.get("gancho") or "")[:300],
        "musica": str(raw.get("musica") or "")[:120],
        "notas": [str(n)[:200] for n in (raw.get("notas") or [])][:8],
        "tomas": shots,
    }


# -- the storyboard frames -----------------------------------------------------------------


def _font(name: str, size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default()


def draw_frame(
    shot: Dict[str, Any], size: tuple, picture: Optional[bytes] = None
) -> Any:
    """One storyboard frame: the picture (or a simple drawing of the framing)
    and a strip with the shot number, length, framing, move and the line."""
    import io

    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGB", (w, h), (244, 241, 236))
    d = ImageDraw.Draw(img)
    if picture:
        try:
            pic = Image.open(io.BytesIO(picture)).convert("RGB")
            pic.thumbnail((w, h))
            img.paste(pic, ((w - pic.width) // 2, (h - pic.height) // 2))
        except Exception:  # noqa: BLE001
            picture = None
    if not picture:  # a quick drawing of what the frame holds
        ink = (40, 34, 30)
        enc = (shot.get("encuadre") or "").lower()
        scale = (
            0.9 if "extreme" in enc or "detalle" in enc
            else 0.7 if "close" in enc or "primer" in enc
            else 0.5 if "medium" in enc or "medio" in enc
            else 0.3
        )  # fmt: skip
        cx, base = w // 2, int(h * 0.82)
        if shot["tipo"] == "cara":
            r = int(min(w, h) * 0.16 * scale / 0.5)
            d.ellipse(
                [cx - r, base - int(3.2 * r), cx + r, base - int(1.2 * r)],
                outline=ink,
                width=6,
            )
            d.arc(
                [
                    cx - int(2.2 * r),
                    base - int(1.1 * r),
                    cx + int(2.2 * r),
                    base + int(2.5 * r),
                ],
                180,
                360,
                fill=ink,
                width=6,
            )
        elif shot["tipo"] == "producto":
            bw, bh = int(w * 0.22 * scale / 0.5), int(h * 0.3 * scale / 0.5)
            d.rounded_rectangle(
                [cx - bw // 2, base - bh, cx + bw // 2, base],
                radius=18,
                outline=ink,
                width=6,
            )
            d.line([int(w * 0.1), base, int(w * 0.9), base], fill=ink, width=4)
        elif shot["tipo"] == "pantalla":
            pw, ph = int(w * 0.5), int(h * 0.42)
            d.rounded_rectangle(
                [cx - pw // 2, int(h * 0.2), cx + pw // 2, int(h * 0.2) + ph],
                radius=24,
                outline=ink,
                width=6,
            )
        elif shot["tipo"] == "texto":
            word = (shot.get("texto") or shot.get("dice") or "TEXTO").upper()[:18]
            f = _font("Anton-Regular.ttf", max(40, int(w * 0.11)))
            tw = d.textlength(word, font=f)
            d.text(((w - tw) / 2, h * 0.35), word, fill=ink, font=f)
        else:  # b-roll: a horizon, a sun and a path
            d.line([0, int(h * 0.6), w, int(h * 0.56)], fill=ink, width=5)
            d.ellipse(
                [
                    int(w * 0.68),
                    int(h * 0.18),
                    int(w * 0.8),
                    int(h * 0.18) + int(w * 0.12),
                ],
                outline=ink,
                width=5,
            )
            d.line([int(w * 0.45), h, int(w * 0.52), int(h * 0.58)], fill=ink, width=4)
        if shot.get("texto") and shot["tipo"] != "texto":
            f = _font("InterDisplay-Black.ttf", max(28, int(w * 0.06)))
            word = shot["texto"].upper()[:24]
            tw = d.textlength(word, font=f)
            d.text(((w - tw) / 2, h * 0.08), word, fill=(122, 31, 61), font=f)
    # the strip: number, length, framing and move; the line said
    strip = int(h * 0.2)
    d.rectangle([0, h - strip, w, h], fill=(12, 10, 9))
    small = _font("InterDisplay-Bold.ttf", max(18, int(w * 0.03)))
    body = _font("InterDisplay-Medium.ttf", max(18, int(w * 0.032)))
    head = f"TOMA {shot['n']} · {shot['segundos']:.1f} s · {KIND_NAMES[shot['tipo']]}"
    move = " · ".join(x for x in (shot.get("encuadre"), shot.get("movimiento")) if x)
    d.text(
        (int(w * 0.05), h - strip + int(strip * 0.1)),
        head,
        fill=(245, 242, 238),
        font=small,
    )
    if move:
        d.text(
            (int(w * 0.05), h - strip + int(strip * 0.28)),
            move,
            fill=(184, 146, 90),
            font=small,
        )
    said = shot.get("dice") or shot.get("que_se_ve") or ""
    lines = textwrap.wrap(
        f"«{said}»" if shot.get("dice") else said,
        width=max(20, int(w / (body.size * 0.55))),
    )[:3]
    for i, ln in enumerate(lines):
        d.text(
            (int(w * 0.05), h - strip + int(strip * (0.48 + 0.16 * i))),
            ln,
            fill=(245, 242, 238),
            font=body,
        )
    return img


def _picture(
    shot: Dict[str, Any], look: str, vertical: bool, gen: Callable[[str], bytes]
) -> Optional[bytes]:
    prompt = (
        f"Storyboard frame, loose pencil and ink sketch on warm paper, grey wash shading, no colour, no text. "
        f"{'Vertical 9:16' if vertical else 'Horizontal 16:9'} frame. Shot: {shot.get('encuadre')}, "
        f"{shot.get('movimiento')}. Shows: {shot.get('que_se_ve')}. {look}"
    )
    try:
        return gen(prompt)
    except Exception:  # noqa: BLE001 — drawn here instead
        return None


def animatic(plan: Dict[str, Any], out: Path, *, vertical: bool, ffmpeg: str,
             gen: Optional[Callable[[str], bytes]] = None) -> Path:  # fmt: skip
    """The storyboard as a video: each frame for its shot's length, with its
    move, and a soft click on each cut (the rhythm the creator will cut to)."""
    import numpy as np

    from openjarvis.video_essay import audio

    size = (720, 1280) if vertical else (1280, 720)
    work = out.parent / "cuadros"
    work.mkdir(parents=True, exist_ok=True)
    shots = plan["tomas"]
    pics: List[Optional[bytes]] = [None] * len(shots)
    if gen is not None:
        with ThreadPoolExecutor(max_workers=4) as pool:
            pics = list(
                pool.map(
                    lambda s: _picture(s, plan.get("look", ""), vertical, gen), shots
                )
            )
    clips = []
    for shot, pic in zip(shots, pics):
        frame = work / f"toma-{shot['n']:02d}.png"
        draw_frame(shot, size, pic).save(frame)
        shot["cuadro"] = frame.name
        dur = shot["segundos"]
        frames = max(2, int(round(dur * 25)))
        mv = (shot.get("movimiento") or "").lower()
        if "push" in mv or "acerc" in mv or "zoom in" in mv:
            z = f"zoom='1+0.12*on/{frames}'"
        elif "pull" in mv or "alej" in mv or "zoom out" in mv:
            z = f"zoom='1.12-0.12*on/{frames}'"
        else:
            z = "zoom='1.04'"
        x = f"x='iw/2-(iw/zoom/2)+({'1' if 'pan' in mv or 'paneo' in mv else '0'})*on*2'"
        clip = work / f"toma-{shot['n']:02d}.mp4"
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(frame), "-t", f"{dur:.2f}",
             "-vf", f"zoompan={z}:{x}:y='ih/2-(ih/zoom/2)':d={frames}:s={size[0]}x{size[1]}:fps=25,format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(clip)],
            check=True, capture_output=True, timeout=300,
        )  # fmt: skip
        clips.append(clip)
    listing = work / "lista.txt"
    listing.write_text("".join(f"file '{c.name}'\n" for c in clips), "utf-8")
    silent = work / "mudo.mp4"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                    str(silent)], check=True, capture_output=True, timeout=300)  # fmt: skip
    total = sum(s["segundos"] for s in shots)
    cuts = np.cumsum([0] + [s["segundos"] for s in shots[:-1]])
    track = audio.effects_track([(float(t), "click") for t in cuts[1:]], total + 0.5)
    clicks = work / "cortes.wav"
    clicks.write_bytes(audio.write_wav(track * 0.6))
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(silent), "-i", str(clicks), "-c:v", "copy", "-c:a", "aac",
                    "-shortest", "-movflags", "+faststart", str(out)],
                   check=True, capture_output=True, timeout=300)  # fmt: skip
    return out


# -- the whole planning step -----------------------------------------------------------------


def create(idea: str, *, seconds: float = 45, vertical: bool = True, reference: str = "",
           ask: Optional[Callable[..., str]] = None, gen: Optional[Callable[[str], bytes]] = None,
           ffmpeg: Optional[str] = None) -> Dict[str, Any]:  # fmt: skip
    """The plan, its animatic and the shot list, saved under a random id."""
    from openjarvis.video_essay import script

    if ask is None:
        from openjarvis.creator import llm

        def ask(p: str, **kw: Any) -> str:
            return llm.ask(p, effort="medium", **kw)

    inspiration = ""
    if reference:
        inspiration = f"Take as STYLE and INSPIRATION (pacing, framing, energy; never copy its content): {reference}."
        try:
            from openjarvis.video_essay import escuela

            bp = escuela.find(reference)
            if bp:
                inspiration += "\nMeasured from it: " + escuela.ficha(reference)[:900]
        except Exception:  # noqa: BLE001 — the link alone still guides
            pass
    try:  # the measured Shorts formats of his references (viral.py)
        from openjarvis.video_essay import viral

        inspiration += "\n" + viral.guide(idea, "", vertical=vertical)
    except Exception:  # noqa: BLE001
        pass
    raw = ask(
        PLAN_PROMPT.format(fmt="vertical 9:16 short" if vertical else "horizontal 16:9", idea=idea[:600],
                           seconds=int(seconds), inspiration=inspiration, kinds=", ".join(KINDS),
                           wps=getattr(script, "WORDS_PER_SECOND", 2.6)),
        json_mode=True, max_tokens=6000,
    )  # fmt: skip
    plan = clean_plan(json.loads(raw), seconds)
    pid = secrets.token_hex(12)
    folder(pid).mkdir(parents=True, exist_ok=True)
    plan.update(id=pid, idea=idea, vertical=vertical, referencia=reference, creado=time.time(),
                estado="animando", montaje=None)  # fmt: skip
    save(pid, plan)
    if ffmpeg is None:
        from openjarvis.video_essay import render

        ffmpeg = render.ffmpeg()
    if gen is None:
        try:
            from openjarvis.creator import studio

            gen = studio.generate_image
        except Exception:  # noqa: BLE001
            gen = None
    try:
        animatic(
            plan,
            folder(pid) / "animatic.mp4",
            vertical=vertical,
            ffmpeg=ffmpeg,
            gen=gen,
        )
        plan["estado"] = "listo"
        plan["animatic"] = f"/v1/creator/plan/{pid}/animatic.mp4"
    except Exception as exc:  # noqa: BLE001 — the shot list still works without it
        plan["estado"] = "listo"
        plan["animatic_error"] = str(exc)[:200]
    save(pid, plan)
    return plan


def card(plan: Dict[str, Any]) -> str:
    rows = [f"{s['n']}. {s['segundos']:.1f} s · {KIND_NAMES[s['tipo']]} · {s['encuadre']}: {s['que_se_ve'][:80]}"
            for s in plan["tomas"]]  # fmt: skip
    return (
        f"Plan «{plan['titulo']}»: {len(plan['tomas'])} tomas, {sum(s['segundos'] for s in plan['tomas']):.0f} s. "
        f"Gancho: {plan['gancho']}\n"
        + "\n".join(rows[:30])
        + f"\n\n[[plan:{plan['id']}]]"
    )


__all__ = [
    "KINDS",
    "animatic",
    "card",
    "clean_plan",
    "create",
    "draw_frame",
    "folder",
    "load",
    "save",
]

"""Only one job: thumbnails that people click and can read when they are tiny.

From a video (or a picture), by code:

1. **The frame.** Up to 24 frames of the video are sampled and scored:
   sharp (edges), contrast, colour, and a face (people click faces). Three
   different moments win; never two from the same second.
2. **The words.** 2 to 4 words, big, in the impact letter, from the given
   text or from the strongest words of the title (never a whole sentence).
3. **Composition.** The words go to the side the subject leaves free (rule
   of thirds, saliency of :mod:`video_essay.color`), never over a face; one
   key word in the accent colour (the complement of the frame, or his brand).
4. **The phone test.** Each variant is shrunk to 168×94 (the size in a list
   on a phone) and the words' contrast is measured there; if it fails, the
   words go on a solid block. The score says why each one won.

Three variants (side, bottom, block) so the owner can test them with the
platform's own A/B test. Nothing is uploaded.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SIZE = (1280, 720)
SMALL = (168, 94)
_STOP = set(
    "el la los las un una unos unas de del al y o u en con por para que como mas muy su sus mi "
    "tu se lo le es son fue era the a an of and or to in on for with is are this that how why "
    "what your you my".split()
)


def _plain(w: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", w.lower()).encode("ascii", "ignore").decode()


def words_from(title: str, limit: int = 4) -> List[str]:
    """The 2–4 words of *title* worth putting on the picture (numbers first)."""
    toks = re.findall(r"[\wÁÉÍÓÚÑáéíóúñ$%€]+", title or "")
    keep = [t for t in toks if _plain(t) not in _STOP]
    nums = [t for t in keep if re.search(r"\d", t)]
    rest = [t for t in keep if t not in nums]
    rest.sort(key=lambda t: -len(t))
    chosen = (nums[:1] + rest)[:limit]
    order = {t: i for i, t in enumerate(toks)}
    return sorted(chosen, key=lambda t: order.get(t, 0)) or toks[:limit]


def _duration(path: Path) -> float:
    exe = shutil.which("ffprobe")
    if not exe:
        return 0.0
    try:
        out = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration", "-of",
                              "default=nw=1:nk=1", str(path)], capture_output=True, text=True, timeout=30)  # fmt: skip
        return float(out.stdout.strip() or 0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0.0


def frames(path: Path, n: int = 24) -> List[Tuple[float, Any]]:
    """(second, picture) samples of a video, or the picture itself."""
    from PIL import Image

    from openjarvis.video_essay.sources import frame_of

    if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        return [(0.0, Image.open(path).convert("RGB"))]
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("falta ffmpeg para leer el video")
    dur = _duration(path) or 10.0
    out = []
    for i in range(n):
        at = dur * (0.04 + 0.92 * i / max(1, n - 1))
        out.append((round(at, 2), frame_of(str(path), ffmpeg, at)))
    return out


def score_frame(img: Any) -> Dict[str, float]:
    """How good a frame is for a thumbnail (higher is better)."""
    import numpy as np

    from openjarvis.video_essay import color

    small = img.convert("RGB").resize((256, 144))
    g = np.asarray(small.convert("L"), dtype=np.float32) / 255
    sharp = float(
        (np.abs(np.diff(g, axis=0)).mean() + np.abs(np.diff(g, axis=1)).mean()) * 8
    )
    contrast = float(g.std() * 4)
    rgb = np.asarray(small, dtype=np.float32)
    rg, yb = rgb[..., 0] - rgb[..., 1], 0.5 * (rgb[..., 0] + rgb[..., 1]) - rgb[..., 2]
    colourful = float(
        (np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean())) / 100
    )
    big = np.asarray(img.convert("L").resize((640, 360)))
    face = 1.0 if color._faces(big) else 0.0
    dark = (
        1.0 if g.mean() < 0.12 or g.mean() > 0.92 else 0.0
    )  # black or blown-out frame
    total = (
        min(sharp, 1.5)
        + min(contrast, 1.2)
        + min(colourful, 1.2)
        + 1.2 * face
        - 2.0 * dark
    )
    return {"total": round(total, 3), "nitidez": round(sharp, 2), "contraste": round(contrast, 2),
            "color": round(colourful, 2), "cara": face}  # fmt: skip


def pick(
    samples: Sequence[Tuple[float, Any]], k: int = 3
) -> List[Tuple[float, Any, Dict[str, float]]]:
    scored = sorted(
        ((t, im, score_frame(im)) for t, im in samples), key=lambda r: -r[2]["total"]
    )
    out: List[Tuple[float, Any, Dict[str, float]]] = []
    for row in scored:
        if all(abs(row[0] - o[0]) >= 1.0 for o in out):
            out.append(row)
        if len(out) >= k:
            break
    return out


def _lines(words: List[str], f: Any, width: int) -> List[str]:
    lines, cur = [], ""
    for w in words:
        if cur and f.getlength(cur + " " + w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])


def compose(
    img: Any, words: List[str], layout: str, accent: Optional[Sequence[int]] = None
) -> Tuple[Any, Dict[str, Any]]:
    """One thumbnail: *layout* is «lado» (free side), «abajo» or «bloque»."""
    from PIL import Image, ImageDraw, ImageEnhance

    from openjarvis.video_essay import color
    from openjarvis.video_essay.render import font

    base = ImageEnhance.Contrast(img.convert("RGB").resize(SIZE)).enhance(1.12)
    base = ImageEnhance.Color(base).enhance(1.15)
    comp = color.composition(base)
    acc = tuple(accent[:3]) if accent else color.accent_for(base)
    words = [w.upper() for w in words][:4]
    longest = max(words, key=len) if words else ""
    side = comp["free_side"] if layout == "lado" else "lower"
    width = 600 if side in ("left", "right") else 1160
    size = 170
    f = font("black", size)
    while size > 70 and (
        len(_lines(words, f, width)) > 3 or any(f.getlength(w) > width for w in words)
    ):
        size -= 10
        f = font("black", size)
    lines = _lines(words, f, width)
    block_h = int(len(lines) * size * 1.02)
    x = 60 if side != "right" else SIZE[0] - 60 - width
    y = (
        (SIZE[1] - block_h) // 2
        if side in ("left", "right")
        else SIZE[1] - 50 - block_h
    )
    zone = {"left": "left", "right": "right"}.get(side, "lower")
    check = color.legible(base, zone, acc)
    boxed = layout == "bloque" or bool(check["box"])
    shade = Image.new("L", (1, SIZE[1]))
    if not boxed and side == "lower":
        for yy in range(SIZE[1]):
            shade.putpixel((0, yy), int(max(0, (yy - 300) / 420) * 190))
        base.paste((0, 0, 0), (0, 0, *SIZE), shade.resize(SIZE))
    d = ImageDraw.Draw(base)
    key = longest.upper()
    for line in lines:
        lw = int(f.getlength(line))
        lx = x if side != "right" else x + width - lw
        if boxed:
            d.rectangle(
                (lx - 18, y - 8, lx + lw + 18, y + int(size * 1.0)),
                fill=acc if line == lines[0] else (12, 12, 12),
            )
        for word in line.split():
            ww = f.getlength(word + " ")
            fill = (255, 255, 255)
            if not boxed and word == key:
                fill = acc
            elif boxed and line == lines[0]:
                fill = color.text_on_block(acc)
            if not boxed:
                d.text(
                    (lx, y),
                    word,
                    font=f,
                    fill=fill,
                    stroke_width=max(4, size // 18),
                    stroke_fill=(0, 0, 0),
                )
            else:
                d.text((lx, y), word, font=f, fill=fill)
            lx += int(ww)
        y += int(size * 1.02)
    return base, {
        "lado": side,
        "bloque": boxed,
        "acento": color.hex_of(acc),
        "tamano_letra": size,
    }


def phone_test(img: Any, zone: str) -> float:
    """The words' contrast when the thumbnail is the size of a phone list."""
    import numpy as np

    from openjarvis.video_essay import color

    tiny = img.resize(SMALL)
    patch = color.region(tiny, zone)
    lum = np.asarray(patch.convert("L"), dtype=np.float32)
    lo, hi = int(np.percentile(lum, 10)), int(np.percentile(lum, 90))
    return round(color.contrast((hi, hi, hi), (lo, lo, lo)), 2)


def crear(
    fuente: str,
    texto: str = "",
    titulo: str = "",
    out_dir: Optional[Path] = None,
    variantes: int = 3,
    acento: str = "",
) -> Dict[str, Any]:
    """Thumbnails for the video or picture at *fuente*; best first."""
    from openjarvis.video_essay import color

    path = Path(fuente).expanduser()
    if not path.exists():
        return {"miniaturas": [], "aviso": f"No encuentro el archivo {path.name}."}
    words = (
        texto.split()
        if texto.strip()
        else words_from(titulo or path.stem.replace("-", " "))
    )[:4]
    if out_dir is None:
        from openjarvis.core.paths import get_config_dir

        out_dir = Path(get_config_dir()) / "estudio" / "miniaturas"
    out_dir.mkdir(parents=True, exist_ok=True)
    best = pick(frames(path), max(1, variantes))
    layouts = ["lado", "abajo", "bloque"]
    brand = color.rgb_of(acento) if acento else None
    made = []
    for i, (at, img, fs) in enumerate(best):
        layout = layouts[i % len(layouts)]
        thumb, info = compose(img, words, layout, brand)
        zone = {"left": "left", "right": "right"}.get(info["lado"], "lower")
        phone = phone_test(thumb, zone)
        out = (
            out_dir
            / f"{re.sub(r'[^a-z0-9]+', '-', _plain(path.stem))[:40]}-{i + 1}.jpg"
        )
        thumb.save(out, quality=92)
        made.append({"archivo": str(out), "segundo": at, "diseno": layout, **info, "cuadro": fs,
                     "contraste_en_telefono": phone, "se_lee_pequena": phone >= 3.0,
                     "puntos": round(fs["total"] + min(phone, 7) / 3, 2)})  # fmt: skip
    made.sort(key=lambda m: -m["puntos"])
    return {"palabras": words, "miniaturas": made,
            "aviso": "Pruebe dos con la prueba A/B de la propia plataforma; no se sube nada."}  # fmt: skip


def texto_de(res: Dict[str, Any]) -> str:
    if not res.get("miniaturas"):
        return res.get("aviso") or "No pude hacer miniaturas."
    lines = [f"Miniaturas con «{' '.join(res['palabras'])}» (la mejor primero):"]
    for m in res["miniaturas"]:
        small = (
            "se lee en el teléfono"
            if m["se_lee_pequena"]
            else "en el teléfono cuesta leerla"
        )
        face = ", con cara" if m["cuadro"]["cara"] else ""
        lines.append(
            f"- {m['archivo']} · segundo {m['segundo']} · {m['diseno']}{face} · {small}"
        )
    lines.append(res["aviso"])
    return "\n".join(lines)


__all__ = [
    "compose",
    "crear",
    "frames",
    "phone_test",
    "pick",
    "score_frame",
    "texto_de",
    "words_from",
]

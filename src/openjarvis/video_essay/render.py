"""Frame by frame: the video essay drawn and encoded.

Each shot has a background (a colour card, a still that moves, or a clip),
a look (black and white, warm, cold), sometimes a frame around it (an old
CRT or film) or a device holding it (an old computer, a phone), and on top
the spoken words appearing as they are said: each one pops in on its own
syllable, one word can stand out in another colour, short lines go big in
capitals. Cuts can flash, whip or fade, and a few frames can glitch.

Frames are drawn with Pillow and numpy and piped to ffmpeg, so it runs on
any computer; a 3-minute 1080p essay takes minutes, the passes of review
around it are what take long.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from openjarvis.video_essay.plan import Shot, Word

FONTS = Path(__file__).parent / "fonts"
FPS = 30
SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
DRAFT_SIZES = {"16:9": (960, 540), "9:16": (540, 960), "1:1": (720, 720)}

PALETTE = {
    "cream": (233, 235, 207),
    "red": (232, 38, 42),
    "navy": (22, 36, 58),
    "black": (11, 11, 11),
    "white": (255, 255, 255),
    "grey": (150, 150, 150),
    "gold": (242, 181, 58),
}


INK = (16, 16, 18)


def ffmpeg() -> str:
    from openjarvis.tools.video_create import ffmpeg_exe

    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("falta ffmpeg (se instala con la actualización de Sergio)")
    return exe


# -- type ---------------------------------------------------------------------------


@lru_cache(maxsize=64)
def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    from openjarvis.video_essay import typo

    if kind in typo.FACES:
        return typo.font(kind, size)
    name = {
        "black": "InterDisplay-Black.ttf",
        "bold": "InterDisplay-Bold.ttf",
        "medium": "InterDisplay-Medium.ttf",
        "italic": "InterDisplay-BoldItalic.ttf",
    }[kind]
    return ImageFont.truetype(str(FONTS / name), size)


@lru_cache(maxsize=4096)
def word_image(
    text: str,
    kind: str,
    size: int,
    rgb: Tuple[int, int, int],
    shadow: bool,
    bg: Optional[Tuple[int, int, int]] = None,
) -> Image.Image:
    """One word, tightly tracked like the reference, with a soft shadow on
    footage so it reads on any picture (or on a block of colour, *bg*)."""
    from openjarvis.video_essay import typo

    f = font(kind, size)
    face = typo.FACES.get(kind)
    track = (face.track if face else -0.045) * size  # tight letter spacing
    widths = [f.getlength(c) for c in text]
    width = int(sum(widths) + track * max(0, len(text) - 1)) + size
    height = int(size * 1.35)
    pad = int(size * 0.35)
    layer = Image.new("RGBA", (width + 2 * pad, height + 2 * pad), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x = float(pad)
    for c, w in zip(text, widths):
        draw.text((x, pad), c, font=f, fill=rgb + (255,))
        x += w + track
    box = layer.getbbox() or (0, 0, 1, 1)
    if shadow:
        alpha = layer.split()[3].filter(ImageFilter.GaussianBlur(size * 0.12))
        shade = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        shade.putalpha(alpha.point(lambda a: int(a * 0.55)))
        shade.alpha_composite(layer)
        layer = shade
    m = shadow_margin(size, shadow)  # the shadow hangs out; the letters set the width
    # same top and bottom for every word, so they share a baseline
    top, bottom = pad, pad + int(size * 1.2)
    word = layer.crop((box[0] - m, top - m, box[2] + m, bottom + m))
    if bg is None:
        return word
    # a block of colour behind the word (the "white on red" of the reference)
    px, py = int(size * 0.16), int(size * 0.02)
    tile = Image.new("RGBA", (word.width + 2 * px, word.height + 2 * py), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle(
        (0, int(size * 0.12), tile.width - 1, tile.height - 1 - int(size * 0.06)),
        radius=max(2, int(size * 0.08)),
        fill=bg + (255,),
    )
    tile.alpha_composite(word, (px, py))
    return tile


def shadow_margin(size: int, shadow: bool) -> int:
    return int(size * 0.3) if shadow else 0


@dataclass
class Placed:
    text: str
    start: float  # seconds into the shot
    x: int
    y: int
    kind: str
    size: int
    rgb: Tuple[int, int, int]
    bg: Optional[Tuple[int, int, int]] = None
    until: float = math.inf  # gone when the next phrase comes in
    lit_rgb: Optional[Tuple[int, int, int]] = None  # its colour while it is said


CHUNK_WORDS = 4  # words on screen at once in a long shot (captions roll)


def chunks_of(texts: List[str], size: int = CHUNK_WORDS) -> List[List[int]]:
    """Word indexes in phrases of at most *size*, cut after punctuation; a
    last phrase of one word joins the one before."""
    out: List[List[int]] = [[]]
    for i, word in enumerate(texts):
        out[-1].append(i)
        if len(out[-1]) >= size or word[-1:] in ",.;:!?…":
            out.append([])
    out = [c for c in out if c]
    if len(out) > 1 and len(out[-1]) == 1 and len(out[-2]) < size + 2:
        tail = out.pop()
        out[-1] += tail
    return out


def _ease_back(p: float) -> float:
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def layout_text(shot: Shot, words: List[Word], size: Tuple[int, int]) -> List[Placed]:
    """Where each on-screen word goes and when it appears.

    Short lines show whole; a long shot's words roll in phrases of a few
    words, each replacing the last in the same place, with the word being
    said lit in the accent colour (karaoke), as the best captions do."""
    w_px, h_px = size
    if shot.text_style == "none":
        return []
    spoken = words[shot.first : shot.last]
    shown = shot.text.split() or [w.text for w in spoken]
    # each shown word appears when it is said (matched in order)
    times: List[float] = []
    j = 0
    for word in shown:
        key = "".join(ch for ch in word.lower() if ch.isalnum())
        found = shot.start
        for k in range(j, len(spoken)):
            if "".join(ch for ch in spoken[k].text.lower() if ch.isalnum()) == key:
                found, j = spoken[k].start, k + 1
                break
        times.append(max(0.0, found - shot.start))
    style = shot.text_style
    on_card = shot.kind == "card"
    rolling = (
        not on_card
        and style in ("pop", "italic", "big_caps")
        and len(shown) > CHUNK_WORDS + 1
    )
    groups = chunks_of(shown) if rolling else [list(range(len(shown)))]
    longest = max(len(g) for g in groups)
    scale = {"pop": 0.072, "big_caps": 0.115, "grey_to_white": 0.05, "italic": 0.062}[
        style
    ]
    if longest <= 2 and style == "pop":
        scale = 0.095
    elif rolling and style == "pop":
        scale = 0.082  # a few words at a time can be bigger
    from openjarvis.video_essay import color, typo

    face = typo.FACES.get(shot.font)
    if face is not None:
        scale *= face.scale
    fsize = max(18, int(min(w_px, h_px * 1.6) * scale))
    kind = (
        shot.font
        if face is not None
        else {
            "pop": "black",
            "big_caps": "black",
            "grey_to_white": "medium",
            "italic": "italic",
        }[style]
    )
    base = PALETTE["white"]
    if on_card and shot.card == "cream":
        base = PALETTE["red"]
    accent = color.rgb_of(shot.accent)
    highlight = "".join(ch for ch in shot.highlight.lower() if ch.isalnum())
    shadow = not on_card
    position = shot.position
    if shot.device != "none" and shot.kind != "card":
        # under the device, never over it
        position = "lower"
        fsize = min(fsize, int(h_px * 0.05))

    def gap_of(a: Optional[tuple], b: tuple) -> float:
        """Space between two words: tight between blocks, a real space
        otherwise (the shadow eats some of it)."""
        if a is None:
            return 0.0
        return fsize * (0.16 if a[4] is not None and b[4] is not None else 0.27)

    corner = position in ("upper_left", "upper_right", "lower_left", "lower_right")
    max_w = w_px * (0.8 if position in ("center", "lower", "upper") else 0.45)
    sung = accent or PALETTE["gold"]  # the colour of the word being said
    entries = []
    for word, t in zip(shown, times):
        text = word.upper() if style == "big_caps" or (face and face.caps) else word
        clean = "".join(ch for ch in word.lower() if ch.isalnum())
        rgb = base
        bg = None
        lit = bool(highlight and clean == highlight)
        if lit:
            rgb = (
                (accent or PALETTE["gold"])
                if not on_card
                else (
                    accent
                    or (PALETTE["red"] if shot.card != "red" else PALETTE["white"])
                )
            )
            if (
                on_card
                and color.contrast(rgb, PALETTE.get(shot.card, PALETTE["black"])) < 3
            ):
                rgb = base  # an accent the card would swallow
            if style != "grey_to_white":
                text = text.upper()
        if shot.box and (lit or not highlight):
            bg = accent or PALETTE["red"]
            rgb = color.text_on_block(bg)
        elif shot.box == "all":
            bg = INK  # the other words on near-black, the highlight stays lit
            rgb = PALETTE["white"]
        karaoke = (
            sung if rolling and not lit and bg in (None, INK) and sung != rgb else None
        )
        img = word_image(text, kind, fsize, rgb, shadow and bg is None, bg)
        width = img.width - 2 * shadow_margin(fsize, shadow and bg is None)
        entries.append((text, width, t, rgb, bg, karaoke))
    line_h = fsize * (1.22 if shot.box else 1.08)
    placed: List[Placed] = []
    for gi, group in enumerate(groups):
        until = times[groups[gi + 1][0]] if gi + 1 < len(groups) else math.inf
        lines: List[list] = [[]]
        line_w = 0.0
        for i in group:
            width = entries[i][1]
            gap = gap_of(lines[-1][-1] if lines[-1] else None, entries[i])
            if lines[-1] and line_w + gap + width > max_w:
                lines.append([])
                line_w, gap = 0.0, 0.0
            line_w += gap + width
            lines[-1].append(entries[i])
        block_h = line_h * len(lines)
        if position in ("upper", "upper_left", "upper_right"):
            top = h_px * (0.14 if position == "upper" else 0.08)
        elif position in ("lower_left", "lower_right"):
            top = h_px * 0.9 - block_h
        elif position == "lower":
            top = h_px * (0.95 if shot.device != "none" else 0.86) - block_h
        else:
            top = (h_px - block_h) / 2
        for li, line in enumerate(lines):
            total = sum(e[1] for e in line) + sum(
                gap_of(a, b) for a, b in zip(line, line[1:])
            )
            if position in ("left", "upper_left", "lower_left"):
                x = w_px * (0.08 if not corner else 0.07)
            elif position in ("right", "upper_right", "lower_right"):
                x = w_px * (0.92 if not corner else 0.93) - total
            else:
                x = (w_px - total) / 2
            y = top + li * line_h
            for k, (text, width, t, rgb, bg, karaoke) in enumerate(line):
                m = shadow_margin(fsize, shadow and bg is None)
                placed.append(
                    Placed(
                        text,
                        t,
                        int(x) - m,
                        int(y) - m,
                        kind,
                        fsize,
                        rgb,
                        bg,
                        until,
                        karaoke,
                    )
                )
                x += width + (gap_of(line[k], line[k + 1]) if k + 1 < len(line) else 0)
    return placed


def draw_text(
    canvas: Image.Image, placed: List[Placed], t: float, style: str, shadow: bool
) -> None:
    visible = [p for p in placed if p.start <= t < p.until]
    said = max((p.start for p in visible), default=-1.0)  # the word being said
    for i, p in enumerate(visible):
        rgb = p.rgb
        if (
            style == "grey_to_white"
            and i < len(visible) - 1
            and rgb == PALETTE["white"]
        ):
            rgb = PALETTE["grey"]
        if p.lit_rgb is not None and p.start == said:
            rgb = p.lit_rgb
        img = word_image(p.text, p.kind, p.size, rgb, shadow and p.bg is None, p.bg)
        prog = min(1.0, (t - p.start) / 0.14)
        if prog < 1.0:
            s = 0.72 + 0.28 * _ease_back(prog)
            w, h = max(1, int(img.width * s)), max(1, int(img.height * s))
            small = img.resize((w, h), Image.BILINEAR)
            if prog < 0.6:
                a = small.split()[3].point(lambda v, k=prog / 0.6: int(v * k))
                small.putalpha(a)
            canvas.alpha_composite(
                small, (p.x + (img.width - w) // 2, p.y + (img.height - h) // 2)
            )
        else:
            canvas.alpha_composite(img, (p.x, p.y))


# -- backgrounds -----------------------------------------------------------------------


def _cover(img: Image.Image, size: Tuple[int, int]) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS)


class Background:
    def frames(self, n: int) -> Iterator[Image.Image]:  # pragma: no cover - interface
        raise NotImplementedError


class Card(Background):
    def __init__(self, rgb: Tuple[int, int, int], size: Tuple[int, int]) -> None:
        self.img = Image.new("RGB", size, rgb)

    def frames(self, n: int) -> Iterator[Image.Image]:
        for _ in range(n):
            yield self.img


class Still(Background):
    """A picture that keeps moving: a slow push, or a punch-in that settles."""

    def __init__(self, path: str, size: Tuple[int, int], effect: str) -> None:
        self.size = size
        self.big = _cover(Image.open(path), (int(size[0] * 1.2), int(size[1] * 1.2)))
        self.effect = effect

    def frames(self, n: int) -> Iterator[Image.Image]:
        W, H = self.big.size
        for i in range(n):
            p = i / max(1, n - 1)
            if self.effect == "punch":
                z = 1.18 - 0.08 * (1 - (1 - min(1.0, i / 6)) ** 3) - 0.02 * p
            else:
                z = 1.0 + 0.1 * p
            cw, ch = W / z * 0.84, H / z * 0.84
            cx, cy = W / 2 + (p - 0.5) * W * 0.02, H / 2
            box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
            yield self.big.resize(self.size, Image.BILINEAR, box=box)


class Clip(Background):
    """A video clip, decoded by ffmpeg at the essay's size and rate."""

    def __init__(self, path: str, size: Tuple[int, int], offset: float = 0.0) -> None:
        self.path, self.size, self.offset = path, size, offset

    def frames(self, n: int) -> Iterator[Image.Image]:
        w, h = self.size
        cmd = [
            ffmpeg(), "-v", "error", "-ss", f"{self.offset:.2f}", "-stream_loop", "-1",
            "-i", self.path, "-frames:v", str(n),
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS}",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ]  # fmt: skip
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        frame_bytes = w * h * 3
        last = Image.new("RGB", self.size, PALETTE["black"])
        try:
            for _ in range(n):
                raw = proc.stdout.read(frame_bytes) if proc.stdout else b""
                if len(raw) == frame_bytes:
                    last = Image.frombytes("RGB", self.size, raw)
                yield last
        finally:
            if proc.stdout:
                proc.stdout.close()
            proc.kill()
            proc.wait()


def background_for(shot: Shot, size: Tuple[int, int]) -> Background:
    if shot.kind == "card" or not shot.asset:
        return Card(PALETTE.get(shot.card, PALETTE["black"]), size)
    if Path(shot.asset).suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        return Clip(shot.asset, size)
    return Still(shot.asset, size, shot.effect)


# -- looks, frames and devices -------------------------------------------------------------


def grade(img: Image.Image, look: str) -> Image.Image:
    if look == "bw":
        g = ImageOps.autocontrast(img.convert("L"), cutoff=1)
        return Image.merge("RGB", (g, g, g))
    if look in ("warm", "cold"):
        a = np.asarray(img).astype(np.float32)
        mul = (1.08, 1.0, 0.86) if look == "warm" else (0.9, 0.98, 1.1)
        a *= np.array(mul, dtype=np.float32)
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return img


@lru_cache(maxsize=8)
def crt_overlay(size: Tuple[int, int], film: bool) -> Image.Image:
    """An old TV (rounded glass, dark corners, scan lines) or a film gate."""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    mask = Image.new("L", size, 255)
    inset = int(min(w, h) * (0.05 if film else 0.035))
    radius = int(min(w, h) * (0.03 if film else 0.08))
    ImageDraw.Draw(mask).rounded_rectangle(
        (inset, inset, w - inset, h - inset), radius, fill=0
    )
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(inset * 0.25)))
    vignette = (
        Image.radial_gradient("L")
        .resize(size)
        .point(lambda v: int(max(0, v - 120) * 0.9))
    )
    dark = Image.new("RGBA", size, (0, 0, 0, 0))
    dark.putalpha(vignette)
    layer.alpha_composite(dark)
    if not film:
        lines = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lines)
        for y in range(0, h, 4):
            d.line((0, y, w, y), fill=(0, 0, 0, 28))
        layer.alpha_composite(lines)
    return layer


@lru_cache(maxsize=4)
def grain_tiles(size: Tuple[int, int], count: int = 6) -> List[np.ndarray]:
    rng = np.random.default_rng(11)
    w, h = size
    return [
        rng.normal(0, 1, (h // 2, w // 2, 1)).astype(np.float32) for _ in range(count)
    ]


def add_grain(img: Image.Image, strength: float, i: int) -> Image.Image:
    tile = grain_tiles(img.size)[i % 6]
    g = np.repeat(np.repeat(tile, 2, axis=0), 2, axis=1)[: img.size[1], : img.size[0]]
    a = np.asarray(img).astype(np.float32) + g * strength
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


@lru_cache(maxsize=4)
def device_layer(
    kind: str, size: Tuple[int, int]
) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    """A device drawn once: an old beige computer or a phone, with the
    screen box where the clip goes."""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if kind == "phone":
        ph = int(h * 0.86)
        pw = int(ph * 0.49)
        x0, y0 = (w - pw) // 2, (h - ph) // 2
        d.rounded_rectangle(
            (x0, y0, x0 + pw, y0 + ph), int(pw * 0.14), fill=(18, 18, 18, 255)
        )
        b = int(pw * 0.045)
        screen = (x0 + b, y0 + b, x0 + pw - b, y0 + ph - b)
        d.rounded_rectangle(screen, int(pw * 0.11), fill=(0, 0, 0, 0))
        d.rounded_rectangle(
            (x0 + pw * 0.36, y0 + b * 1.6, x0 + pw * 0.64, y0 + b * 2.6),
            b,
            fill=(18, 18, 18, 255),
        )
        return layer, screen
    cw = int(min(w * 0.46, h * 0.62))
    ch = int(cw * 0.9)
    x0, y0 = (w - cw) // 2, int(h * 0.1)
    body = (217, 207, 184, 255)
    d.rounded_rectangle((x0, y0, x0 + cw, y0 + ch), int(cw * 0.04), fill=body)
    sx0, sy0 = x0 + int(cw * 0.12), y0 + int(ch * 0.1)
    screen = (sx0, sy0, x0 + cw - int(cw * 0.12), sy0 + int(ch * 0.62))
    d.rounded_rectangle(
        (screen[0] - 10, screen[1] - 10, screen[2] + 10, screen[3] + 10),
        18,
        fill=(160, 150, 130, 255),
    )
    d.rounded_rectangle(screen, 14, fill=(0, 0, 0, 0))
    d.rectangle(
        (x0 + cw * 0.55, y0 + ch * 0.84, x0 + cw * 0.85, y0 + ch * 0.87),
        fill=(120, 112, 98, 255),
    )
    d.rectangle(
        (x0 + cw * 0.1, y0 + ch, x0 + cw * 0.9, y0 + ch + int(ch * 0.06)),
        fill=(200, 190, 168, 255),
    )
    return layer, screen


def in_device(img: Image.Image, kind: str) -> Image.Image:
    size = img.size
    back = img.resize((size[0] // 8, size[1] // 8), Image.BILINEAR).resize(
        size, Image.BILINEAR
    )
    back = Image.blend(back, Image.new("RGB", size, (0, 0, 0)), 0.45).convert("RGBA")
    layer, screen = device_layer(kind, size)
    sw, sh = screen[2] - screen[0], screen[3] - screen[1]
    back.paste(_cover(img, (sw, sh)), (screen[0], screen[1]))
    back.alpha_composite(layer)
    return back.convert("RGB")


def zoom(img: Image.Image, z: float, dx: float = 0.0, dy: float = 0.0) -> Image.Image:
    if abs(z - 1) < 1e-3 and not dx and not dy:
        return img
    w, h = img.size
    cw, ch = w / z, h / z
    cx, cy = w / 2 + dx, h / 2 + dy
    return img.resize(
        (w, h), Image.BILINEAR, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    )


def glitch(img: Image.Image, seed: int) -> Image.Image:
    a = np.asarray(img).copy()
    rng = np.random.default_rng(seed)
    shift = max(4, a.shape[1] // 120)
    a[:, :, 0] = np.roll(a[:, :, 0], shift, axis=1)
    a[:, :, 2] = np.roll(a[:, :, 2], -shift, axis=1)
    for _ in range(5):
        y = int(rng.integers(0, a.shape[0] - 20))
        hgt = int(rng.integers(6, 30))
        a[y : y + hgt] = np.roll(a[y : y + hgt], int(rng.integers(-40, 40)), axis=1)
    return Image.fromarray(a)


# -- the shot, frame by frame --------------------------------------------------------------


def letterbox(canvas: Image.Image, ratio: float = 2.39) -> None:
    """Black bars to a cinema frame (only on a frame wider than tall)."""
    w, h = canvas.size
    if w <= h:
        return
    bar = max(0, int((h - w / ratio) / 2))
    if bar:
        d = ImageDraw.Draw(canvas)
        d.rectangle((0, 0, w, bar), fill=(0, 0, 0, 255))
        d.rectangle((0, h - bar, w, h), fill=(0, 0, 0, 255))


def _ease(t: float, length: float = 0.35) -> float:
    x = min(1.0, max(0.0, t / length))
    return 1 - (1 - x) ** 3


def draw_motion(canvas: Image.Image, kind: str, t: float, accent=(255, 59, 48)) -> bool:
    """Motion graphics of a heavy edit, drawn on the frame: «circle» (a ring
    that draws itself round the centre of attention), «arrow:LABEL» (an
    arrow that flies in towards it, with its label) and «bar:N» (a progress
    bar that fills to N %). Returns False when *kind* is not one of them."""
    w, h = canvas.size
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    k = _ease(t)
    stroke = max(4, int(h * 0.009))
    if kind == "circle":
        cx, cy, r = w * 0.5, h * 0.45, h * 0.2
        d.arc(
            (cx - r, cy - r * 0.8, cx + r, cy + r * 0.8),
            -90,
            -90 + 360 * k,
            fill=accent + (255,),
            width=stroke,
        )
    elif kind.startswith("arrow"):
        label = kind.partition(":")[2]
        x1, y1 = w * 0.62, h * 0.62
        x0, y0 = w * 0.86, h * 0.84
        x0, y0 = x0 + (1 - k) * w * 0.2, y0 + (1 - k) * h * 0.2
        d.line((x0, y0, x1, y1), fill=accent + (255,), width=stroke * 2)
        a = math.atan2(y1 - y0, x1 - x0)
        head = stroke * 6
        pts = [(x1, y1)] + [
            (x1 - head * math.cos(a + s), y1 - head * math.sin(a + s))
            for s in (0.45, -0.45)
        ]
        d.polygon(pts, fill=accent + (255,))
        if label and k > 0.6:
            size = max(18, int(h * 0.05))
            img = word_image(label, "black", size, PALETTE["white"], True)
            layer.alpha_composite(
                img,
                (
                    int(min(w - img.size[0], x0 - img.size[0] * 0.5)),
                    int(min(h - img.size[1], y0 + stroke)),
                ),
            )
    elif kind.startswith("bar:"):
        try:
            goal = max(0.0, min(100.0, float(kind[4:]))) / 100
        except ValueError:
            return False
        x, y, bw, bh = w * 0.25, h * 0.08, w * 0.5, max(14, int(h * 0.028))
        d.rounded_rectangle((x, y, x + bw, y + bh), bh // 2, fill=(255, 255, 255, 200))
        d.rounded_rectangle(
            (x, y, x + max(bh, bw * goal * k), y + bh), bh // 2, fill=accent + (255,)
        )
    else:
        return False
    canvas.alpha_composite(layer)
    return True


def draw_overlay(canvas: Image.Image, text: str, t: float) -> None:
    """A stamp or counter at the top left, like the counters of challenge
    videos; a number in it counts up during the first half second. Motion
    graphics («circle», «arrow:…», «bar:N») draw themselves instead."""
    import re

    if draw_motion(canvas, text, t):
        return

    m = re.search(r"\d[\d.,]*", text)
    shown = text
    if m and t < 0.6:
        digits = re.sub(r"\D", "", m.group(0))
        if digits:
            value = int(int(digits) * min(1.0, t / 0.6))
            sep = "," if "," in m.group(0) else "."
            num = f"{value:,}".replace(",", sep) if len(digits) > 3 else str(value)
            shown = text[: m.start()] + num + text[m.end() :]
    size = max(18, int(canvas.size[1] * 0.075))
    img = word_image(shown.upper(), "black", size, PALETTE["white"], True)
    m_px = shadow_margin(size, True)
    canvas.alpha_composite(
        img, (int(canvas.size[0] * 0.05) - m_px, int(canvas.size[1] * 0.07) - m_px)
    )


def size_for(aspect: str, height: str = "1080") -> Tuple[int, int]:
    """The frame size of *aspect* at 720, 1080 or 2160 lines."""
    base = SIZES.get(aspect, SIZES["16:9"])
    scale = {"720": 2 / 3, "1080": 1.0, "2160": 2.0}.get(str(height), 1.0)
    return (int(base[0] * scale) // 2 * 2, int(base[1] * scale) // 2 * 2)


def shot_frames(
    shot: Shot, words: List[Word], size: Tuple[int, int], index: int = 0
) -> Iterator[Image.Image]:
    n = max(1, round(shot.dur * FPS))
    placed = layout_text(shot, words, size)
    shadow = shot.kind != "card"
    overlay = (
        crt_overlay(size, shot.frame == "film")
        if shot.frame in ("crt", "film")
        else None
    )
    rng = np.random.default_rng(index)
    for i, bg in enumerate(background_for(shot, size).frames(n)):
        t = i / FPS
        img = bg
        if shot.kind != "card":
            if shot.tone:
                from openjarvis.video_essay.color import apply_tone

                img = apply_tone(img, shot.tone)
            img = grade(img, shot.grade)
            if isinstance(img, Image.Image) and shot.effect in (
                "punch",
                "push",
                "shake",
            ):
                if shot.effect == "punch" and not shot.asset.endswith(
                    (".png", ".jpg", ".jpeg", ".webp")
                ):
                    img = zoom(img, 1.14 - 0.06 * min(1.0, i / 5))
                elif shot.effect == "shake":
                    img = zoom(img, 1.06, rng.normal(0, 6), rng.normal(0, 4))
            if shot.device != "none":
                img = in_device(img, shot.device)
            if shot.frame != "none" or shot.grade == "bw":
                img = add_grain(img, 14 if shot.frame == "film" else 8, i + index)
        canvas = img.convert("RGBA")
        if overlay is not None:
            canvas.alpha_composite(overlay)
        draw_text(canvas, placed, t, shot.text_style, shadow)
        if shot.overlay:
            draw_overlay(canvas, shot.overlay, t)
        if shot.frame == "letterbox":
            letterbox(canvas)
        out = canvas.convert("RGB")
        if shot.effect == "glitch" and i < 4:
            out = glitch(out, index * 10 + i)
        if shot.transition == "flash" and i < 3:
            out = Image.blend(
                out, Image.new("RGB", size, (255, 255, 255)), (0.8, 0.45, 0.15)[i]
            )
        elif shot.transition == "fade" and i < 8:
            out = Image.blend(Image.new("RGB", size, (0, 0, 0)), out, (i + 1) / 9)
        elif shot.transition == "whip" and i < 4:
            out = _whip(out, 1 - i / 4)
        yield out


def _whip(img: Image.Image, amount: float) -> Image.Image:
    a = np.asarray(img).astype(np.float32)
    shift = int(img.size[0] * 0.04 * amount) or 1
    acc = np.zeros_like(a)
    for k in range(6):
        acc += np.roll(a, k * shift, axis=1)
    return Image.fromarray((acc / 6).astype(np.uint8))


def render_video(
    shots: Sequence[Shot],
    words: List[Word],
    out: Path,
    *,
    size: Tuple[int, int],
    audio: Optional[Path] = None,
    preset: str = "medium",
    progress: Optional[Callable[[float], None]] = None,
) -> Path:
    """All the shots into one mp4 (with the mixed audio when given)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    silent = out.with_suffix(".video.mp4")
    w, h = size
    cmd = [
        ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", preset, "-crf", "18", "-pix_fmt", "yuv420p",
        str(silent),
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    total = sum(max(1, round(s.dur * FPS)) for s in shots) or 1
    done = 0
    try:
        for k, shot in enumerate(shots):
            for frame in shot_frames(shot, words, size, k):
                assert proc.stdin is not None
                proc.stdin.write(frame.tobytes())
                done += 1
                if progress and done % 30 == 0:
                    progress(done / total)
    finally:
        if proc.stdin:
            proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg no pudo codificar el video: {err[-400:]}")
    if audio is None:
        silent.replace(out)
        return out
    subprocess.run(
        [
            ffmpeg(), "-y", "-v", "error", "-i", str(silent), "-i", str(audio),
            "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(out),
        ],
        check=True, capture_output=True, timeout=1800,
    )  # fmt: skip
    silent.unlink(missing_ok=True)
    return out


def still_of(
    shot: Shot, words: List[Word], size: Tuple[int, int], at: float = 0.7
) -> Image.Image:
    """One frame of a shot (for the review and the preview)."""
    frames = shot_frames(shot, words, size)
    wanted = int(max(0, min(shot.dur * at, shot.dur - 0.05)) * FPS)
    last = None
    for i, frame in enumerate(frames):
        last = frame
        if i >= wanted:
            break
    return last if last is not None else Image.new("RGB", size)


def sheet(images: List[Image.Image], cols: int = 4, width: int = 1600) -> Image.Image:
    """Frames side by side, for the reviewer to see the whole edit at once."""
    if not images:
        return Image.new("RGB", (width, 10))
    cw = width // cols
    ch = int(cw * images[0].size[1] / images[0].size[0])
    rows = math.ceil(len(images) / cols)
    out = Image.new("RGB", (cw * cols, ch * rows), (0, 0, 0))
    for i, img in enumerate(images):
        out.paste(
            img.resize((cw, ch), Image.BILINEAR), ((i % cols) * cw, (i // cols) * ch)
        )
    return out


__all__ = [
    "draw_overlay",
    "size_for",
    "DRAFT_SIZES",
    "FPS",
    "PALETTE",
    "SIZES",
    "layout_text",
    "render_video",
    "sheet",
    "shot_frames",
    "still_of",
]

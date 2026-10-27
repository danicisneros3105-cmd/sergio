"""Colour theory and composition: what the picture already has, and where
the words can go without covering it.

The owner (27 Oct 2026): «que agregue teoría del color y composición». What
an editor does by eye, here in numbers:

* **palette** — the few colours a frame is made of (median cut), with how
  much of the frame each one takes;
* **harmony** — the colours that go with one (complementary, analogous,
  triadic, split-complementary), turning the hue on the colour wheel and
  keeping its strength;
* **contrast** — the WCAG ratio between two colours: text needs 4.5:1 to be
  read easily (3:1 when it is big), so the text colour is checked against
  the part of the picture it sits on, and gets a block behind it when
  neither white nor black reaches it;
* **accent** — the highlight colour of each shot: the style's own (NextCore's
  red) when it reads on the picture, else the complement of the picture's
  main colour, made bright enough to stand out;
* **saliency** — where the eye goes (spectral residual, plus faces when
  OpenCV is there), so the text sits on a third of the frame that is empty
  (rule of thirds, inside the title-safe area) and never on a face.

Everything is numpy and Pillow; nothing here calls out.
"""

from __future__ import annotations

import colorsys
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

RGB = Tuple[int, int, int]

SCHEMES = {
    "complementary": (180,),
    "analogous": (-30, 30),
    "triadic": (120, 240),
    "split": (150, 210),
}
# where text can go: the rule-of-thirds cells inside the title-safe area
# (5% in from every edge), as (x0, y0, x1, y1) fractions of the frame
SAFE = 0.05
ZONES: Dict[str, Tuple[float, float, float, float]] = {
    "upper_left": (SAFE, SAFE, 0.5, 0.36),
    "upper": (0.18, 0.08, 0.82, 0.38),
    "upper_right": (0.5, SAFE, 1 - SAFE, 0.36),
    "left": (SAFE, 0.3, 0.46, 0.7),
    "center": (0.2, 0.36, 0.8, 0.64),
    "right": (0.54, 0.3, 1 - SAFE, 0.7),
    "lower_left": (SAFE, 0.64, 0.5, 1 - SAFE),
    "lower": (0.18, 0.6, 0.82, 0.9),
    "lower_right": (0.5, 0.64, 1 - SAFE, 1 - SAFE),
}


# -- colour ----------------------------------------------------------------------------


def hex_of(rgb: Sequence[int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(int(c) for c in rgb[:3]))


def rgb_of(text: str) -> Optional[RGB]:
    text = str(text or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return None
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return None


def palette(img: Image.Image, k: int = 5) -> List[Tuple[RGB, float]]:
    """The *k* main colours of *img*, most of the frame first, with their share."""
    small = img.convert("RGB").copy()
    small.thumbnail((160, 160))
    q = small.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    total = sum(c for c, _ in counts) or 1
    out = []
    for count, idx in counts:
        rgb = tuple(pal[idx * 3 : idx * 3 + 3])
        out.append(((int(rgb[0]), int(rgb[1]), int(rgb[2])), count / total))
    return out


def rotate(rgb: Sequence[int], degrees: float) -> RGB:
    h, light, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb[:3]))
    r, g, b = colorsys.hls_to_rgb((h + degrees / 360) % 1.0, light, s)
    return (round(r * 255), round(g * 255), round(b * 255))


def harmony(rgb: Sequence[int], scheme: str = "complementary") -> List[RGB]:
    """The colours that go with *rgb* in *scheme* (the colour itself excluded)."""
    return [rotate(rgb, d) for d in SCHEMES.get(scheme, SCHEMES["complementary"])]


def luminance(rgb: Sequence[int]) -> float:
    """WCAG relative luminance."""

    def lin(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(float(c)) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: Sequence[int], b: Sequence[int]) -> float:
    """WCAG contrast ratio, 1 (none) to 21 (black on white)."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def vivid(rgb: Sequence[int], sat: float = 0.85, light: float = 0.55) -> RGB:
    """The same hue, strong enough to be an accent."""
    h, _l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb[:3]))
    if s < 0.08:  # a grey picture has no hue to answer: a warm gold
        h = 0.12
    r, g, b = colorsys.hls_to_rgb(h, light, max(s, sat))
    return (round(r * 255), round(g * 255), round(b * 255))


def mean_rgb(img: Image.Image) -> RGB:
    a = np.asarray(img.convert("RGB").resize((32, 32)), dtype=np.float32)
    m = a.reshape(-1, 3).mean(axis=0)
    return (int(m[0]), int(m[1]), int(m[2]))


def region(img: Image.Image, zone: str) -> Image.Image:
    x0, y0, x1, y1 = ZONES.get(zone, ZONES["center"])
    w, h = img.size
    return img.crop((int(x0 * w), int(y0 * h), max(int(x0 * w) + 1, int(x1 * w)),
                     max(int(y0 * h) + 1, int(y1 * h))))  # fmt: skip


def text_colour(behind: Sequence[int]) -> RGB:
    """White or near-black, whichever reads better on *behind*."""
    white, ink = (255, 255, 255), (12, 12, 12)
    return white if contrast(white, behind) >= contrast(ink, behind) else ink


def text_on_block(block: Sequence[int]) -> RGB:
    """The words on a block of colour: white when it reaches the 3:1 of big
    text (white on red reads as the reference does), else near-black."""
    white = (255, 255, 255)
    return white if contrast(white, block) >= 3.0 else (12, 12, 12)


def busy(img: Image.Image) -> float:
    """How busy a patch is (0 flat … 1 full of detail): text on busy picture
    needs a block or a strong shadow, whatever its average colour."""
    g = np.asarray(img.convert("L").resize((64, 36)), dtype=np.float32) / 255
    return float(
        min(
            1.0,
            (np.abs(np.diff(g, axis=0)).mean() + np.abs(np.diff(g, axis=1)).mean()) * 6,
        )
    )


def accent_for(
    img: Image.Image, brand: Optional[Sequence[int]] = None, zone: str = "center"
) -> RGB:
    """The highlight colour for a shot on *img*: the brand's when it stands
    out from the picture, else the complement of the picture's main colour."""
    behind = mean_rgb(region(img, zone))
    if brand is not None and contrast(brand, behind) >= 3.0:
        return tuple(int(c) for c in brand[:3])  # type: ignore[return-value]
    main = palette(img, 4)[0][0]
    best: Optional[RGB] = None
    for cand in [
        vivid(c) for c in harmony(main, "complementary") + harmony(main, "split")
    ]:
        for light in (0.55, 0.68, 0.42):
            c = vivid(cand, light=light)
            if best is None or contrast(c, behind) > contrast(best, behind):
                best = c
    return best or (242, 181, 58)


def legible(img: Image.Image, zone: str, accent: Sequence[int]) -> Dict[str, object]:
    """Whether the words (white with a shadow on footage, as render draws
    them) read on *zone* of *img*, or need a block behind them; the WCAG
    contrast reached (4.5 normal text, 3.0 big text) and the better colour."""
    patch = region(img, zone)
    behind = mean_rgb(patch)
    fill = text_colour(behind)
    # white fails on the bright parts, whatever the average: the brightest
    # quarter of the patch decides
    lum = np.asarray(patch.convert("L").resize((64, 36)), dtype=np.float32)
    bright = int(np.percentile(lum, 75))
    ratio = contrast((255, 255, 255), (bright, bright, bright))
    detail = busy(patch)
    needs_box = ratio < 3.0 or (ratio < 4.5 and detail > 0.45) or detail > 0.85
    return {"fill": fill, "ratio": round(ratio, 2), "box": needs_box,
            "box_text": text_on_block(accent), "behind": behind}  # fmt: skip


# -- composition -----------------------------------------------------------------------


def _faces(gray: np.ndarray) -> List[Tuple[int, int, int, int]]:
    try:
        import cv2
    except ImportError:
        return []
    try:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        found = cascade.detectMultiScale(gray, 1.15, 5, minSize=(24, 24))
        return [tuple(int(v) for v in f) for f in found]  # type: ignore[misc]
    except Exception:  # noqa: BLE001 — no faces is a safe answer
        return []


def saliency(img: Image.Image, width: int = 128) -> np.ndarray:
    """Where the eye goes, 0..1 per pixel at *width* (spectral residual,
    Hou & Zhang 2007), faces raised to the top."""
    w, h = img.size
    height = max(8, round(width * h / max(1, w)))
    g = np.asarray(img.convert("L").resize((width, height)), dtype=np.float32) / 255
    f = np.fft.fft2(g)
    amp = np.log(np.abs(f) + 1e-6)
    pad = np.pad(amp, 1, mode="edge")
    avg = (
        sum(
            pad[dy : dy + height, dx : dx + width] for dy in range(3) for dx in range(3)
        )
        / 9
    )
    sal = np.abs(np.fft.ifft2(np.exp(amp - avg + 1j * np.angle(f)))) ** 2
    # blur a little: regions, not pixels
    k = np.array([1, 4, 6, 4, 1], dtype=np.float32) / 16
    sal = np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 1, sal)
    sal = np.apply_along_axis(lambda c: np.convolve(c, k, "same"), 0, sal)
    sal = sal / (sal.max() or 1)
    big = np.asarray(img.convert("L").resize((width * 4, height * 4)))
    for x, y, fw, fh in _faces(big):
        # the face and what hangs under it (chin, beard, neck): never under
        # text (2.5: above anything else in the frame, so no place wins over it)
        x0, y0, s = x // 4, y // 4, max(1, fw // 4)
        sal[
            max(0, y0 - 2) : y0 + int(s * 1.7) + 3,
            max(0, x0 - s // 5) : x0 + s + s // 5 + 3,
        ] = 2.5
    return sal


def zone_scores(sal: np.ndarray) -> Dict[str, float]:
    """How much of the eye's attention each text zone would cover (lower is freer)."""
    h, w = sal.shape
    total = float(sal.sum()) or 1.0
    out = {}
    for name, (x0, y0, x1, y1) in ZONES.items():
        cell = sal[int(y0 * h) : max(int(y0 * h) + 1, int(y1 * h)),
                   int(x0 * w) : max(int(x0 * w) + 1, int(x1 * w))]  # fmt: skip
        # its own share of the attention, and how hot its hottest part is
        out[name] = float(cell.sum()) / total * 0.6 + float(cell.max()) * 0.4
    return out


def best_zone(
    img: Image.Image,
    allowed: Iterable[str] = tuple(ZONES),
    avoid: Iterable[str] = (),
    prefer: str = "",
    readable: bool = False,
) -> str:
    """The text zone that covers the least of what matters in *img*.

    *avoid*: the last shot's place, a small cost so the words move around
    without ever landing on a face for it; *prefer* wins near-ties;
    *readable*: white words must read there too (a zone that would need a
    block costs more)."""
    scores = zone_scores(saliency(img))
    names = [z for z in allowed if z in scores]
    if not names:
        return "center"
    skip = set(avoid)
    cost = {}
    for z in names:
        c = scores[z] + (0.12 if z in skip else 0.0)
        if readable and legible(img, z, (232, 38, 42))["box"]:
            c += 0.15
        cost[z] = c
    low = min(cost.values())
    if prefer in cost and cost[prefer] <= low + 0.04:
        return prefer
    return min(names, key=lambda z: cost[z])


def subject(img: Image.Image) -> Tuple[float, float]:
    """Where the subject sits (centre of attention), as fractions of the frame."""
    sal = saliency(img)
    h, w = sal.shape
    weight = sal**2
    total = float(weight.sum()) or 1.0
    ys, xs = np.mgrid[0:h, 0:w]
    return (
        float((weight * xs).sum() / total / w),
        float((weight * ys).sum() / total / h),
    )


def composition(img: Image.Image) -> Dict[str, object]:
    """A short composition read: where the subject is, whether it sits on a
    third, the free side for text (leading space), main colours."""
    x, y = subject(img)
    thirds = (
        min(abs(x - 1 / 3), abs(x - 2 / 3)) < 0.08
        or min(abs(y - 1 / 3), abs(y - 2 / 3)) < 0.08
    )
    centred = abs(x - 0.5) < 0.08 and abs(y - 0.5) < 0.1
    return {
        "subject": (round(x, 2), round(y, 2)),
        "on_thirds": bool(thirds),
        "centred": bool(centred),
        "free_side": "left" if x > 0.55 else ("right" if x < 0.45 else "lower"),
        "palette": [hex_of(c) for c, _ in palette(img, 4)],
    }


def _stats(img: Image.Image) -> np.ndarray:
    a = np.asarray(img.convert("RGB").resize((96, 54)), dtype=np.float32).reshape(-1, 3)
    return np.stack([a.mean(axis=0), a.std(axis=0) + 1.0])


def tone_for(
    img: Image.Image, target: np.ndarray, strength: float = 0.55
) -> List[float]:
    """Per channel (gain, offset) that moves *img* part of the way toward
    the video's colour (*target*: mean and spread of every shot together),
    as a colourist matches shots from different cameras (Reinhard et al.,
    2001, here per RGB channel and only half way, so each shot keeps its own
    light). Gains stay within 0.8-1.25 and offsets within ±32."""
    src = _stats(img)
    out: List[float] = []
    for c in range(3):
        gain = 1 + strength * (target[1][c] / src[1][c] - 1)
        gain = float(min(1.25, max(0.8, gain)))
        offset = src[0][c] * (1 - gain) + strength * (target[0][c] - src[0][c])
        out += [round(gain, 4), round(float(min(32.0, max(-32.0, offset))), 2)]
    return out


def apply_tone(img: Image.Image, tone: Sequence[float]) -> Image.Image:
    """*img* with a :func:`tone_for` match (a lookup table: cheap per frame)."""
    if len(tone) != 6:
        return img
    lut: List[int] = []
    for c in range(3):
        gain, offset = tone[2 * c], tone[2 * c + 1]
        lut += [int(min(255, max(0, round(v * gain + offset)))) for v in range(256)]
    return img.convert("RGB").point(lut)


def unify(shots: Sequence[object], still: Callable[[object], object]) -> int:
    """One colour for the whole video: every picture shot moves half way
    toward the average look of all of them (not cards, not black and white
    or graded ones, which have their own look on purpose). Safe to run again."""
    todo = [
        s
        for s in shots
        if getattr(s, "kind", "") != "card" and not getattr(s, "tone", None)
    ]
    if len(todo) < 2:
        return 0
    seen = []
    for s in todo:
        try:
            img = still(s)
        except Exception:  # noqa: BLE001
            img = None
        if img is not None:
            seen.append((s, img))
    if len(seen) < 2:
        return 0
    target = np.mean([_stats(img) for _, img in seen], axis=0)
    for s, img in seen:
        s.tone = (
            tone_for(img, target)
            if getattr(s, "grade", "natural") == "natural"
            else [1, 0, 1, 0, 1, 0]
        )
    return len(seen)


def look_of(frames: Iterable[Image.Image]) -> Dict[str, float]:
    """The colour temperature and strength of a run of shots, so a video
    can keep one colour script: warm >0, cold <0; saturation 0..1."""
    warm, sat, n = 0.0, 0.0, 0
    for f in frames:
        r, g, b = mean_rgb(f)
        warm += (r - b) / 255
        sat += colorsys.rgb_to_hls(r / 255, g / 255, b / 255)[2]
        n += 1
    return {
        "warmth": round(warm / max(1, n), 3),
        "saturation": round(sat / max(1, n), 3),
    }


__all__ = [
    "SCHEMES",
    "ZONES",
    "accent_for",
    "apply_tone",
    "tone_for",
    "unify",
    "best_zone",
    "busy",
    "composition",
    "contrast",
    "harmony",
    "hex_of",
    "legible",
    "look_of",
    "luminance",
    "palette",
    "region",
    "rgb_of",
    "rotate",
    "saliency",
    "subject",
    "text_colour",
    "text_on_block",
    "vivid",
    "zone_scores",
]

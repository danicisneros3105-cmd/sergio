"""Which free typeface looks most like the Bang & Olufsen logo? Measured.

Renders B, & and O of each candidate font, scales each glyph to the height
of the same glyph in the logo, and scores the overlap (intersection over
union). B and O weigh 40 % each, & 20 %. Usage::

    python scripts/font_match.py logo.png fonts/*.ttf

``logo.png``: the logo in black on white (B, & and O as separate shapes,
in that reading order: B left, & top right, O bottom right). Result
(46 Google Fonts, weights 300-700): Josefin Sans 400 first (O 0.944,
& 0.624), then Josefin Sans 500 and Jost 400. No free font has the logo's
very tall B, so B scores low for all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def logo_glyphs(path: str) -> dict[str, np.ndarray]:
    img = (cv2.imread(path, 0) < 128).astype("uint8")
    n, lab, stats, _ = cv2.connectedComponentsWithStats(img, 8)
    parts = sorted(range(1, n), key=lambda i: -stats[i][4])[:3]  # the three biggest shapes
    by_x = sorted(parts, key=lambda i: stats[i][0])
    b = by_x[0]
    rest = sorted(by_x[1:], key=lambda i: stats[i][1])  # & above, O below
    out = {}
    for ch, i in (("B", b), ("&", rest[0]), ("O", rest[1])):
        x, y, w, h, _ = stats[i]
        out[ch] = (lab[y : y + h, x : x + w] == i).astype("uint8")
    return out


def render(font: str, ch: str) -> np.ndarray | None:
    f = ImageFont.truetype(font, 600)
    im = Image.new("L", (1400, 1400), 0)
    ImageDraw.Draw(im).text((300, 200), ch, font=f, fill=255)
    a = np.array(im) > 128
    ys, xs = np.where(a)
    if not len(xs):
        return None
    return a[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1].astype("uint8")


def iou(ref: np.ndarray, glyph: np.ndarray) -> float:
    h, w = ref.shape
    gh, gw = glyph.shape
    nw = max(1, int(round(gw * h / gh)))
    g = cv2.resize(glyph, (nw, h), interpolation=cv2.INTER_AREA) > 0
    width = max(w, nw)
    a = np.zeros((h, width), bool)
    b = np.zeros((h, width), bool)
    a[:, (width - w) // 2 : (width - w) // 2 + w] = ref > 0
    b[:, (width - nw) // 2 : (width - nw) // 2 + nw] = g
    return float((a & b).sum() / (a | b).sum())


def main(logo: str, fonts: list[str]) -> list[tuple[float, str]]:
    ref = logo_glyphs(logo)
    scores = []
    for font in fonts:
        s = {}
        for ch in "BO&":
            g = render(font, ch)
            s[ch] = iou(ref[ch], g) if g is not None else 0.0
        scores.append((0.4 * s["B"] + 0.4 * s["O"] + 0.2 * s["&"], Path(font).name))
    return sorted(scores, reverse=True)


if __name__ == "__main__":
    for score, name in main(sys.argv[1], sys.argv[2:])[:15]:
        print(f"{score:.3f}  {name}")

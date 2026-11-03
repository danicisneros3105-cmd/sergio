"""An image, measured: the numbers behind the superskills' matrices.

Everything runs on a small copy (256 px on the long side) with numpy and PIL,
on this computer. What is measured here is labelled as measured; composition
taste that needs eyes stays with the model and the owner.
"""

from __future__ import annotations

import colorsys
from pathlib import Path
from typing import Any, Dict, Optional

LUMA = (0.2126, 0.7152, 0.0722)
GOLD = (0.382, 0.618)
THIRDS = (1 / 3, 2 / 3)


def _load(img: Any):
    import numpy as np
    from PIL import Image

    if isinstance(img, (str, Path)):
        im = Image.open(img)
    elif isinstance(img, Image.Image):
        im = img
    else:
        im = Image.fromarray(np.asarray(img).astype("uint8"))
    im = im.convert("RGB")
    im.thumbnail((256, 256))
    return np.asarray(im).astype("float32") / 255


def saliency(rgb: Any) -> Any:
    """What stands out: distance of each pixel's colour from the frame's main
    (median) colour, plus local edge energy. 0..1."""
    import numpy as np

    bg = np.median(rgb.reshape(-1, 3), axis=0)
    dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    y = rgb @ np.asarray(LUMA, dtype="float32")
    gx = np.abs(np.diff(y, axis=1, append=y[:, -1:]))
    gy = np.abs(np.diff(y, axis=0, append=y[-1:, :]))
    edges = gx + gy
    s = dist / (dist.max() + 1e-6) * 0.7 + edges / (edges.max() + 1e-6) * 0.3
    return s


def measure(img: Any) -> Dict[str, Any]:
    """The numbers of one image (see the module docstring)."""
    import numpy as np

    rgb = _load(img)
    h, w, _ = rgb.shape
    y = rgb @ np.asarray(LUMA, dtype="float32")
    sal = saliency(rgb)
    thr = max(0.18, float(np.percentile(sal, 75)) * 0.6)
    fig = sal > thr
    weight = sal * fig
    total = float(weight.sum()) + 1e-6
    ys, xs = np.mgrid[0:h, 0:w]
    cx = float((weight * xs).sum() / total) / max(1, w - 1)
    cy = float((weight * ys).sum() / total) / max(1, h - 1)
    # the strongest point (smoothed) for lines of force
    k = max(3, min(h, w) // 16)
    pad = np.pad(sal, k, mode="edge")
    box = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    smooth = (
        box[2 * k :, 2 * k :]
        - box[: -2 * k, 2 * k :]
        - box[2 * k :, : -2 * k]
        + box[: -2 * k, : -2 * k]
    )
    smooth = smooth[:h, :w]
    py, px = np.unravel_index(int(np.argmax(smooth)), smooth.shape)
    fx, fy = px / max(1, w - 1), py / max(1, h - 1)

    def near(v: float, lines: tuple) -> float:
        return min(abs(v - x) for x in lines)

    # colour
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in rgb[::4, ::4].reshape(-1, 3)])
    sat = float(hsv[:, 1].mean())
    vivid = hsv[(hsv[:, 1] > 0.12) & (hsv[:, 2] > 0.12)]
    hues = 0
    spread = 0.0
    if len(vivid):
        hist, _ = np.histogram(vivid[:, 0], bins=12, range=(0, 1))
        hues = int((hist / max(1, len(hsv)) > 0.05).sum())
        ang = vivid[:, 0] * 2 * np.pi
        r = np.hypot(np.cos(ang).mean(), np.sin(ang).mean())
        spread = float(np.degrees(np.sqrt(max(0.0, -2 * np.log(max(r, 1e-6))))))
    # light
    p5, p95 = np.percentile(y, [5, 95])
    steps = int((np.histogram(y, bins=10, range=(0, 1))[0] / y.size > 0.02).sum())
    sym = 1.0 - float(np.abs(y - y[:, ::-1]).mean()) * 2
    return {
        "espacio_negativo": round(1.0 - float(fig.mean()), 3),
        "masa_dx": round(cx - 0.5, 3),
        "masa_dy": round(cy - 0.5, 3),
        "foco": [round(float(fx), 3), round(float(fy), 3)],
        "aureo_dist": round(float(min(near(fx, GOLD), near(fy, GOLD))), 3),
        "tercios_dist": round(float(min(near(fx, THIRDS), near(fy, THIRDS))), 3),
        "brillo": round(float(y.mean()), 3),
        "contraste": round(float(p95 - p5), 3),
        "sombras": round(float((y < 0.1).mean()), 3),
        "negro": round(float((y < 0.03).mean()), 3),
        "luces": round(float((y > 0.95).mean()), 3),
        "escalones": steps,
        "saturacion_media": round(sat, 3),
        "tonos": hues,
        "dispersion_tono": round(min(180.0, spread), 1),
        "calidez": round(float(rgb[..., 0].mean() - rgb[..., 2].mean()), 3),
        "simetria": round(max(0.0, sym), 3),
        "vertical": h > w,
    }


# Ranges of the matrices that code can check (superskill → measure → range).
# When the owner's boards are measured, his percentiles 10-90 replace these.
DEFAULT_RANGES: Dict[str, Dict[str, tuple]] = {
    "1": {"espacio_negativo": (0.55, 0.85)},
    "2": {"masa_desplazamiento": (0.08, 0.30)},
    "4": {"aureo_dist": (0.0, 0.05)},
    "6": {"luces": (0.0, 0.02), "sombras": (0.0, 0.08), "contraste": (0.35, 0.85)},
    "7": {"sombras": (0.55, 0.85), "negro": (0.0, 0.15)},
    "8": {"saturacion_media": (0.0, 0.15), "escalones": (5, 10)},
    "9": {"saturacion_media": (0.0, 0.25), "tonos": (0, 3)},
}


def score(m: Dict[str, Any], ranges: Optional[Dict[str, Dict[str, tuple]]] = None,
          only: Optional[list] = None) -> Dict[str, Any]:  # fmt: skip
    """How the measured criteria score (0-100 each) against their ranges.
    Only the measurable part of each matrix: the rest is judgement."""
    ranges = ranges or DEFAULT_RANGES
    vals = dict(m)
    vals["masa_desplazamiento"] = round(
        (m.get("masa_dx", 0) ** 2 + m.get("masa_dy", 0) ** 2) ** 0.5, 3
    )
    out: Dict[str, Any] = {}
    for key, rules in ranges.items():
        if only and key not in only:
            continue
        parts = {}
        for name, (lo, hi) in rules.items():
            v = vals.get(name)
            if v is None:
                continue
            if lo <= v <= hi:
                parts[name] = 100
            else:
                gap = (lo - v) if v < lo else (v - hi)
                span = max(abs(hi - lo), 0.05)
                parts[name] = max(0, int(round(100 - 100 * gap / span)))
        if parts:
            out[key] = {
                "medido": parts,
                "puntos": int(round(sum(parts.values()) / len(parts))),
            }
    return out


__all__ = ["DEFAULT_RANGES", "measure", "saliency", "score"]

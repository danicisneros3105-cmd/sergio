"""Holograms of anything: Gemini designs the object part by part.

"Haz un teléfono" used to give a cube called "teléfono". Now Gemini acts as
an industrial designer and answers with the object's real parts in metres
(body, screen, camera bump, lenses, buttons, port...), each a simple solid
the companion can draw at once: rounded boxes, cylinders, spheres, cones,
tori, capsules and wedges, with position, rotation and colour. The same
recipe seeds Blender Pro's detailed version.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

SHAPES = (
    "box",
    "rounded_box",
    "cylinder",
    "sphere",
    "cone",
    "torus",
    "capsule",
    "wedge",
    "lathe",
    "extrude",
    "tube",
)
MAX_PARTS = 60

PROMPT = """You are a senior industrial designer and 3D modeller. Build \
«{request}» as a 3D assembly of simple solids, faithful to the real object \
(real proportions and real size in METRES, e.g. a phone is about 0.072 x \
0.150 x 0.008). Coordinates: x right, y UP, z toward the viewer; the object \
centred at the origin, front facing +z.
Use 8 to 45 parts: the main body plus every recognisable detail (for a phone: \
rounded body, screen glass, bezel, camera bump, each lens and its ring, flash, \
side buttons, port, speaker holes...). Thin parts sit ON the surface (offset \
by half their thickness), never floating or hidden inside.
NEVER build a curved object out of boxes: a cup, bottle, vase, lampshade, \
wheel, bowl or bulb is a "lathe"; a flat shape with a real outline (a phone \
body, a guitar body, a logo, a leaf, a bracket) is an "extrude"; a handle, \
cable, frame, arm or pipe that bends is a "tube". The result must be \
recognisable from its silhouette alone.
Shapes and their "size" (metres): box/rounded_box/wedge [w, h, d]; \
cylinder/cone/capsule [diameter, height, diameter] (axis = y before \
rotation); sphere [dx, dy, dz]; torus [outer diameter, tube thickness, \
outer diameter] (ring in the xz plane).
Free-form shapes (local coordinates in metres, then "pos"/"rot" as usual):
- "lathe": "profile" = [[radius, y], ...] from bottom to top (4-30 points), \
turned around the y axis; radius 0 closes the bottom/top (a cup: [[0,0], \
[0.035,0], [0.04,0.09], [0.037,0.09], [0.032,0.004], [0,0.004]] makes a \
hollow cup with a wall).
- "extrude": "outline" = [[x, y], ...] closed outline in the xy plane (3-60 \
points), "size" [w, h, depth] where only depth (along z) is used.
- "tube": "path" = [[x, y, z], ...] (2-40 points) and "radius" in metres.
"rot" is degrees around x, y, z (applied x then y then z). "color" is RGB \
0..1 of the real material (black glass, aluminium, etc.).
Answer ONLY JSON: {{"name": "short Spanish name", "description": "one Spanish \
sentence", "parts": [{{"name": "Spanish part name", "shape": "rounded_box", \
"size": [0.072, 0.15, 0.008], "pos": [0, 0, 0], "rot": [0, 0, 0], \
"color": [0.1, 0.1, 0.12]}}]}}"""


def _nums(value: Any, n: int, default: float) -> list[float]:
    try:
        out = [float(x) for x in list(value)[:n]]
    except (TypeError, ValueError):
        out = []
    return out + [default] * (n - len(out))


def _points(value: Any, dims: int, lo: int, hi: int) -> list[list[float]] | None:
    """A list of *dims*-number points (lo..hi of them, metres), or None."""
    if not isinstance(value, list):
        return None
    pts = []
    for p in value[:hi]:
        if not isinstance(p, (list, tuple)) or len(p) < dims:
            continue
        try:
            pts.append([max(min(float(x), 50.0), -50.0) for x in p[:dims]])
        except (TypeError, ValueError):
            continue
    return pts if len(pts) >= lo else None


def _free_form(shape: str, raw: dict[str, Any]) -> dict[str, Any] | None:
    """The points of a lathe / extrude / tube part ({} for other shapes)."""
    if shape == "lathe":
        prof = _points(raw.get("profile"), 2, 2, 40)
        return {"profile": [[abs(r), y] for r, y in prof]} if prof else None
    if shape == "extrude":
        out = _points(raw.get("outline"), 2, 3, 80)
        return {"outline": out} if out else None
    if shape == "tube":
        path = _points(raw.get("path"), 3, 2, 60)
        if not path:
            return None
        try:
            radius = float(raw.get("radius") or 0.005)
        except (TypeError, ValueError):
            radius = 0.005
        return {"path": path, "radius": min(max(abs(radius), 0.0005), 5.0)}
    return {}


def parse_recipe(text: str) -> dict[str, Any]:
    """Gemini's answer, checked: known shapes, sane sizes, at most 60 parts."""
    found = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(found.group(0)) if found else {}
    except ValueError:
        data = {}
    parts = []
    for raw in data.get("parts") or []:
        if not isinstance(raw, dict):
            continue
        shape = str(raw.get("shape") or "box").lower()
        if shape not in SHAPES:
            shape = "box"
        size = [min(max(abs(v), 0.0005), 50.0) for v in _nums(raw.get("size"), 3, 0.05)]
        color = [min(max(v, 0.0), 1.0) for v in _nums(raw.get("color"), 3, 0.6)]
        part = {
            "name": str(raw.get("name") or shape)[:40],
            "shape": shape,
            "size": size,
            "pos": [max(min(v, 50.0), -50.0) for v in _nums(raw.get("pos"), 3, 0.0)],
            "rot": [v % 360 for v in _nums(raw.get("rot"), 3, 0.0)],
            "color": color,
        }
        free = _free_form(shape, raw)
        if free is None:  # a free shape without its points: a plain box instead
            part["shape"] = "box" if shape in ("lathe", "extrude", "tube") else shape
        else:
            part.update(free)
        parts.append(part)
        if len(parts) >= MAX_PARTS:
            break
    if not parts:
        raise RuntimeError("El diseñador no devolvió piezas.")
    return {
        "name": " ".join(str(data.get("name") or "objeto").split())[:40],
        "description": str(data.get("description") or "")[:200],
        "parts": parts,
    }


# Best first; the light model only when the others are busy or refuse.
DESIGN_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
)
HEDGE_AFTER = 15.0


def _good_recipe(text: str) -> dict[str, Any]:
    """A recipe worth showing: parsed, and more than a few blocks."""
    recipe = parse_recipe(text)
    if len(recipe["parts"]) < 5:
        raise ValueError(f"solo {len(recipe['parts'])} piezas")
    return recipe


def design(request: str, ask: Callable[[str], str] | None = None) -> dict[str, Any]:
    return parse_recipe((ask or _ask)(PROMPT.format(request=request)))


def _ask(prompt: str, retry: bool = True) -> str:
    import os

    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs
    from openjarvis.engine.google_client import SwitchingClient

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY")
    client = SwitchingClient(key)
    from openjarvis.engine.google_client import short_wait
    from openjarvis.engine.hedge import HedgeError, first_valid

    def call(model: str) -> Callable[[], str]:
        def run() -> str:
            resp = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    **google_config_kwargs(model, 0.4, 12000, "medium"),
                    response_mime_type="application/json",
                ),
            )
            return str(resp.text or "")

        return run

    # Hedged: a busy model that takes minutes never makes the owner wait;
    # after HEDGE_AFTER s the next model starts too and the first valid
    # recipe wins (a refusal starts the next one at once).
    try:
        _, text = first_valid(
            [call(m) for m in DESIGN_MODELS],
            names=DESIGN_MODELS,
            check=_good_recipe,
            hedge_after=HEDGE_AFTER,
            timeout=240,
        )
        return text
    except HedgeError as exc:
        errors = exc.errors
    wait = short_wait(errors) if retry else 0.0
    if wait:  # a short quota pause ("back in ~1 min"): one more try after it
        import time

        time.sleep(wait)
        return _ask(prompt, retry=False)
    raise RuntimeError("No pude diseñar el holograma: " + " | ".join(errors))


FREE_LABELS = (
    ("profile", "lathe profile (radius, height)"),
    ("outline", "outline (x, y)"),
    ("path", "tube path"),
)


def _points_brief(part: dict[str, Any]) -> str:
    """A free-form part's points in cm (lathe profile, outline or tube path)."""
    for key, label in FREE_LABELS:
        if part.get(key):
            pts = ", ".join(
                "(" + ", ".join(f"{v * 100:.1f}" for v in pt) + ")" for pt in part[key]
            )
            extra = f", {label} cm {pts}"
            if key == "path":
                extra += f", radius {part.get('radius', 0) * 100:.1f} cm"
            return extra
    return ""


def recipe_brief(recipe: dict[str, Any]) -> str:
    """The parts in words, for Blender Pro (cm, so it reads naturally)."""
    lines = []
    for p in recipe["parts"]:
        size = " x ".join(f"{v * 100:.1f}" for v in p["size"])
        pos = ", ".join(f"{v * 100:.1f}" for v in p["pos"])
        line = f"- {p['name']}: {p['shape']} {size} cm at ({pos}) cm, rot {p['rot']}"
        lines.append(line + f", colour {p['color']}" + _points_brief(p))
    return "\n".join(lines)


__all__ = ["SHAPES", "design", "parse_recipe", "recipe_brief"]

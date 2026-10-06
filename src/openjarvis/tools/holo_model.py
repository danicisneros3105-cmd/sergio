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

SHAPES = ("box", "rounded_box", "cylinder", "sphere", "cone", "torus", "capsule", "wedge")
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
Shapes and their "size" (metres): box/rounded_box/wedge [w, h, d]; \
cylinder/cone/capsule [diameter, height, diameter] (axis = y before \
rotation); sphere [dx, dy, dz]; torus [outer diameter, tube thickness, \
outer diameter] (ring in the xz plane).
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
        parts.append(
            {
                "name": str(raw.get("name") or shape)[:40],
                "shape": shape,
                "size": size,
                "pos": [max(min(v, 50.0), -50.0) for v in _nums(raw.get("pos"), 3, 0.0)],
                "rot": [v % 360 for v in _nums(raw.get("rot"), 3, 0.0)],
                "color": color,
            }
        )
        if len(parts) >= MAX_PARTS:
            break
    if not parts:
        raise RuntimeError("El diseñador no devolvió piezas.")
    return {
        "name": " ".join(str(data.get("name") or "objeto").split())[:40],
        "description": str(data.get("description") or "")[:200],
        "parts": parts,
    }


def design(request: str, ask: Callable[[str], str] | None = None) -> dict[str, Any]:
    return parse_recipe((ask or _ask)(PROMPT.format(request=request)))


def _ask(prompt: str) -> str:
    import os

    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs
    from openjarvis.engine.google_client import SwitchingClient

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY")
    client = SwitchingClient(key)
    errors = []
    for model in ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.1-pro-preview",
                  "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    **google_config_kwargs(model, 0.4, 8000, "low"),
                    response_mime_type="application/json",
                ),
            )
            text = str(resp.text or "")
            parse_recipe(text)
            return text
        except Exception as exc:  # noqa: BLE001 — next model
            errors.append(f"{model}: {str(exc)[:100]}")
    raise RuntimeError("No pude diseñar el holograma: " + " | ".join(errors))


def recipe_brief(recipe: dict[str, Any]) -> str:
    """The parts in words, for Blender Pro (cm, so it reads naturally)."""
    lines = []
    for p in recipe["parts"]:
        size = " x ".join(f"{v * 100:.1f}" for v in p["size"])
        pos = ", ".join(f"{v * 100:.1f}" for v in p["pos"])
        lines.append(f"- {p['name']}: {p['shape']} {size} cm at ({pos}) cm, rot {p['rot']}, colour {p['color']}")
    return "\n".join(lines)


__all__ = ["SHAPES", "design", "parse_recipe", "recipe_brief"]

"""Check a proposed spatial layout; never infer metric depth from a screenshot."""

from __future__ import annotations

import html
import json
import math
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


def scene(objects: list[dict], mode: str = "proposal", units: str = "m") -> dict:
    if mode not in ("proposal", "measured") or units not in ("m", "cm", "px"):
        raise ValueError("Indique proposal/measured y unidades m/cm/px.")
    if not isinstance(objects, list) or not 1 <= len(objects) <= 50:
        raise ValueError("Entre 1 y 50 objetos.")
    boxes = []
    for obj in objects:
        name = str(obj.get("name") or "objeto")[:80]
        vectors = []
        for key in ("position", "size"):
            raw = obj.get(key)
            if not isinstance(raw, list) or len(raw) != 3:
                raise ValueError("position y size necesitan tres números.")
            vec = [float(v) for v in raw]
            if any(not math.isfinite(v) or abs(v) > 1e6 for v in vec):
                raise ValueError("Coordenada inválida.")
            vectors.append(vec)
        pos, size = vectors
        if any(v < 1e-9 for v in size):
            raise ValueError("Dimensiones positivas.")
        boxes.append({"name": name, "position": pos, "size": size})
    overlaps, distances = [], []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            pair = [a["name"], b["name"]]
            delta = [abs(x - y) for x, y in zip(a["position"], b["position"])]
            if all(d < (s + t) / 2 for d, s, t in zip(delta, a["size"], b["size"])):
                overlaps.append(pair)
            distances.append(
                {
                    "pair": pair,
                    "center_distance": math.dist(a["position"], b["position"]),
                }
            )
    # Top view (x,z), scaled to fit. SVG text is escaped, with no scripts or links.
    x0 = min(b["position"][0] - b["size"][0] / 2 for b in boxes)
    z0 = min(b["position"][2] - b["size"][2] / 2 for b in boxes)
    w = max(b["position"][0] + b["size"][0] / 2 for b in boxes) - x0
    h = max(b["position"][2] + b["size"][2] / 2 for b in boxes) - z0
    scale = 500 / max(w, h)
    shapes = []
    for b in boxes:
        x = 20 + (b["position"][0] - b["size"][0] / 2 - x0) * scale
        z = 20 + (b["position"][2] - b["size"][2] / 2 - z0) * scale
        shapes.append(
            f'<rect x="{x:.2f}" y="{z:.2f}" width="{b["size"][0] * scale:.2f}" '
            f'height="{b["size"][2] * scale:.2f}" fill="#c6dfee" stroke="#254960"/>'
            f'<text x="{x + 4:.2f}" y="{z + 16:.2f}" font-size="12">{html.escape(b["name"])}</text>'
        )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 560">'
        + "".join(shapes)
        + "</svg>"
    )
    return {
        "mode": mode,
        "units": units,
        "objects": boxes,
        "overlaps": overlaps,
        "distances": distances,
        "top_view_svg": svg,
        "note": "Propuesta imaginada, no observación."
        if mode == "proposal"
        else "Geometría de las medidas aportadas; no valida la exactitud de su fuente.",
    }


@ToolRegistry.register("scene_reason")
class SceneReasonTool(BaseTool):
    tool_id = "scene_reason"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            category="reasoning",
            description=(
                "Check or imagine a 3D box layout. Calculates collisions and center distances "
                "and returns an SVG top view. Positions are centers; size is width,height,depth. "
                "Measured means user-supplied measurements, never metric depths guessed from pixels."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "objects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "position": {
                                    "type": "array",
                                    "items": {"type": "number"},
                                },
                                "size": {"type": "array", "items": {"type": "number"}},
                            },
                            "required": ["name", "position", "size"],
                        },
                    },
                    "mode": {"type": "string", "enum": ["proposal", "measured"]},
                    "units": {"type": "string", "enum": ["m", "cm", "px"]},
                },
                "required": ["objects"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        try:
            result = scene(
                params.get("objects"),
                params.get("mode", "proposal"),
                params.get("units", "m"),
            )
            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(result, ensure_ascii=False),
                success=True,
            )
        except (ValueError, TypeError, AttributeError, OverflowError) as exc:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Escena no verificada: {exc}",
                success=False,
            )


__all__ = ["SceneReasonTool", "scene"]

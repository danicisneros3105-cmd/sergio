"""Sergio's designs, made inside OpenDesign.

OpenDesign (clawnify/OpenDesign, MIT) is the Canva-like editor Creator shows
in Diseño. It keeps designs in its own local database behind a small REST
API (``/api/designs``). When the owner asks Sergio for a design, Sergio
lays it out (the same layout Gemini makes for Creator) and creates it there
as a Fabric.js canvas, so it opens ready to edit in the real editor.
"""

from __future__ import annotations

import json
from typing import Any

from openjarvis.creator.llm import CreatorError
from openjarvis.unified.supervisor import OPENDESIGN_API_PORT

API = f"http://127.0.0.1:{OPENDESIGN_API_PORT}/api"
FONT = "Inter"


def fabric_json(layout: dict[str, Any], width: int, height: int) -> str:
    """The layout as OpenDesign's canvas JSON (Fabric v6), like its templates:
    a full-size background rect first, then shapes and text boxes."""
    objects: list[dict[str, Any]] = [
        {
            "type": "rect",
            "left": 0,
            "top": 0,
            "width": width,
            "height": height,
            "fill": layout.get("background") or "#ffffff",
            "selectable": True,
        }
    ]
    for el in layout.get("elements") or []:
        kind = el.get("type")
        if kind == "rect":
            radius = float(el.get("radius") or 0)
            objects.append(
                {
                    "type": "rect",
                    "left": el["x"],
                    "top": el["y"],
                    "width": el["w"],
                    "height": el["h"],
                    "fill": el["fill"],
                    "rx": radius,
                    "ry": radius,
                }
            )
        elif kind == "circle":
            objects.append(
                {
                    "type": "circle",
                    "left": el["x"],
                    "top": el["y"],
                    "radius": el["r"],
                    "fill": el["fill"],
                }
            )
        elif kind == "text":
            objects.append(
                {
                    "type": "textbox",
                    "left": el["x"],
                    "top": el["y"],
                    "width": el["w"],
                    "text": el["text"],
                    "fontSize": el["size"],
                    "fontFamily": FONT,
                    "fontWeight": str(el.get("weight", 700)),
                    "fill": el["color"],
                    "textAlign": el.get("align", "left"),
                    "lineHeight": 1.2,
                }
            )
    return json.dumps(
        {
            "version": "6.0.0",
            "objects": objects,
            "background": layout.get("background") or "#ffffff",
        },
        ensure_ascii=False,
    )


def create_design(
    name: str,
    layout: dict[str, Any],
    width: int,
    height: int,
    *,
    post: Any = None,
) -> dict[str, Any]:
    """Create the design in OpenDesign; returns its row (with ``id``)."""
    body = {
        "name": (name or "Diseño de Sergio")[:80],
        "canvas_json": fabric_json(layout, width, height),
        "width": int(width),
        "height": int(height),
    }
    if post is None:
        import httpx

        def post(url: str, payload: dict[str, Any]) -> Any:
            resp = httpx.post(url, json=payload, timeout=20)
            resp.raise_for_status()
            return resp.json()

    try:
        row = post(f"{API}/designs", body)
    except Exception as exc:  # noqa: BLE001 — the editor is not running
        raise CreatorError(
            "OpenDesign no responde. Ábralo en Creator → Diseño y vuelva a pedírmelo."
        ) from exc
    if not isinstance(row, dict) or "id" not in row:
        raise CreatorError("OpenDesign no creó el diseño.")
    return row


__all__ = ["create_design", "fabric_json"]

"""Creator's floor plan as an IFC building model (BIM).

The plan drawn in Creator → Arquitectura (walls, doors, windows, in metres)
becomes a real IFC4 file made with IfcOpenShell: project, site, building and
storey, each wall an ``IfcWall`` with its body, and each door or window a
void cut in its wall and filled by an ``IfcDoor`` / ``IfcWindow``. FreeCAD's
BIM workbench and Blender with Bonsai open it as a building, not a drawing.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

from openjarvis.creator.llm import CreatorError

WALL_HEIGHT = 2.7
DOOR = {"height": 2.1, "sill": 0.0}
WINDOW = {"height": 1.2, "sill": 0.9}


def _matrix(x: float, y: float, z: float, angle: float) -> Any:
    import numpy as np

    c, s = math.cos(angle), math.sin(angle)
    return np.array(
        [[c, -s, 0.0, x], [s, c, 0.0, y], [0.0, 0.0, 1.0, z], [0.0, 0.0, 0.0, 1.0]]
    )


def _clean_walls(walls: list[dict[str, Any]]) -> list[dict[str, float]]:
    out = []
    for wall in walls[:500]:
        try:
            x1, y1, x2, y2 = (float(wall[k]) for k in ("x1", "y1", "x2", "y2"))
            t = min(max(float(wall.get("thickness", 0.2)), 0.02), 2.0)
            h = min(max(float(wall.get("height", WALL_HEIGHT)), 0.5), 30.0)
        except (KeyError, TypeError, ValueError):
            continue
        if math.hypot(x2 - x1, y2 - y1) >= 0.01:
            out.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "t": t, "h": h})
    return out


def nearest_wall(
    walls: list[dict[str, float]], x: float, y: float
) -> tuple[int, float] | None:
    """The wall an opening sits in, and where along it (metres from its start)."""
    best: tuple[float, int, float] | None = None
    for i, w in enumerate(walls):
        dx, dy = w["x2"] - w["x1"], w["y2"] - w["y1"]
        length = math.hypot(dx, dy)
        along = ((x - w["x1"]) * dx + (y - w["y1"]) * dy) / length
        if along < -0.05 or along > length + 0.05:
            continue
        px, py = w["x1"] + dx / length * along, w["y1"] + dy / length * along
        dist = math.hypot(x - px, y - py)
        if dist <= w["t"] / 2 + 0.35 and (best is None or dist < best[0]):
            best = (dist, i, along)
    return (best[1], best[2]) if best else None


def plan_ifc(
    walls: list[dict[str, Any]],
    openings: list[dict[str, Any]] | None = None,
    name: str = "Plano de Sergio",
) -> bytes:
    """IFC4 bytes for the plan (metres)."""
    try:
        import ifcopenshell
        import ifcopenshell.api.aggregate
        import ifcopenshell.api.context
        import ifcopenshell.api.feature
        import ifcopenshell.api.geometry
        import ifcopenshell.api.project
        import ifcopenshell.api.root
        import ifcopenshell.api.spatial
        import ifcopenshell.api.unit
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise ImportError("ifcopenshell") from exc

    clean = _clean_walls(walls)
    if not clean:
        raise CreatorError("El plano no tiene muros.")
    api = ifcopenshell.api
    model = api.project.create_file(version="IFC4")
    project = api.root.create_entity(model, ifc_class="IfcProject", name=name[:80])
    api.unit.assign_unit(model, length={"is_metric": True, "raw": "METERS"})
    model_ctx = api.context.add_context(model, context_type="Model")
    body = api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )
    site = api.root.create_entity(model, ifc_class="IfcSite", name="Parcela")
    building = api.root.create_entity(model, ifc_class="IfcBuilding", name="Edificio")
    storey = api.root.create_entity(
        model, ifc_class="IfcBuildingStorey", name="Planta baja"
    )
    api.aggregate.assign_object(model, relating_object=project, products=[site])
    api.aggregate.assign_object(model, relating_object=site, products=[building])
    api.aggregate.assign_object(model, relating_object=building, products=[storey])

    made = []
    for n, w in enumerate(clean, 1):
        length = math.hypot(w["x2"] - w["x1"], w["y2"] - w["y1"])
        angle = math.atan2(w["y2"] - w["y1"], w["x2"] - w["x1"])
        wall = api.root.create_entity(model, ifc_class="IfcWall", name=f"Muro {n}")
        api.geometry.edit_object_placement(
            model, product=wall, matrix=_matrix(w["x1"], w["y1"], 0.0, angle)
        )
        rep = api.geometry.add_wall_representation(
            model,
            context=body,
            length=length,
            height=w["h"],
            thickness=w["t"],
            offset=-w["t"] / 2,
        )
        api.geometry.assign_representation(model, product=wall, representation=rep)
        api.spatial.assign_container(model, relating_structure=storey, products=[wall])
        made.append((wall, angle))

    for k, opening in enumerate((openings or [])[:500], 1):
        try:
            x, y = float(opening["x"]), float(opening["y"])
            width = min(max(float(opening.get("width", 0.9)), 0.3), 6.0)
        except (KeyError, TypeError, ValueError):
            continue
        hit = nearest_wall(clean, x, y)
        if hit is None:
            continue
        index, along = hit
        w = clean[index]
        wall, angle = made[index]
        door = opening.get("kind") == "puerta"
        spec = DOOR if door else WINDOW
        height = min(spec["height"], w["h"] - spec["sill"] - 0.05)
        start = max(0.0, along - width / 2)
        ox = w["x1"] + math.cos(angle) * start
        oy = w["y1"] + math.sin(angle) * start
        void = api.root.create_entity(
            model, ifc_class="IfcOpeningElement", name=f"Hueco {k}"
        )
        api.geometry.edit_object_placement(
            model, product=void, matrix=_matrix(ox, oy, spec["sill"], angle)
        )
        void_rep = api.geometry.add_wall_representation(
            model,
            context=body,
            length=width,
            height=height,
            thickness=w["t"] + 0.1,
            offset=-(w["t"] + 0.1) / 2,
        )
        api.geometry.assign_representation(model, product=void, representation=void_rep)
        api.feature.add_feature(model, feature=void, element=wall)
        fill = api.root.create_entity(
            model,
            ifc_class="IfcDoor" if door else "IfcWindow",
            name=f"{'Puerta' if door else 'Ventana'} {k}",
        )
        api.geometry.edit_object_placement(
            model, product=fill, matrix=_matrix(ox, oy, spec["sill"], angle)
        )
        fill_rep = api.geometry.add_wall_representation(
            model,
            context=body,
            length=width,
            height=height,
            thickness=0.05,
            offset=-0.025,
        )
        api.geometry.assign_representation(model, product=fill, representation=fill_rep)
        fill.OverallHeight, fill.OverallWidth = height, width
        api.feature.add_filling(model, opening=void, element=fill)
        api.spatial.assign_container(model, relating_structure=storey, products=[fill])

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "plano.ifc"
        model.write(str(path))
        return path.read_bytes()


__all__ = ["nearest_wall", "plan_ifc"]

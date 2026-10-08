"""Sergio's Blender VFX toolkit: each effect builds a Blender Python script.

    from openjarvis.vfx import EFFECTS, build_scene, run
    script = build_scene([("smoke_fire", {"kind": "fire"}), ("shaders", {"shader": "lava"})])
    result = run(script)   # needs Blender (SERGIO_BLENDER) or a bpy Python (SERGIO_BPY_PYTHON)
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

from openjarvis.vfx._base import BlenderRun, compose, find_blender, run

EFFECTS = ("smoke_fire", "fluid", "destruction", "cloth", "hair_fur", "volumetrics", "shaders", "geo_nodes")


def effect(name: str) -> ModuleType:
    if name not in EFFECTS:
        raise ValueError(f"unknown effect '{name}'; known: {', '.join(EFFECTS)}")
    return importlib.import_module(f"openjarvis.vfx.{name}")


def catalog() -> dict[str, dict[str, Any]]:
    """Every effect with its description and parameters (name -> (default, help))."""
    return {name: {"description": effect(name).DESCRIPTION, "params": effect(name).PARAMS} for name in EFFECTS}


def build_scene(steps: list[tuple[str, dict[str, Any]]], **compose_kw: Any) -> str:
    """One Blender script from (effect, params) steps, in order."""
    return compose([effect(name).build(**params) for name, params in steps], **compose_kw)


__all__ = ["EFFECTS", "BlenderRun", "build_scene", "catalog", "compose", "effect", "find_blender", "run"]

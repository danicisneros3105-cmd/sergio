"""Unreal Engine 5 projects from Creator (owner, 1 Nov 2026: «integra Unreal
Engine en Creator para poder también hacer juegos»).

Sergio writes a ready-to-open project: the ``.uproject`` (Blueprint, so no
compiler is needed) with Python editor scripting on, a game brief, and a
``Content/Python/init_unreal.py`` that UE runs when the editor opens. That
script builds the first level: floor, light, sky, player start, and every 3D
model of the game (the GLB files Creator made, imported and placed where the
brief says). Then the desktop opens it in Unreal (``creator_apps``).

UE itself comes from the Epic Games Launcher with the owner's free account;
Sergio never downloads the engine for him.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List

ENGINE = "5.5"
GENRES = (
    "tercera persona",
    "primera persona",
    "plataformas",
    "carreras",
    "puzle",
    "mundo abierto",
)
TEMPLATE_OF = {  # what the brief asks for → the starter the owner adds in UE
    "tercera persona": "Third Person",
    "primera persona": "First Person",
    "plataformas": "Third Person",
    "carreras": "Vehicle",
    "puzle": "Top Down",
    "mundo abierto": "Third Person",
}


class UnrealError(ValueError):
    """Something wrong in what was asked, in plain words."""


def slug(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]+", "", (name or "").title())
    if not clean or not clean[0].isalpha():
        clean = "Juego" + clean
    return clean[:20]


def uproject(name: str) -> Dict[str, Any]:
    return {
        "FileVersion": 3,
        "EngineAssociation": ENGINE,
        "Category": "",
        "Description": f"{name} — creado con Sergio",
        "Plugins": [
            {"Name": "PythonScriptPlugin", "Enabled": True},
            {"Name": "EditorScriptingUtilities", "Enabled": True},
            {"Name": "ModelingToolsEditorMode", "Enabled": True},
        ],
    }


def level_script(models: List[Dict[str, Any]]) -> str:
    """The editor script that builds the first level (runs inside Unreal)."""
    spec = json.dumps(models, ensure_ascii=False)
    return f'''"""Builds the first level when the project opens (written by Sergio)."""
import json
import os

import unreal

MODELS = json.loads({spec!r})
HERE = os.path.dirname(os.path.abspath(__file__))
DONE = os.path.join(HERE, ".nivel_hecho")

if not os.path.exists(DONE):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.new_level("/Game/Mapas/Inicio")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    floor = actors.spawn_actor_from_object(
        unreal.load_asset("/Engine/BasicShapes/Plane"), unreal.Vector(0, 0, 0)
    )
    floor.set_actor_scale3d(unreal.Vector(80, 80, 1))
    actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 800), unreal.Rotator(-40, 30, 0))
    actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 900))
    actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
    actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 120))
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    for i, m in enumerate(MODELS):
        path = os.path.join(HERE, "..", "Modelos", m["file"])
        if not os.path.exists(path):
            continue
        task = unreal.AssetImportTask()
        task.filename = path
        task.destination_path = "/Game/Modelos"
        task.automated = True
        task.save = True
        tools.import_asset_tasks([task])
        for asset_path in task.imported_object_paths:
            asset = unreal.load_asset(asset_path)
            if isinstance(asset, unreal.StaticMesh):
                x, y = m.get("x", 300 * (i + 1)), m.get("y", 0)
                actors.spawn_actor_from_object(asset, unreal.Vector(x, y, 0))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    open(DONE, "w").close()
    unreal.log("Sergio: nivel inicial listo")
'''


def brief(name: str, idea: str, genre: str) -> str:
    template = TEMPLATE_OF.get(genre, "Third Person")
    return (
        f"# {name}\n\n{idea.strip()}\n\n"
        f"- Género: {genre}. Plantilla de UE recomendada: «{template}» "
        "(en Unreal: Add → Add Feature or Content Pack).\n"
        "- El primer nivel lo arma `Content/Python/init_unreal.py` al abrir el proyecto.\n"
        "- Los modelos 3D de Sergio están en `Content/Modelos/`.\n"
    )


def build(
    name: str,
    idea: str,
    *,
    genre: str = "",
    models: List[Dict[str, Any]] | None = None,
    model_files: Dict[str, bytes] | None = None,
) -> bytes:
    """The whole project as a zip the desktop unpacks and opens."""
    if not (idea or "").strip():
        raise UnrealError("Dígame de qué trata el juego.")
    genre = (
        genre
        if genre in GENRES
        else next((g for g in GENRES if g in idea.lower()), "tercera persona")
    )
    title = (name or idea).strip()[:60]
    key = slug(title)
    models = [
        m
        for m in (models or [])
        if str(m.get("file", "")).lower().endswith((".glb", ".gltf", ".fbx", ".obj"))
    ]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{key}/{key}.uproject", json.dumps(uproject(title), indent=2))
        z.writestr(f"{key}/Content/Python/init_unreal.py", level_script(models))
        z.writestr(f"{key}/LEEME.md", brief(title, idea, genre))
        for fname, data in (model_files or {}).items():
            z.writestr(f"{key}/Content/Modelos/{Path(fname).name}", data)
    return out.getvalue()


__all__ = [
    "GENRES",
    "UnrealError",
    "brief",
    "build",
    "level_script",
    "slug",
    "uproject",
]

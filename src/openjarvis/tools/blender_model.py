"""Model a real object in Blender from a photo (the thing in your hands).

Gemini looks at the camera photo, works out what the object is, its real
size, parts and materials, and writes a detailed Blender script for it.
Before it runs on the user's laptop the script is checked: it must compile,
and anything that is not modelling (files, network, programs) is refused.
Sergio adds the end himself: lights, camera and saving the .blend project.
"""

from __future__ import annotations

import ast
import json
import os
import re
from typing import Any

MODELS = (
    "gemini-3.1-pro-preview",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash",
)

PROMPT = """You are a senior 3D modeller. The photo comes from the user's webcam: \
they are holding or showing an object. {note}
1. Identify the main object (the one held in the hands, else the most prominent).
2. Estimate its real dimensions in centimetres from context (hands are ~18 cm long).
3. Model it in Blender 4.x with Python (bpy) in HIGH DETAIL, true to the photo: \
every visible part as its own object (body, handle, lid, buttons, labels, screws...), \
correct proportions in metres, bevels on hard edges, subdivision surface on organic \
shapes, and Principled BSDF materials matching colours, roughness, metal or glass.
Rules for the script:
- Only bpy, bmesh, math, mathutils. No os, sys, subprocess, files, network or exec.
- Start from an empty scene: bpy.ops.wm.read_factory_settings(use_empty=True).
- Put the object on the ground (lowest point at z = 0), centred at the origin.
- Parent all parts to one empty named after the object.
- Do NOT add cameras, lights, render settings or save the file (Sergio does).
Answer ONLY with JSON:
{{"name": "short Spanish name", "description": "one Spanish sentence of what it is and \
its materials", "dimensions_cm": [width, depth, height], "parts": number of parts, \
"script": "the complete Python script"}}"""

FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "requests", "urllib",
    "http", "ftplib", "ctypes", "importlib", "pickle", "marshal", "builtins",
    "multiprocessing", "threading", "asyncio", "webbrowser", "glob", "io", "tempfile",
}  # fmt: skip
FORBIDDEN_CALLS = {
    "exec",
    "eval",
    "compile",
    "open",
    "__import__",
    "getattr",
    "setattr",
    "input",
}
FORBIDDEN_OPS = re.compile(
    r"bpy\.ops\.(wm\.(save|open|quit|url|read_homefile|append|link)|script\.|"
    r"preferences\.|extensions\.|import_|export_)|bpy\.utils\.(register|unregister)|"
    r"bpy\.app\.handlers|\.filepath\s*="
)
ALLOWED_OPS = ("bpy.ops.wm.read_factory_settings",)


class UnsafeScript(ValueError):
    """The generated script does something other than modelling."""


def check_script(script: str) -> None:
    """Refuse anything that is not plain modelling (raises UnsafeScript)."""
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        raise UnsafeScript(f"no compila: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                if name.split(".")[0] in FORBIDDEN_MODULES:
                    raise UnsafeScript(f"importa {name}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                raise UnsafeScript(f"usa {node.func.id}()")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise UnsafeScript(f"usa {node.attr}")
    cleaned = script
    for allowed in ALLOWED_OPS:
        cleaned = cleaned.replace(allowed, "")
    found = FORBIDDEN_OPS.search(cleaned)
    if found:
        raise UnsafeScript(f"usa {found.group(0)}")


PREVIEW = """
# --- Sergio: a quick render to check the work ---
try:
    _scene.render.engine = "CYCLES"
    _scene.cycles.samples = 24
    _scene.cycles.use_denoising = False
    _scene.render.resolution_x, _scene.render.resolution_y = 640, 480
    _scene.render.filepath = {path}
    _bpy.ops.render.render(write_still=True)
    print("SERGIO_PREVIEW", {path})
except Exception as _exc:
    print("SERGIO_PREVIEW_FAILED", _exc)
"""


def finish_script(script: str, save_path: str, name: str, preview_path: str = "") -> str:
    """Sergio's ending: light, camera framing the object, save the project
    (and, for the checking loop, a quick render to look at)."""
    return (
        script.rstrip()
        + "\n\n# --- Sergio: lights, camera and saving the project ---\n"
        + f"""import bpy as _bpy, math as _math
from mathutils import Vector as _V
_scene = _bpy.context.scene
_objs = [o for o in _scene.objects if o.type == "MESH"]
_lo = _V((min((o.matrix_world @ _V(c))[i] for o in _objs for c in o.bound_box) for i in range(3))) if _objs else _V((0, 0, 0))
_hi = _V((max((o.matrix_world @ _V(c))[i] for o in _objs for c in o.bound_box) for i in range(3))) if _objs else _V((1, 1, 1))
_centre, _size = (_lo + _hi) / 2, max((_hi - _lo).length, 0.05)
_sun = _bpy.data.objects.new("Sol", _bpy.data.lights.new("Sol", "SUN"))
_sun.data.energy = 4.5
_sun.rotation_euler = (0.9, 0.15, 0.7)
_scene.collection.objects.link(_sun)
_fill = _bpy.data.objects.new("Relleno", _bpy.data.lights.new("Relleno", "AREA"))
_fill.data.energy = 60 * _size * _size
_fill.location = _centre + _V((-_size, -_size, _size))
_scene.collection.objects.link(_fill)
_cam = _bpy.data.objects.new("Cámara", _bpy.data.cameras.new("Cámara"))
_cam.location = _centre + _V((_size * 0.55, -_size * 1.05, _size * 0.65))
_dir = _centre - _cam.location
_cam.rotation_euler = _dir.to_track_quat("-Z", "Y").to_euler()
_scene.collection.objects.link(_cam)
_scene.camera = _cam
if _scene.world is None:
    _scene.world = _bpy.data.worlds.new("Mundo")
_scene.world.color = (0.16, 0.17, 0.19)
_scene["sergio_model"] = {json.dumps(name)}
_path = {json.dumps(save_path)}
_bpy.ops.wm.save_as_mainfile(filepath=_path)
print("SERGIO_SAVED", _path, len(_objs))
"""
        + (PREVIEW.format(path=json.dumps(preview_path)) if preview_path else "")
    )


def _ask(image: bytes, prompt: str, mime: str) -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY (sergio nube configurar --gemini …)")
    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs
    from openjarvis.engine.google_client import SwitchingClient

    client = SwitchingClient(key)
    last: Exception | None = None
    for model in MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=image, mime_type=mime), prompt],
                config=types.GenerateContentConfig(
                    **google_config_kwargs(model, 0.4, 24000, "high"),
                    response_mime_type="application/json",
                ),
            )
            text = str(resp.text or "").strip()
            parse_model(text)  # an unusable answer: ask the next model
            return text
        except Exception as exc:  # noqa: BLE001 — next model
            last = exc
    raise RuntimeError(f"Gemini no pudo modelar el objeto: {last}")


def parse_model(text: str) -> dict[str, Any]:
    found = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(found.group(0)) if found else {}
    except ValueError:
        data = {}
    script = str(data.get("script") or "")
    if not script.strip():
        raise RuntimeError("Gemini no devolvió un script de Blender.")
    dims = data.get("dimensions_cm") or []
    try:
        dims = [round(float(d), 1) for d in dims][:3]
    except (TypeError, ValueError):
        dims = []
    return {
        "name": str(data.get("name") or "objeto")[:60],
        "description": str(data.get("description") or "")[:400],
        "dimensions_cm": dims,
        "parts": int(data.get("parts") or 0)
        if str(data.get("parts") or "0").isdigit()
        else 0,
        "script": script,
    }


def model_object(
    image: bytes,
    save_path: str,
    note: str = "",
    mime: str = "image/jpeg",
    ask: Any = None,
    tries: int = 2,
    preview_path: str = "",
) -> dict[str, Any]:
    """Photo -> {name, description, dimensions_cm, parts, script (ready to run)}."""
    prompt = PROMPT.format(note=f"The user says: {note}" if note.strip() else "")
    problem = ""
    for _ in range(tries):
        text = (ask or _ask)(
            image,
            prompt
            + (
                f"\nYour previous script was refused: {problem}. Fix it."
                if problem
                else ""
            ),
            mime,
        )
        model = parse_model(text)
        try:
            check_script(model["script"])
        except UnsafeScript as exc:
            problem = str(exc)
            continue
        model["raw_script"] = model["script"]
        model["script"] = finish_script(model["script"], save_path, model["name"], preview_path)
        return model
    raise RuntimeError(
        f"El script de Blender no era seguro ({problem}); no lo ejecuto."
    )


__all__ = [
    "UnsafeScript",
    "check_script",
    "finish_script",
    "model_object",
    "parse_model",
]

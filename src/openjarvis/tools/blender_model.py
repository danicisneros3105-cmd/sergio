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
# --- Sergio: four views on one sheet, so the review sees the whole shape ---
# Top left the finished look (3/4 view); top right FRONT, bottom left RIGHT
# side and bottom right TOP, orthographic and at the same scale, like a
# blueprint (proportions can be compared directly).
try:
    import os as _os
    _out = {path}
    _cell = 512
    _shots = []
    _span = max(_hi.x - _lo.x, _hi.y - _lo.y, _hi.z - _lo.z, 0.02) * 1.18
    for _m in _bpy.data.materials:  # the workbench views show the real colours
        try:
            _bsdf = _m.node_tree.nodes.get("Principled BSDF") if _m.use_nodes else None
            if _bsdf is not None:
                _m.diffuse_color = tuple(_bsdf.inputs["Base Color"].default_value)
        except Exception:
            pass
    _views = [
        ("beauty", None, None),
        ("front", (0.0, -1.0, 0.0), (_math.pi / 2, 0.0, 0.0)),
        ("right", (1.0, 0.0, 0.0), (_math.pi / 2, 0.0, _math.pi / 2)),
        ("top", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0)),
    ]
    for _name, _axis, _rot in _views:
        _scene.render.resolution_x = _scene.render.resolution_y = _cell
        _scene.render.resolution_percentage = 100
        try:
            _scene.render.image_settings.media_type = "IMAGE"  # Blender 5
        except Exception:
            pass
        _scene.render.image_settings.file_format = "PNG"
        _scene.render.image_settings.color_depth = "8"
        if _axis is None:
            _scene.camera = _cam
            _engines = ("CYCLES", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH")
        else:
            _ocam = _bpy.data.objects.new("Vista_" + _name, _bpy.data.cameras.new("Vista_" + _name))
            _ocam.data.type = "ORTHO"
            _ocam.data.ortho_scale = _span
            _ocam.location = _centre + _V(_axis) * (_size * 3 + 1)
            _ocam.rotation_euler = _rot
            _ocam.data.clip_end = _size * 8 + 10
            _scene.collection.objects.link(_ocam)
            _scene.camera = _ocam
            _engines = ("BLENDER_WORKBENCH",)
        for _engine in _engines:
            try:
                _scene.render.engine = _engine
                break
            except Exception:
                continue
        if _scene.render.engine == "CYCLES":
            _scene.cycles.samples = 24
            _scene.cycles.use_denoising = False
        if _scene.render.engine == "BLENDER_WORKBENCH":
            _shade = _scene.display.shading
            _shade.light = "STUDIO"
            _shade.color_type = "MATERIAL"
            _shade.show_cavity = True
            _shade.show_object_outline = True
        _file = _out[:-4] + "-" + _name + ".png"
        _scene.render.filepath = _file
        _bpy.ops.render.render(write_still=True)
        _shots.append(_file)
    _scene.camera = _cam
    import numpy as _np
    _sheet = _np.ones((_cell * 2, _cell * 2, 4), dtype=_np.float32)
    for _i, _file in enumerate(_shots):
        _img = _bpy.data.images.load(_file)
        _px = _np.empty(_img.size[0] * _img.size[1] * 4, dtype=_np.float32)
        _img.pixels.foreach_get(_px)
        _px = _px.reshape(_img.size[1], _img.size[0], 4)[:_cell, :_cell]
        _row, _col = divmod(_i, 2)
        _y0 = (1 - _row) * _cell  # image rows start at the bottom
        _sheet[_y0:_y0 + _px.shape[0], _col * _cell:_col * _cell + _px.shape[1]] = _px
        _bpy.data.images.remove(_img)
        try:
            _os.remove(_file)
        except OSError:
            pass
    _sheet[_cell - 1:_cell + 1, :, :3] = 0.35  # thin dividers between the views
    _sheet[:, _cell - 1:_cell + 1, :3] = 0.35
    _final = _bpy.data.images.new("SergioVistas", _cell * 2, _cell * 2, alpha=True)
    _final.pixels.foreach_set(_sheet.ravel())
    _final.filepath_raw = _out
    _final.file_format = "PNG"
    _final.save()
    print("SERGIO_PREVIEW", _out)
    print("SERGIO_VIEW_SCALE each orthographic view is %.1f cm wide" % (_span * 100))
except Exception as _exc:
    print("SERGIO_PREVIEW_FAILED", _exc)
"""


# Checked before saving, like a technical director would: closed parts get
# their normals pointing out, curved parts (subdivision) are shaded smooth,
# scale is metric 1:1, and the rest is reported to the review round
# (non-manifold edges, loose vertices) instead of being hidden.
TOPOLOGY = """
# --- Sergio: topology check (normals, manifold, smooth shading, units) ---
import bmesh as _bmesh
_topo = {"flipped": 0, "bad_edges": 0, "open_edges": 0, "loose": 0, "smoothed": 0}
try:
    _scene.unit_settings.system = "METRIC"
    _scene.unit_settings.scale_length = 1.0
except Exception:
    pass
for _data in {o.data for o in _objs}:
    try:
        _b = _bmesh.new()
        _b.from_mesh(_data)
        _border = sum(1 for e in _b.edges if len(e.link_faces) == 1)
        _topo["bad_edges"] += sum(1 for e in _b.edges if len(e.link_faces) > 2)
        _topo["open_edges"] += _border
        _topo["loose"] += sum(1 for v in _b.verts if not v.link_edges)
        if _b.faces and not _border:  # closed: the outside is well defined
            _before = [f.normal.copy() for f in _b.faces]
            _bmesh.ops.recalc_face_normals(_b, faces=list(_b.faces))
            _b.normal_update()
            _topo["flipped"] += sum(1 for f, n in zip(_b.faces, _before) if f.normal.dot(n) < 0)
            _b.to_mesh(_data)
            _data.update()
        _b.free()
    except Exception as _exc:
        print("SERGIO_TOPOLOGY_SKIP", _exc)
for _o in _objs:
    try:
        if any(m.type == "SUBSURF" for m in _o.modifiers) and not any(p.use_smooth for p in _o.data.polygons):
            _o.data.polygons.foreach_set("use_smooth", [True] * len(_o.data.polygons))
            _topo["smoothed"] += 1
    except Exception:
        pass
print("SERGIO_TOPOLOGY normals fixed %(flipped)d, non-manifold edges %(bad_edges)d, open border edges "
      "%(open_edges)d, loose vertices %(loose)d, curved parts smoothed %(smoothed)d" % _topo)
"""

# The saved project is ready for a final render (F12), with production
# settings: Cycles 256 samples with adaptive sampling (noise threshold 0.01,
# at least 32), OIDN denoising fed with albedo and normals, 32 transparency
# bounces (no black patches in overlapping glass or leaves), no volume
# bounces, persistent data, and Z / vector / Cryptomatte passes in a 32-bit
# multilayer EXR for compositing. The review previews stay quick (24 samples).
RENDER = """
# --- Sergio: production render settings (saved with the project) ---
_rs = (
    ("render.engine", "CYCLES"), ("cycles.samples", 256), ("cycles.use_adaptive_sampling", True),
    ("cycles.adaptive_threshold", 0.01), ("cycles.adaptive_min_samples", 32),
    ("cycles.use_denoising", True), ("cycles.denoiser", "OPENIMAGEDENOISE"),
    ("cycles.denoising_input_passes", "RGB_ALBEDO_NORMAL"), ("cycles.max_bounces", 12),
    ("cycles.diffuse_bounces", 4), ("cycles.glossy_bounces", 4), ("cycles.transmission_bounces", 12),
    ("cycles.transparent_max_bounces", 32), ("cycles.volume_bounces", 0),
    ("render.use_persistent_data", True), ("eevee.taa_render_samples", 64),
    ("render.image_settings.media_type", "MULTI_LAYER_IMAGE"),  # Blender 5
    ("render.image_settings.file_format", "OPEN_EXR_MULTILAYER"),  # Blender 4
    ("render.image_settings.color_depth", "32"),
)
for _key, _value in _rs:
    try:
        _owner, _attr = _key.rsplit(".", 1)
        _target = _scene
        for _part in _owner.split("."):
            _target = getattr(_target, _part)
        setattr(_target, _attr, _value)
    except Exception:
        pass
for _vl in _scene.view_layers:
    for _attr in ("use_pass_z", "use_pass_vector", "use_pass_cryptomatte_object", "use_pass_cryptomatte_material"):
        try:
            setattr(_vl, _attr, True)
        except Exception:
            pass
    try:
        _vl.cycles.denoising_store_passes = True
    except Exception:
        pass
"""


# The model's script runs step by step: a wrong API detail (a socket name, an
# operator argument) used to stop everything and leave a cube or nothing.
# Now that step is skipped and reported (SERGIO_STEP_ERROR), the rest of the
# model is built and saved, and the review round fixes the failed step.
RESILIENT = """import ast as _ast, functools as _ft, traceback as _tb
_SOURCE = __SOURCE__
_ns = {"__name__": "__main__"}


def _safe(fn):
    @_ft.wraps(fn)
    def inner(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as _e:
            print("SERGIO_STEP_ERROR in %s(): %s: %s" % (fn.__name__, type(_e).__name__, _e))
            _tb.print_exc()
            return None
    return inner


_ns["_sergio_safe"] = _safe
for _node in _ast.parse(_SOURCE).body:
    if isinstance(_node, _ast.FunctionDef):
        _node.decorator_list.append(_ast.Name(id="_sergio_safe", ctx=_ast.Load()))
    _code = _ast.fix_missing_locations(_ast.Module(body=[_node], type_ignores=[]))
    try:
        exec(compile(_code, "<modelo>", "exec"), _ns)
    except Exception as _e:
        print("SERGIO_STEP_ERROR line %d: %s: %s" % (_node.lineno, type(_e).__name__, _e))
        _tb.print_exc()
"""


def finish_script(script: str, save_path: str, name: str, preview_path: str = "") -> str:
    """Sergio's ending: light, camera framing the object, save the project
    (and, for the checking loop, a quick render to look at)."""
    return (
        RESILIENT.replace("__SOURCE__", json.dumps(script.rstrip()))
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
_cam.location = _centre + _V((_size * 0.75, -_size * 1.45, _size * 0.85))
_dir = _centre - _cam.location
_cam.rotation_euler = _dir.to_track_quat("-Z", "Y").to_euler()
_scene.collection.objects.link(_cam)
_scene.camera = _cam
if _scene.world is None:
    _scene.world = _bpy.data.worlds.new("Mundo")
_scene.world.color = (0.16, 0.17, 0.19)
_scene["sergio_model"] = {json.dumps(name)}
""" + TOPOLOGY + RENDER + f"""_path = {json.dumps(save_path)}
_bpy.ops.wm.save_as_mainfile(filepath=_path)
print("SERGIO_SAVED", _path, len(_objs))
_dims = (_hi - _lo) * 100
print("SERGIO_DIMS width %.1f x depth %.1f x height %.1f cm (lowest point z = %.1f cm)" % (_dims.x, _dims.y, _dims.z, _lo.z * 100))
print("SERGIO_PARTS %d meshes: %s" % (len(_objs), ", ".join(sorted(o.name for o in _objs)[:80])))
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

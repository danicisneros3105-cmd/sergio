"""Shared machinery for Sergio's Blender VFX tools.

Every effect module exposes ``PARAMS`` (name -> (default, help)) and
``build(**params) -> str``, a Blender Python snippet. ``compose`` joins
snippets after ``PRELUDE`` — version-proof helpers for Blender 4.2 LTS to
5.x (EEVEE's engine id, node settings that became input sockets in 5.0,
the compositor that became a node group, Principled BSDF socket names) —
and ends with saving the .blend and optional preview renders. ``run``
executes the script in a real Blender (the ``blender`` program, or a
Python that has the ``bpy`` module) and returns what it reported.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PRELUDE = r'''
import bpy, bmesh, math, random, json
from mathutils import Vector, Matrix, Euler

VFX_INFO = {}
VFX_VERSION = bpy.app.version


def vfx_info(**kw):
    VFX_INFO.update(kw)


def vfx_reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.frame_start, sc.frame_end = 1, 48
    sc.render.fps = 24
    return sc


def vfx_engine(kind="EEVEE", samples=32):
    sc = bpy.context.scene
    ids = [e.identifier for e in sc.render.bl_rna.properties["engine"].enum_items]
    if kind.upper().startswith("CYC"):
        sc.render.engine = "CYCLES"
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        try:
            sc.cycles.device = "CPU"
        except Exception:
            pass
    else:
        sc.render.engine = next((e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE") if e in ids), ids[0])
        try:
            sc.eevee.taa_render_samples = samples
        except Exception:
            pass
    return sc.render.engine


def vfx_set(node, name, value):
    """Set a node setting whether it is an input socket (5.0+) or a property (4.x)."""
    sock = node.inputs.get(name) if hasattr(node, "inputs") else None
    if sock is not None and hasattr(sock, "default_value"):
        try:
            sock.default_value = value
            return True
        except Exception:
            pass
    for attr in (name, name.lower().replace(" ", "_")):
        if hasattr(node, attr):
            try:
                setattr(node, attr, value)
                return True
            except Exception:
                pass
    return False


def vfx_input(node, names, value):
    """Set the first existing input socket among *names* (socket names differ by version)."""
    for n in ([names] if isinstance(names, str) else names):
        s = node.inputs.get(n)
        if s is not None:
            try:
                s.default_value = value
                return True
            except Exception:
                continue
    return False


def vfx_material(name, color=(0.8, 0.8, 0.8, 1), metallic=0.0, roughness=0.5, **extra):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    vfx_input(bsdf, "Base Color", color)
    vfx_input(bsdf, "Metallic", metallic)
    vfx_input(bsdf, "Roughness", roughness)
    aliases = {
        "transmission": ["Transmission Weight", "Transmission"],
        "subsurface": ["Subsurface Weight", "Subsurface"],
        "coat": ["Coat Weight", "Clearcoat"],
        "emission_color": ["Emission Color", "Emission"],
        "emission_strength": ["Emission Strength"],
        "ior": ["IOR"],
        "alpha": ["Alpha"],
        "sheen": ["Sheen Weight", "Sheen"],
        "anisotropic": ["Anisotropic"],
        "specular": ["Specular IOR Level", "Specular"],
    }
    for key, value in extra.items():
        vfx_input(bsdf, aliases.get(key, [key]), value)
    return mat


def vfx_assign(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def vfx_camera(location=(7, -7, 4.5), target=(0, 0, 1), lens=40):
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = lens
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    direction = Vector(target) - Vector(location)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def vfx_light(kind="SUN", energy=3.0, location=(4, -3, 8), rotation=(0.6, 0.2, 0.8), color=(1, 1, 1)):
    data = bpy.data.lights.new(kind.title(), kind)
    data.energy = energy
    data.color = color
    obj = bpy.data.objects.new(kind.title(), data)
    obj.location, obj.rotation_euler = location, rotation
    bpy.context.scene.collection.objects.link(obj)
    return obj


def vfx_world(color=(0.05, 0.05, 0.06), strength=1.0):
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*color, 1)
    bg.inputs[1].default_value = strength
    return world


def vfx_mesh(kind, name, location=(0, 0, 0), size=1.0, **kw):
    ops = {"cube": bpy.ops.mesh.primitive_cube_add, "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
           "ico": bpy.ops.mesh.primitive_ico_sphere_add, "plane": bpy.ops.mesh.primitive_plane_add,
           "cylinder": bpy.ops.mesh.primitive_cylinder_add, "cone": bpy.ops.mesh.primitive_cone_add,
           "torus": bpy.ops.mesh.primitive_torus_add, "monkey": bpy.ops.mesh.primitive_monkey_add,
           "grid": bpy.ops.mesh.primitive_grid_add}
    if kind in ("cube", "plane", "monkey", "grid"):
        ops[kind](size=size, location=location, **kw)
    elif kind == "torus":
        ops[kind](location=location, **kw)
    else:
        ops[kind](radius=size, location=location, **kw)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def vfx_ground(size=30, color=(0.18, 0.18, 0.19, 1)):
    g = vfx_mesh("plane", "Ground", size=size)
    vfx_assign(g, vfx_material("Ground", color, roughness=0.8))
    return g


def vfx_comp_tree():
    """The compositor node tree (a node group in 5.0+, scene.node_tree in 4.x) and
    the socket the final image must reach."""
    sc = bpy.context.scene
    if hasattr(sc, "compositing_node_group"):
        tree = sc.compositing_node_group
        if tree is None:
            tree = bpy.data.node_groups.new("Compositing", "CompositorNodeTree")
            sc.compositing_node_group = tree
        if not any(i.in_out == "OUTPUT" for i in tree.interface.items_tree):
            tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        out = next((n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"), None) or tree.nodes.new("NodeGroupOutput")
        rl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None) or tree.nodes.new("CompositorNodeRLayers")
        return tree, rl, out.inputs[0]
    sc.use_nodes = True
    tree = sc.node_tree
    rl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None) or tree.nodes.new("CompositorNodeRLayers")
    comp = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeComposite"), None) or tree.nodes.new("CompositorNodeComposite")
    return tree, rl, comp.inputs["Image"]


def vfx_comp_chain(build):
    """Insert a chain between Render Layers and the output: build(tree, image_socket, rl) -> socket."""
    tree, rl, final = vfx_comp_tree()
    for link in list(final.links):
        tree.links.remove(link)
    source = VFX_COMP_LAST.get("socket") or rl.outputs["Image"]
    result = build(tree, source, rl)
    tree.links.new(result, final)
    VFX_COMP_LAST["socket"] = result
    return tree


VFX_COMP_LAST = {}


def vfx_bake(frames=None):
    """Bake every physics cache in the scene (fluids, cloth, rigid bodies)."""
    sc = bpy.context.scene
    if frames:
        sc.frame_end = sc.frame_start + frames - 1
    baked = []
    for obj in sc.objects:
        for mod in obj.modifiers:
            if mod.type == "FLUID" and mod.fluid_type == "DOMAIN":
                mod.domain_settings.cache_frame_start = sc.frame_start
                mod.domain_settings.cache_frame_end = sc.frame_end
                with bpy.context.temp_override(object=obj, active_object=obj, scene=sc):
                    bpy.ops.fluid.bake_all()
                baked.append(f"fluid:{obj.name}")
    for frame in range(sc.frame_start, sc.frame_end + 1):  # cloth/rigid/particles step by frame
        sc.frame_set(frame)
    return baked
'''

FINISH = r'''
sc = bpy.context.scene
VFX_INFO.setdefault("objects", len(sc.objects))
VFX_INFO.setdefault("engine", sc.render.engine)
VFX_INFO["blender"] = bpy.app.version_string
if __SAVE__:
    bpy.ops.wm.save_as_mainfile(filepath=__SAVE__)
    VFX_INFO["blend"] = __SAVE__
if __PREVIEW__:
    sc.render.resolution_x, sc.render.resolution_y = __RES__
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    shots = []
    for i, frame in enumerate(__FRAMES__):
        sc.frame_set(frame)
        sc.render.filepath = __PREVIEW__.replace(".png", f"_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        shots.append(sc.render.filepath)
    VFX_INFO["previews"] = shots
print("VFX_INFO " + json.dumps(VFX_INFO, default=str))
print("VFX_OK")
'''


def compose(parts: list[str], *, save: str = "", preview: str = "", frames: tuple[int, ...] = (1,),
            resolution: tuple[int, int] = (640, 360), reset: bool = True) -> str:
    """One runnable Blender script from effect snippets."""
    body = "\n".join(parts)
    head = PRELUDE + ("\nvfx_reset()\n" if reset else "\n")
    tail = (FINISH.replace("__SAVE__", json.dumps(save)).replace("__PREVIEW__", json.dumps(preview))
            .replace("__FRAMES__", json.dumps(list(frames))).replace("__RES__", json.dumps(list(resolution))))
    return head + "\n# ---- effects ----\n" + body + "\n" + tail


def py(value: Any) -> str:
    """A Python literal for *value*, safe to paste into a script."""
    return repr(value) if not isinstance(value, str) else json.dumps(value)


def params_with_defaults(params_spec: dict[str, tuple[Any, str]], given: dict[str, Any]) -> dict[str, Any]:
    """Defaults merged with *given*; unknown names are rejected; types follow the default."""
    unknown = set(given) - set(params_spec)
    if unknown:
        raise ValueError(f"unknown parameter(s): {', '.join(sorted(unknown))}; known: {', '.join(params_spec)}")
    out = {}
    for name, (default, _help) in params_spec.items():
        value = given.get(name, default)
        if isinstance(default, bool):
            value = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "si", "sí")
        elif isinstance(default, int) and not isinstance(default, bool):
            value = int(float(value))
        elif isinstance(default, float):
            value = float(value)
        elif isinstance(default, (tuple, list)) and isinstance(value, (tuple, list)):
            value = tuple(value)
        out[name] = value
    return out


# -- running Blender -----------------------------------------------------------
WINDOWS_BLENDER = [Path(p) for p in (
    r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
)]


def find_blender() -> list[str] | None:
    """The command that runs a script in Blender: ``blender -b --python``, or a
    Python with the bpy module (SERGIO_BPY_PYTHON)."""
    exe = os.environ.get("SERGIO_BLENDER") or shutil.which("blender")
    if not exe:
        exe = next((str(p) for p in WINDOWS_BLENDER if p.exists()), None)
    if exe:
        return [exe, "-b", "--factory-startup", "--python-exit-code", "1", "--python"]
    bpy_python = os.environ.get("SERGIO_BPY_PYTHON")
    if bpy_python:
        return [bpy_python]
    return None


@dataclass
class BlenderRun:
    ok: bool
    info: dict = field(default_factory=dict)
    log: str = ""
    script: str = ""


def run(script: str, *, timeout: float = 1800.0, env: dict[str, str] | None = None) -> BlenderRun:
    """Execute *script* in Blender and parse what it reported."""
    cmd = find_blender()
    if cmd is None:
        return BlenderRun(False, {}, "Blender not found: install it or set SERGIO_BLENDER / SERGIO_BPY_PYTHON.", script)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sergio_vfx.py"
        path.write_text(script, "utf-8")
        try:
            proc = subprocess.run(cmd + [str(path)], capture_output=True, text=True, timeout=timeout,
                                  env={**os.environ, **(env or {})}, cwd=tmp)
        except subprocess.TimeoutExpired:
            return BlenderRun(False, {}, f"Blender timed out after {timeout:.0f} s", script)
    log = proc.stdout + proc.stderr
    info: dict = {}
    for line in log.splitlines():
        if line.startswith("VFX_INFO "):
            try:
                info = json.loads(line[9:])
            except ValueError:
                pass
    return BlenderRun("VFX_OK" in log and proc.returncode == 0, info, log[-8000:], script)


__all__ = ["PRELUDE", "BlenderRun", "compose", "find_blender", "params_with_defaults", "py", "run"]

"""Shaders: a PBR library plus VFX shaders, as Blender node trees.

PBR presets use measured-style values (metal IOR/roughness, glass
transmission and IOR, car paint with clear coat, skin with subsurface,
procedural wood and concrete). VFX shaders: hologram (fresnel rim +
scanlines + transparency), force field (fresnel glow + moving noise),
dissolve (noise threshold with a glowing burn edge), lava (animated
emissive noise) and energy (pulsing emission). Version-proof socket names.
"""

from __future__ import annotations

from openjarvis.vfx._base import params_with_defaults, py

DESCRIPTION = "PBR materials (metal, glass, car paint, skin, wood, concrete) and VFX shaders (hologram, force field, dissolve, lava, energy)."
PBR = {
    "gold": dict(color=(1.0, 0.77, 0.34, 1), metallic=1.0, roughness=0.18),
    "steel": dict(
        color=(0.56, 0.57, 0.58, 1), metallic=1.0, roughness=0.3, anisotropic=0.4
    ),
    "copper": dict(color=(0.95, 0.64, 0.54, 1), metallic=1.0, roughness=0.25),
    "glass": dict(color=(1, 1, 1, 1), roughness=0.0, transmission=1.0, ior=1.5),
    "water": dict(color=(0.9, 0.95, 1, 1), roughness=0.02, transmission=1.0, ior=1.333),
    "plastic": dict(color=(0.8, 0.1, 0.1, 1), roughness=0.35),
    "rubber": dict(color=(0.05, 0.05, 0.05, 1), roughness=0.9),
    "car_paint": dict(
        color=(0.6, 0.02, 0.03, 1), metallic=0.6, roughness=0.35, coat=1.0
    ),
    "skin": dict(color=(0.8, 0.58, 0.47, 1), roughness=0.45, subsurface=0.3),
    "velvet": dict(color=(0.3, 0.02, 0.1, 1), roughness=0.9, sheen=1.0),
}
VFX = ("hologram", "force_field", "dissolve", "lava", "energy", "wood", "concrete")
PARAMS = {
    "shader": ("hologram", f"PBR: {', '.join(PBR)}; VFX/procedural: {', '.join(VFX)}"),
    "target": (
        "monkey",
        "object to shade: monkey, sphere, cube, torus, cylinder or the name of an object in the scene",
    ),
    "color": ((0.1, 0.7, 1.0), "main colour for VFX shaders"),
    "strength": (4.0, "emission strength for glowing shaders"),
    "animate": (True, "animate time-based shaders (noise drift, pulse, dissolve)"),
}


def build(**kw) -> str:
    p = params_with_defaults(PARAMS, kw)
    shader = str(p["shader"]).lower()
    pbr = PBR.get(shader)
    target = str(p["target"])
    return f"""
shader_name = {py(shader)}
target_name = {py(target)}
obj = bpy.data.objects.get(target_name) or vfx_mesh(target_name if target_name in ("monkey", "sphere", "cube", "torus", "cylinder") else "monkey",
                                                     "Shaded", location=(0, 0, 1), size=1)
if obj.type == "MESH" and len(obj.data.polygons) < 2000:
    obj.modifiers.new("Smooth", "SUBSURF").levels = 2
    for poly in obj.data.polygons:
        poly.use_smooth = True
color = (*{py(tuple(p["color"]))}, 1)
strength = {p["strength"]}
animate = {p["animate"]}
pbr = {py(pbr)}
if pbr:
    mat = vfx_material(shader_name.title(), **pbr)
else:
    mat = bpy.data.materials.new(shader_name.title())
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    L = nt.links.new
    def node(kind, **inputs):
        n = nt.nodes.new(kind)
        for k, v in inputs.items():
            vfx_input(n, k, v)
        return n
    def math_node(op, a=None, b=None):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = op
        if a is not None and not hasattr(a, "links"):
            n.inputs[0].default_value = a
        if b is not None and not hasattr(b, "links"):
            n.inputs[1].default_value = b
        return n
    def time_driver(sock, speed=0.05):
        if animate:
            fc = sock.driver_add("default_value")
            fc.driver.expression = f"frame*{{speed}}"
    try:
        mat.blend_method = "BLEND"
    except Exception:
        pass
    try:
        mat.surface_render_method = "BLENDED"
    except Exception:
        pass
    if shader_name in ("hologram", "force_field"):
        fres = node("ShaderNodeLayerWeight", Blend=0.35)
        emit = node("ShaderNodeEmission", Color=color, Strength=strength)
        transp = node("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        coord = node("ShaderNodeTexCoord")
        if shader_name == "hologram":
            wave = node("ShaderNodeTexWave", Scale=40.0, Distortion=0.0)
            try:
                wave.bands_direction = "Z"
            except Exception:
                pass
            L(coord.outputs["Object"], wave.inputs["Vector"])
            time_driver(wave.inputs["Phase Offset"], 0.2) if wave.inputs.get("Phase Offset") else None
            lines = math_node("MULTIPLY", None, 0.6)
            L(wave.outputs["Fac"], lines.inputs[0])
            fac = math_node("ADD")
            L(fres.outputs["Facing"], fac.inputs[0])
            L(lines.outputs[0], fac.inputs[1])
        else:
            noise = node("ShaderNodeTexNoise", Scale=6.0, Detail=4.0)
            L(coord.outputs["Object"], noise.inputs["Vector"])
            if noise.inputs.get("W") is not None:
                noise.noise_dimensions = "4D"
                time_driver(noise.inputs["W"], 0.03)
            fac = math_node("MULTIPLY")
            L(fres.outputs["Facing"], fac.inputs[0])
            L(noise.outputs["Fac"], fac.inputs[1])
        clamp = math_node("MINIMUM", None, 1.0)
        L(fac.outputs[0], clamp.inputs[0])
        L(clamp.outputs[0], mix.inputs["Fac"])
        L(transp.outputs[0], mix.inputs[1])
        L(emit.outputs[0], mix.inputs[2])
        L(mix.outputs[0], out.inputs["Surface"])
    elif shader_name == "dissolve":
        base = nt.nodes.new("ShaderNodeBsdfPrincipled")
        vfx_input(base, "Base Color", (0.7, 0.7, 0.72, 1))
        noise = node("ShaderNodeTexNoise", Scale=4.0, Detail=6.0)
        progress = math_node("ADD")  # noise + progress -> alpha cut
        L(noise.outputs["Fac"], progress.inputs[0])
        progress.inputs[1].default_value = 0.0
        if animate:
            progress.inputs[1].keyframe_insert("default_value", frame=bpy.context.scene.frame_start)
            progress.inputs[1].default_value = -1.0
            progress.inputs[1].keyframe_insert("default_value", frame=bpy.context.scene.frame_end)
        alpha = math_node("GREATER_THAN", None, 0.5)
        L(progress.outputs[0], alpha.inputs[0])
        edge = math_node("GREATER_THAN", None, 0.45)
        L(progress.outputs[0], edge.inputs[0])
        burn = math_node("SUBTRACT")
        L(edge.outputs[0], burn.inputs[0])
        L(alpha.outputs[0], burn.inputs[1])
        glow = math_node("MULTIPLY", None, strength * 4)
        L(burn.outputs[0], glow.inputs[0])
        L(glow.outputs[0], base.inputs["Emission Strength"])
        vfx_input(base, ["Emission Color", "Emission"], (1.0, 0.4, 0.05, 1))
        L(alpha.outputs[0], base.inputs["Alpha"])
        L(base.outputs[0], out.inputs["Surface"])
    elif shader_name in ("lava", "energy"):
        noise = node("ShaderNodeTexNoise", Scale=3.0 if shader_name == "lava" else 8.0, Detail=10.0)
        if noise.inputs.get("W") is not None:
            noise.noise_dimensions = "4D"
            time_driver(noise.inputs["W"], 0.02)
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (0.02, 0.0, 0.0, 1) if shader_name == "lava" else (0, 0, 0, 1)
        ramp.color_ramp.elements[1].color = (1.0, 0.35, 0.02, 1) if shader_name == "lava" else color
        ramp.color_ramp.elements[0].position = 0.45
        emit = node("ShaderNodeEmission", Strength=strength)
        L(noise.outputs["Fac"], ramp.inputs["Fac"])
        L(ramp.outputs["Color"], emit.inputs["Color"])
        L(emit.outputs[0], out.inputs["Surface"])
        if shader_name == "energy" and animate:
            fc = emit.inputs["Strength"].driver_add("default_value")
            fc.driver.expression = f"{{strength}}*(1.2+0.8*sin(frame*0.4))"
    elif shader_name in ("wood", "concrete"):
        base = nt.nodes.new("ShaderNodeBsdfPrincipled")
        coord = node("ShaderNodeTexCoord")
        if shader_name == "wood":
            wave = node("ShaderNodeTexWave", Scale=3.0, Distortion=6.0, Detail=4.0)
            try:
                wave.wave_type = "RINGS"
            except Exception:
                pass
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = (0.25, 0.12, 0.05, 1)
            ramp.color_ramp.elements[1].color = (0.55, 0.32, 0.15, 1)
            L(coord.outputs["Object"], wave.inputs["Vector"])
            L(wave.outputs["Fac"], ramp.inputs["Fac"])
            L(ramp.outputs["Color"], base.inputs["Base Color"])
            vfx_input(base, "Roughness", 0.55)
        else:
            noise = node("ShaderNodeTexNoise", Scale=18.0, Detail=12.0)
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = (0.3, 0.3, 0.29, 1)
            ramp.color_ramp.elements[1].color = (0.55, 0.55, 0.53, 1)
            bump = node("ShaderNodeBump", Strength=0.3)
            L(coord.outputs["Object"], noise.inputs["Vector"])
            L(noise.outputs["Fac"], ramp.inputs["Fac"])
            L(noise.outputs["Fac"], bump.inputs["Height"])
            L(ramp.outputs["Color"], base.inputs["Base Color"])
            L(bump.outputs["Normal"], base.inputs["Normal"])
            vfx_input(base, "Roughness", 0.9)
        L(base.outputs[0], out.inputs["Surface"])
    else:
        raise ValueError(f"unknown shader {{shader_name}}")
vfx_assign(obj, mat)
vfx_info(effect="shaders", shader=shader_name, material=mat.name, nodes=len(mat.node_tree.nodes), target=obj.name)
"""


__all__ = [
    "build",
    "DESCRIPTION",
    "PARAMS",
    "PBR",
    "VFX",
]

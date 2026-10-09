"""Hair & fur as strands: particle hair with children, clumping, kink and a
Principled Hair shader (melanin-based colour, like real hair pigment).

Presets set the strand count, length and styling for short fur, long hair
and grass; a vertex-group mask can limit growth to part of the surface.
"""

from __future__ import annotations

from openjarvis.vfx._base import params_with_defaults, py

DESCRIPTION = "Strand hair/fur/grass on an object, with clumping, curls and a physically based hair shader."
PRESETS = {  # count, length, children, clump, kink amplitude, roughness
    "fur": (2000, 0.08, 20, 0.2, 0.0, 0.05),
    "hair": (800, 0.45, 30, 0.6, 0.0, 0.02),
    "curly": (800, 0.3, 30, 0.5, 0.08, 0.02),
    "grass": (3000, 0.18, 8, 0.0, 0.0, 0.15),
}
PARAMS = {
    "preset": ("fur", "fur, hair, curly or grass"),
    "surface": ("sphere", "what grows it: sphere, monkey, plane, cube"),
    "melanin": (0.6, "0 blond .. 1 black"),
    "redness": (0.2, "red pigment (pheomelanin share)"),
    "color": ((0.1, 0.5, 0.1), "colour for grass (ignored for hair)"),
    "density": (1.0, "multiplier on the preset strand count"),
}


def build(**kw) -> str:
    p = params_with_defaults(PARAMS, kw)
    preset = str(p["preset"]).lower()
    count, length, children, clump, kink, rough = PRESETS.get(preset, PRESETS["fur"])
    return f"""
surface = vfx_mesh({py(p["surface"])}, "Hair Surface", location=(0, 0, 1), size=1)
if surface.data.polygons and len(surface.data.polygons) < 200:
    surface.modifiers.new("Sub", "SUBSURF").levels = 2
mod = surface.modifiers.new("Hair", "PARTICLE_SYSTEM")
ps = surface.particle_systems[0].settings
ps.type = "HAIR"
ps.count = int({count} * {p["density"]})
ps.hair_length = {length}
ps.use_advanced_hair = True
ps.child_type = "INTERPOLATED"
ps.child_percent = ps.rendered_child_count = {children}
ps.clump_factor = {clump}
ps.roughness_2 = {rough}
if {kink} > 0:
    ps.kink = "CURL"
    ps.kink_amplitude = {kink}
    ps.kink_frequency = 6
ps.root_radius, ps.tip_radius = 1.0, 0.0
mat = bpy.data.materials.new("Strands")
mat.use_nodes = True
nt = mat.node_tree
out = nt.nodes.get("Material Output")
if {py(preset)} == "grass":
    shader = nt.nodes.get("Principled BSDF")
    vfx_input(shader, "Base Color", (*{py(tuple(p["color"]))}, 1))
else:
    for n in list(nt.nodes):
        if n.bl_idname == "ShaderNodeBsdfPrincipled":
            nt.nodes.remove(n)
    shader = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
    try:
        shader.parametrization = "MELANIN"
    except Exception:
        pass
    vfx_input(shader, "Melanin", {p["melanin"]})
    vfx_input(shader, "Melanin Redness", {p["redness"]})
    vfx_input(shader, "Roughness", 0.3)
nt.links.new(shader.outputs[0], out.inputs["Surface"])
skin = vfx_material("Skin", (0.25, 0.18, 0.14, 1), roughness=0.7)
vfx_assign(surface, skin)
surface.data.materials.append(mat)
ps.material = 2
vfx_info(effect="hair_fur", preset={py(preset)}, strands=ps.count, children=ps.rendered_child_count,
         shader=shader.bl_idname)
"""

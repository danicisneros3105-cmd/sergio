"""Smoke & fire with Mantaflow: gas domain, emitter, a blackbody fire shader.

The domain wraps the emitter with headroom for the plume; vorticity adds
curl, dissolve thins old smoke; noise upres adds detail without raising the
base grid. The volume shader colours flames by temperature (blackbody) and
smoke by density, which is how production fire shaders are built.
"""

from __future__ import annotations

from openjarvis.vfx._base import params_with_defaults, py

DESCRIPTION = "Mantaflow smoke and/or fire from an emitter object, with a blackbody volume shader."
PARAMS = {
    "kind": ("both", "smoke, fire or both"),
    "emitter": ("cube", "shape that burns: cube, sphere, cylinder, monkey"),
    "resolution": (64, "base grid divisions (32 preview, 128+ final)"),
    "vorticity": (0.2, "swirl of the plume (0-1)"),
    "fuel": (1.0, "fuel amount (fire)"),
    "smoke_color": ((0.35, 0.35, 0.37), "smoke RGB"),
    "dissolve": (True, "smoke fades over time"),
    "noise": (False, "high-resolution noise upres (slower bake)"),
    "frames": (48, "frames to simulate"),
    "bake": (False, "bake the cache now (needed for renders)"),
}


def build(**kw) -> str:
    p = params_with_defaults(PARAMS, kw)
    flow_type = {"smoke": "SMOKE", "fire": "FIRE", "both": "BOTH"}.get(
        str(p["kind"]).lower(), "BOTH"
    )
    return f"""
sc = bpy.context.scene
sc.frame_end = sc.frame_start + {p["frames"]} - 1
emitter = vfx_mesh({py(p["emitter"])}, "Emitter", location=(0, 0, 0.5), size=0.5)
fm = emitter.modifiers.new("Fluid", "FLUID")
fm.fluid_type = "FLOW"
fs = fm.flow_settings
fs.flow_type = {py(flow_type)}
fs.flow_behavior = "INFLOW"
fs.flow_source = "MESH"
fs.surface_distance = 0.2
fs.smoke_color = {py(tuple(p["smoke_color"]))}
fs.fuel_amount = {p["fuel"]}
domain = vfx_mesh("cube", "Smoke Domain", location=(0, 0, 3.0), size=1)
domain.scale = (3, 3, 3.5)
dm = domain.modifiers.new("Fluid", "FLUID")
dm.fluid_type = "DOMAIN"
d = dm.domain_settings
d.domain_type = "GAS"
d.resolution_max = {p["resolution"]}
d.vorticity = {p["vorticity"]}
d.use_dissolve_smoke = {p["dissolve"]}
d.dissolve_speed = 25
d.use_noise = {p["noise"]}
d.cache_type = "ALL"
d.cache_directory = bpy.app.tempdir + "sergio_smoke_cache"
d.use_adaptive_domain = True
mat = bpy.data.materials.new("Fire and Smoke")
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputMaterial")
vol = nt.nodes.new("ShaderNodeVolumePrincipled")
vfx_input(vol, "Density", 5.0)
vfx_input(vol, "Color", (*{py(tuple(p["smoke_color"]))}, 1))
vfx_input(vol, "Blackbody Intensity", 1.0 if {py(flow_type)} != "SMOKE" else 0.0)
vfx_input(vol, "Temperature", 1200)
attr = nt.nodes.new("ShaderNodeAttribute")
attr.attribute_name = "flame"
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].position = 0.05
nt.links.new(attr.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], vol.inputs["Blackbody Intensity"])
nt.links.new(vol.outputs[0], out.inputs["Volume"])
vfx_assign(domain, mat)
domain.display_type = "WIRE"
baked = vfx_bake() if {p["bake"]} else []
vfx_info(effect="smoke_fire", flow=fs.flow_type, domain=d.domain_type, resolution=d.resolution_max, baked=baked)
"""

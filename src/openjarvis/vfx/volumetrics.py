"""Volumetrics: clouds, fog, light shafts and a physical sky atmosphere.

* ``clouds`` — a volume box whose density comes from layered noise shaped by
  a height gradient, so it reads as cumulus, not a foggy cube.
* ``fog`` — world volume scattering (depth haze) with anisotropy.
* ``god_rays`` — a spot light through scattering fog behind an occluder.
* ``sky`` — Nishita physical sky (sun elevation, air, dust, ozone).
Effects combine: ``layers`` is a comma list.
"""

from __future__ import annotations

from openjarvis.vfx._base import params_with_defaults

DESCRIPTION = "Clouds, fog, god rays and a physical sky atmosphere."
PARAMS = {
    "layers": ("sky,clouds,fog", "any of: clouds, fog, god_rays, sky"),
    "fog_density": (0.03, "world fog density"),
    "cloud_density": (4.0, "cloud density"),
    "cloud_scale": (1.6, "noise scale of the clouds (bigger = smaller puffs)"),
    "sun_elevation": (12.0, "sun height in degrees (low = golden hour)"),
    "anisotropy": (0.4, "forward scattering (0 even, 0.9 strong shafts)"),
}


def build(**kw) -> str:
    p = params_with_defaults(PARAMS, kw)
    layers = {x.strip().lower() for x in str(p["layers"]).split(",") if x.strip()}
    return f'''
layers = {sorted(layers)!r}
world = vfx_world((0.4, 0.5, 0.7), 1.0)
wt = world.node_tree
wout = next(n for n in wt.nodes if n.bl_idname == "ShaderNodeOutputWorld")
if "sky" in layers:
    sky = wt.nodes.new("ShaderNodeTexSky")
    for kind in ("NISHITA", "MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "PREETHAM"):
        try:
            sky.sky_type = kind
            break
        except Exception:
            continue
    for attr, val in (("sun_elevation", math.radians({p["sun_elevation"]})), ("air_density", 1.0),
                      ("dust_density", 1.5), ("ozone_density", 1.0)):
        if hasattr(sky, attr):
            setattr(sky, attr, val)
    wt.links.new(sky.outputs[0], wt.nodes.get("Background").inputs[0])
if "fog" in layers or "god_rays" in layers:
    scatter = wt.nodes.new("ShaderNodeVolumePrincipled")
    vfx_input(scatter, "Density", {p["fog_density"]})
    vfx_input(scatter, "Anisotropy", {p["anisotropy"]})
    wt.links.new(scatter.outputs[0], wout.inputs["Volume"])
if "clouds" in layers:
    cloud = vfx_mesh("cube", "Clouds", location=(0, 0, 9), size=1)
    cloud.scale = (14, 14, 2.5)
    mat = bpy.data.materials.new("Cloud Volume")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    coords = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    vfx_input(noise, "Scale", {p["cloud_scale"]})
    vfx_input(noise, "Detail", 8.0)
    vfx_input(noise, "Roughness", 0.6)
    grad = nt.nodes.new("ShaderNodeSeparateXYZ")
    shape = nt.nodes.new("ShaderNodeFloatCurve") if hasattr(bpy.types, "ShaderNodeFloatCurve") else None
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.48
    ramp.color_ramp.elements[1].position = 0.62
    mult = nt.nodes.new("ShaderNodeMath")
    mult.operation = "MULTIPLY"
    height = nt.nodes.new("ShaderNodeMath")
    height.operation = "PINGPONG" if "PINGPONG" in [e.identifier for e in height.bl_rna.properties["operation"].enum_items] else "SINE"
    height.inputs[1].default_value = 1.0
    dens = nt.nodes.new("ShaderNodeMath")
    dens.operation = "MULTIPLY"
    dens.inputs[1].default_value = {p["cloud_density"]}
    nt.links.new(coords.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(coords.outputs["Generated"], grad.inputs[0])
    nt.links.new(grad.outputs["Z"], height.inputs[0])
    nt.links.new(ramp.outputs["Color"], mult.inputs[0])
    nt.links.new(height.outputs[0], mult.inputs[1])
    nt.links.new(mult.outputs[0], dens.inputs[0])
    nt.links.new(dens.outputs[0], vol.inputs["Density"])
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    vfx_assign(cloud, mat)
    if shape is not None:
        nt.nodes.remove(shape)
if "god_rays" in layers:
    blocker = vfx_mesh("plane", "Window Blinds", location=(0, 2, 3), size=3)
    blocker.rotation_euler = (math.radians(90), 0, 0)
    bm = bmesh.new()
    bm.from_mesh(blocker.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=7, use_grid_fill=True)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for i, f in enumerate(bm.faces) if (i // 8) % 2 == 0], context="FACES")
    bm.to_mesh(blocker.data)
    bm.free()
    spot = vfx_light("SPOT", 4000, (0, 6, 4), (math.radians(-80), 0, math.radians(180)), (1, 0.85, 0.6))
    spot.data.spot_size = math.radians(50)
vfx_info(effect="volumetrics", layers=layers, world_volume=bool(wout.inputs["Volume"].links))
'''

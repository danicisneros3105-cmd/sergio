"""Liquids with Mantaflow FLIP: pour, splash into a pool, or a dam break.

* ``pour``: a stream from an inflow into an open container (obstacle).
* ``splash``: a ball dropped into a pool of water (initial liquid volume).
* ``dam``: a block of water released in a tank.
The domain meshes the particles into a smooth surface (mesh upres), with
splash/foam/bubble secondary particles optional, and a water shader.
"""

from __future__ import annotations

from openjarvis.vfx._base import params_with_defaults

DESCRIPTION = (
    "FLIP liquid simulation (pour, splash or dam break) with a meshed water surface."
)
PARAMS = {
    "scenario": ("splash", "pour, splash or dam"),
    "resolution": (64, "domain grid divisions"),
    "viscosity": (0.0, "0 = water; higher = honey-like (base value x 10^-exponent)"),
    "spray": (False, "secondary spray/foam/bubble particles"),
    "frames": (60, "frames to simulate"),
    "bake": (False, "bake the cache now"),
}


def build(**kw) -> str:
    p = params_with_defaults(PARAMS, kw)
    scenario = str(p["scenario"]).lower()
    return f"""
sc = bpy.context.scene
sc.frame_end = sc.frame_start + {p["frames"]} - 1
domain = vfx_mesh("cube", "Liquid Domain", location=(0, 0, 1.5), size=1)
domain.scale = (2, 2, 1.5)


def flow(obj, behavior, velocity=(0, 0, 0)):
    m = obj.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "FLOW"
    f = m.flow_settings
    f.flow_type = "LIQUID"
    f.flow_behavior = behavior
    if any(velocity):
        f.use_initial_velocity = True
        f.velocity_coord = velocity
    return obj

def effector(obj):
    m = obj.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "EFFECTOR"
    m.effector_settings.effector_type = "COLLISION"
    return obj

scenario = {scenario!r}
if scenario == "pour":
    spout = vfx_mesh("cylinder", "Spout", location=(-1.2, 0, 2.4), size=0.15)
    spout.scale.z = 0.3
    flow(spout, "INFLOW", velocity=(2.5, 0, 0))
    cup = vfx_mesh("cylinder", "Container", location=(0.6, 0, 0.6), size=0.7)
    cup.scale.z = 0.6
    sol = cup.modifiers.new("Wall", "SOLIDIFY"); sol.thickness = 0.06
    effector(cup)
elif scenario == "dam":
    water = vfx_mesh("cube", "Water Block", location=(-1.3, 0, 0.8), size=1)
    water.scale = (0.6, 1.9, 0.8)
    flow(water, "GEOMETRY")
    water.hide_render = True
else:
    pool = vfx_mesh("cube", "Pool Water", location=(0, 0, 0.35), size=1)
    pool.scale = (1.95, 1.95, 0.35)
    flow(pool, "GEOMETRY")
    pool.hide_render = True
    ball = vfx_mesh("sphere", "Ball", location=(0, 0, 2.6), size=0.35)
    effector(ball)
    ball.keyframe_insert("location", frame=1)
    ball.location.z = 0.2
    ball.keyframe_insert("location", frame=14)
dm = domain.modifiers.new("Fluid", "FLUID")  # added last: evaluation starts the solver
dm.fluid_type = "DOMAIN"
d = dm.domain_settings
d.domain_type = "LIQUID"
d.resolution_max = {p["resolution"]}
d.use_mesh = True
d.cache_type = "ALL"
d.cache_directory = bpy.app.tempdir + "sergio_liquid_cache"
if {p["viscosity"]} > 0:
    d.use_viscosity = True
    d.viscosity_value = {p["viscosity"]}
if {p["spray"]}:
    d.use_spray_particles = True
    d.use_foam_particles = True
    d.use_bubble_particles = True
water_mat = vfx_material("Water", (0.8, 0.9, 1.0, 1), roughness=0.02, transmission=1.0, ior=1.333)
vfx_assign(domain, water_mat)
baked = vfx_bake() if {p["bake"]} else []
vfx_info(effect="fluid", scenario=scenario, domain=d.domain_type, baked=baked)
"""

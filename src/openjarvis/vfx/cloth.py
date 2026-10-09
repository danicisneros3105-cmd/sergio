"""Cloth like a garment tool: real fabric presets, pinning, sewing, collisions.

Scenarios:
* ``drape`` — a tablecloth falls over an object (collision, self-collision).
* ``flag`` — a pinned flag in wind (vertex group pin + wind force field).
* ``garment`` — two panels sewn together around a body (sewing springs on
  loose edges pull the panels shut, then shrink to fit), the way
  Marvelous Designer stitches patterns.
Fabric presets use Blender's own cloth preset values (mass, stiffness,
damping) for silk, cotton, denim, leather and rubber.
"""

from __future__ import annotations

from openjarvis.vfx._base import params_with_defaults, py

DESCRIPTION = (
    "Cloth simulation (drape, flag in wind, sewn garment) with real fabric presets."
)
FABRICS = {  # mass kg/m2, tension, compression, shear, bending, air damping
    "silk": (0.15, 5, 5, 5, 0.05, 1),
    "cotton": (0.3, 15, 15, 15, 0.5, 1),
    "denim": (1.0, 40, 40, 40, 10, 1),
    "leather": (0.4, 80, 80, 80, 150, 1),
    "rubber": (3.0, 15, 15, 15, 25, 1),
}
PARAMS = {
    "scenario": ("drape", "drape, flag or garment"),
    "fabric": ("cotton", "silk, cotton, denim, leather or rubber"),
    "subdivisions": (24, "cloth resolution (cuts per side)"),
    "wind": (6.0, "wind strength (flag)"),
    "frames": (60, "frames to simulate"),
    "bake": (False, "step the simulation now"),
}


def build(**kw) -> str:
    p = params_with_defaults(PARAMS, kw)
    fabric = FABRICS.get(str(p["fabric"]).lower(), FABRICS["cotton"])
    return f"""
sc = bpy.context.scene
sc.frame_end = sc.frame_start + {p["frames"]} - 1
mass, tension, compression, shear, bending, air = {py(fabric)}
scenario = {py(str(p["scenario"]).lower())}

def make_cloth(obj, pin_group=None, sewing=False):
    m = obj.modifiers.new("Cloth", "CLOTH")
    s = m.settings
    s.quality = 8
    s.mass = mass
    s.tension_stiffness, s.compression_stiffness, s.shear_stiffness = tension, compression, shear
    s.bending_stiffness = bending
    s.air_damping = air
    if pin_group:
        s.vertex_group_mass = pin_group
    if sewing:
        s.use_sewing_springs = True
        s.sewing_force_max = 8
        s.shrink_min = 0.1
    c = m.collision_settings
    c.use_self_collision = True
    c.distance_min = 0.008
    m.point_cache.frame_end = sc.frame_end
    return m

def collider(obj):
    obj.modifiers.new("Collision", "COLLISION")
    obj.collision.thickness_outer = 0.01
    return obj

def subdivided_plane(name, size, location, cuts):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=cuts, y_subdivisions=cuts, size=size, location=location)
    ob = bpy.context.active_object
    ob.name = name
    return ob

fabric_mat = vfx_material("Fabric", (0.55, 0.12, 0.12, 1), roughness=0.85, sheen=0.6)
cloth_objects = []
if scenario == "flag":
    pole = vfx_mesh("cylinder", "Pole", location=(-1.05, 0, 1.5), size=0.04)
    pole.scale.z = 1.6
    flag = subdivided_plane("Flag", 2, (0, 0, 2.4), {p["subdivisions"]})
    flag.rotation_euler = (math.radians(90), 0, 0)
    grp = flag.vertex_groups.new(name="pin")
    grp.add([v.index for v in flag.data.vertices if v.co.x < -0.95], 1.0, "REPLACE")
    make_cloth(flag, pin_group="pin")
    bpy.ops.object.effector_add(type="WIND", location=(-3, 0, 2.4), rotation=(0, math.radians(90), 0))
    bpy.context.active_object.field.strength = {p["wind"]}
    bpy.ops.object.effector_add(type="TURBULENCE", location=(0, 0, 2.4))
    bpy.context.active_object.field.strength = {p["wind"]} * 0.4
    cloth_objects.append(flag)
elif scenario == "garment":
    body = collider(vfx_mesh("cylinder", "Body", location=(0, 0, 1.2), size=0.35))
    body.scale.z = 1.0
    front = subdivided_plane("Panel Front", 1.1, (0, -0.55, 1.2), {p["subdivisions"]})
    front.rotation_euler = (math.radians(90), 0, 0)
    back = subdivided_plane("Panel Back", 1.1, (0, 0.55, 1.2), {p["subdivisions"]})
    back.rotation_euler = (math.radians(90), 0, 0)
    for o in (front, back):
        o.select_set(True)
    bpy.context.view_layer.objects.active = front
    bpy.ops.object.join()
    garment = bpy.context.active_object
    garment.name = "Garment"
    bm = bmesh.new()
    bm.from_mesh(garment.data)
    bm.verts.ensure_lookup_table()
    side = [v for v in bm.verts if abs(abs(v.co.x) - 0.55) < 1e-4]
    seams = 0
    for v in side:
        mate = min((w for w in side if w is not v and abs(w.co.z - v.co.z) < 1e-4 and w.co.x * v.co.x > 0
                    and (w.co.y * v.co.y) <= 0), key=lambda w: (w.co - v.co).length, default=None)
        if mate and not any(mate in e.verts for e in v.link_edges):
            bm.edges.new((v, mate))  # a loose edge = a sewing spring
            seams += 1
    bm.to_mesh(garment.data)
    bm.free()
    gm = make_cloth(garment, sewing=True)
    gm.settings.effector_weights.gravity = 0.0  # like a pattern tool: seams close first, no falling
    gm.settings.shrink_min = 0.15
    vfx_info(seams=seams)
    cloth_objects.append(garment)
else:
    table = collider(vfx_mesh("cylinder", "Table", location=(0, 0, 0.9), size=0.8))
    table.scale.z = 0.05
    cloth = subdivided_plane("Tablecloth", 2.4, (0, 0, 1.6), {p["subdivisions"]})
    make_cloth(cloth)
    cloth_objects.append(cloth)
for ob in cloth_objects:
    vfx_assign(ob, fabric_mat)
    ob.modifiers.new("Smooth", "SUBSURF").levels = 1
collider(vfx_ground())
if {p["bake"]}:
    vfx_bake()
    deps = bpy.context.evaluated_depsgraph_get()
    ev = cloth_objects[0].evaluated_get(deps)
    zs = [(ev.matrix_world @ v.co).z for v in ev.data.vertices]
    vfx_info(lowest_z=round(min(zs), 3), highest_z=round(max(zs), 3))
vfx_info(effect="cloth", scenario=scenario, fabric={py(str(p["fabric"]))}, cloth_objects=len(cloth_objects))
"""


__all__ = [
    "build",
    "DESCRIPTION",
    "FABRICS",
    "PARAMS",
]

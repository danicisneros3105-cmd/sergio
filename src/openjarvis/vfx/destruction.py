"""Destruction: Voronoi-style fracture + rigid body dynamics.

The object is broken with bmesh: random cut planes through seed points
(``bisect_plane`` + ``contextual_create`` to cap the cut) give convex
shards, like a Voronoi cell fracture, without needing the Cell Fracture
add-on. Shards become active rigid bodies (convex hulls, mass from volume),
the ground is passive, and a projectile (or a force field) hits them.
Optional ``glue`` keeps shards together until impact (rigid body
constraints that break above a threshold).
"""

from __future__ import annotations

from openjarvis.vfx._base import params_with_defaults, py

DESCRIPTION = "Fracture an object into shards and smash it with rigid bodies (projectile or explosion)."
PARAMS = {
    "target": ("cube", "object to break: cube, sphere, cylinder, monkey"),
    "pieces": (24, "number of shards"),
    "impact": ("projectile", "projectile, explosion or drop"),
    "glue": (True, "shards stay glued until the hit (breakable constraints)"),
    "strength": (40.0, "glue strength / explosion force"),
    "seed": (7, "random seed (repeatable shapes)"),
    "frames": (72, "frames to simulate"),
    "bake": (False, "step the simulation now"),
}


def build(**kw) -> str:
    p = params_with_defaults(PARAMS, kw)
    return f'''
sc = bpy.context.scene
sc.frame_end = sc.frame_start + {p["frames"]} - 1
random.seed({p["seed"]})
ground = vfx_ground()
src = vfx_mesh({py(p["target"])}, "Target", location=(0, 0, 1.0), size=1)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
src_mesh = src.data.copy()
mat = vfx_material("Shard", (0.75, 0.72, 0.68, 1), roughness=0.6)
inner = vfx_material("Shard Inside", (0.55, 0.5, 0.45, 1), roughness=0.9)

def shard_cells(n):
    # Seed points inside the bounding box; each cell = points closer to its seed (Voronoi).
    bb = [Vector(c) for c in src.bound_box]
    lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    return [Vector((random.uniform(lo.x, hi.x), random.uniform(lo.y, hi.y), random.uniform(lo.z, hi.z)))
            for _ in range(n)]

seeds = shard_cells({p["pieces"]})
shards = []
for i, seed in enumerate(seeds):
    bm = bmesh.new()
    bm.from_mesh(src_mesh)
    for j, other in enumerate(seeds):
        if i == j:
            continue
        mid = (seed + other) / 2
        normal = (other - seed).normalized()
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=mid, plane_no=normal, clear_outer=True)
        cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if cut_edges:
            try:
                bmesh.ops.contextual_create(bm, geom=cut_edges)
            except Exception:
                pass
        if not bm.verts:
            break
    if len(bm.verts) < 4:
        bm.free()
        continue
    me = bpy.data.meshes.new(f"Shard_{{i:03d}}")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(me.name, me)
    sc.collection.objects.link(ob)
    ob.location = src.location
    ob.data.materials.append(mat)
    ob.data.materials.append(inner)
    shards.append(ob)
bpy.data.objects.remove(src)

bpy.ops.rigidbody.world_add()
sc.rigidbody_world.point_cache.frame_end = sc.frame_end
def rigid(ob, kind, shape="CONVEX_HULL", mass=1.0):
    sc.rigidbody_world.collection = sc.rigidbody_world.collection or bpy.data.collections.new("RigidBodyWorld")
    if ob.name not in sc.rigidbody_world.collection.objects:
        sc.rigidbody_world.collection.objects.link(ob)
    ob.rigid_body.type = kind
    ob.rigid_body.collision_shape = shape
    ob.rigid_body.mass = mass
    ob.rigid_body.friction = 0.6
    return ob

for ob in shards:
    rigid(ob, "ACTIVE", mass=max(0.05, ob.dimensions.x * ob.dimensions.y * ob.dimensions.z * 2.4))
rigid(ground, "PASSIVE", shape="BOX")

glued = 0
if {p["glue"]}:
    for a in shards:
        near = sorted(shards, key=lambda b: (b.matrix_world @ Vector(b.bound_box[0]) - a.location).length)[1:4]
        for b in near:
            if a.name < b.name:
                empty = bpy.data.objects.new(f"Glue_{{a.name}}_{{b.name}}", None)
                sc.collection.objects.link(empty)
                empty.location = (a.location + b.location) / 2
                if sc.rigidbody_world.constraints is None:
                    sc.rigidbody_world.constraints = bpy.data.collections.new("RigidBodyConstraints")
                sc.rigidbody_world.constraints.objects.link(empty)
                bpy.context.view_layer.objects.active = empty
                empty.select_set(True)
                bpy.ops.rigidbody.constraint_add()
                c = empty.rigid_body_constraint
                c.type = "FIXED"
                c.object1, c.object2 = a, b
                c.use_breaking = True
                c.breaking_threshold = {p["strength"]}
                glued += 1

impact = {py(str(p["impact"]).lower())}
if impact == "projectile":
    ball = vfx_mesh("sphere", "Projectile", location=(-6, 0, 1.0), size=0.25)
    rigid(ball, "ACTIVE", shape="SPHERE", mass=25)
    ball.rigid_body.kinematic = True
    ball.keyframe_insert("location", frame=1)
    ball.location.x = -0.6
    ball.keyframe_insert("location", frame=10)
    ball.rigid_body.keyframe_insert("kinematic", frame=10)
    ball.rigid_body.kinematic = False
    ball.rigid_body.keyframe_insert("kinematic", frame=11)
elif impact == "explosion":
    bpy.ops.object.effector_add(type="FORCE", location=(0, 0, 0.6))
    field = bpy.context.active_object
    field.field.strength = {p["strength"]} * 25
    field.field.falloff_type = "SPHERE"
    field.field.use_max_distance = True
    field.field.distance_max = 3
else:
    for ob in shards:
        ob.location.z += 3

if {p["bake"]}:
    vfx_bake()
moved = sum(1 for ob in shards if (ob.matrix_world.translation - Vector((0, 0, 1.0))).length > 0.6)
vfx_info(effect="destruction", shards=len(shards), glue_constraints=glued, impact=impact, moved=moved)
'''

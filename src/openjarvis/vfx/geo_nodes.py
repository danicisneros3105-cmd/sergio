"""Procedural modelling with Geometry Nodes, built node by node from Python.

* ``scatter`` — rocks/trees: points distributed on a surface (Poisson disk),
  random rotation and scale, instanced and realised.
* ``city`` — a grid of blocks extruded to random heights (skyline).
* ``along_curve`` — objects repeated along a curve (fence, chain, lights).
The node groups use the 4.x/5.x interface API (``tree.interface``) and are
fully editable afterwards in Blender's node editor.
"""

from __future__ import annotations

from openjarvis.vfx._base import params_with_defaults, py

DESCRIPTION = "Geometry Nodes generators: scatter instances, procedural city, objects along a curve."
PARAMS = {
    "kind": ("scatter", "scatter, city or along_curve"),
    "count": (200, "instances (scatter/curve) or blocks per side (city: square root)"),
    "instance": ("ico", "shape to repeat: ico, cube, cone, cylinder, monkey"),
    "scale_min": (0.2, "smallest random scale"),
    "scale_max": (0.6, "largest random scale"),
    "max_height": (6.0, "tallest building (city)"),
    "seed": (3, "random seed"),
}


def build(**kw) -> str:
    p = params_with_defaults(PARAMS, kw)
    return f"""
kind = {py(str(p["kind"]).lower())}
seed = {p["seed"]}

def gn_tree(name):
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gin = tree.nodes.new("NodeGroupInput")
    gout = tree.nodes.new("NodeGroupOutput")
    return tree, gin, gout

def put(node, name, value):
    vfx_set(node, name, value)
    return node

def attach(obj, tree):
    mod = obj.modifiers.new(tree.name, "NODES")
    mod.node_group = tree
    return mod

proto = vfx_mesh({py(p["instance"])}, "Instance Source", location=(0, 0, -50), size=0.5)
proto.hide_render = True
if kind == "city":
    ground = vfx_mesh("grid", "City Ground", size=40, x_subdivisions=2, y_subdivisions=2)
    tree, gin, gout = gn_tree("Sergio City")
    N = tree.nodes.new
    side = max(2, int({p["count"]} ** 0.5))
    grid = N("GeometryNodeMeshGrid")
    put(grid, "Size X", 40.0); put(grid, "Size Y", 40.0)
    put(grid, "Vertices X", side); put(grid, "Vertices Y", side)
    pts = N("GeometryNodeMeshToPoints")
    cube = N("GeometryNodeMeshCube")
    s = 40.0 / side * 0.7
    put(cube, "Size", (s, s, 1.0))
    inst = N("GeometryNodeInstanceOnPoints")
    rnd = N("FunctionNodeRandomValue")
    rnd.data_type = "FLOAT_VECTOR"
    put(rnd, "Min", (1.0, 1.0, 1.0)); put(rnd, "Max", (1.0, 1.0, {p["max_height"]}))
    put(rnd, "Seed", seed)
    tree.links.new(grid.outputs["Mesh"], pts.inputs["Mesh"])
    tree.links.new(pts.outputs["Points"], inst.inputs["Points"])
    tree.links.new(cube.outputs["Mesh"], inst.inputs["Instance"])
    tree.links.new(rnd.outputs["Value"], inst.inputs["Scale"])
    real = N("GeometryNodeRealizeInstances")
    tree.links.new(inst.outputs["Instances"], real.inputs["Geometry"])
    join = N("GeometryNodeJoinGeometry")
    tree.links.new(real.outputs["Geometry"], join.inputs["Geometry"])
    tree.links.new(gin.outputs["Geometry"], join.inputs["Geometry"])
    tree.links.new(join.outputs["Geometry"], gout.inputs["Geometry"])
    target = ground
elif kind == "along_curve":
    bpy.ops.curve.primitive_bezier_circle_add(radius=5, location=(0, 0, 0))
    curve = bpy.context.active_object
    curve.name = "Path"
    tree, gin, gout = gn_tree("Sergio Along Curve")
    N = tree.nodes.new
    resample = N("GeometryNodeResampleCurve")
    put(resample, "Count", {p["count"]})
    pts = N("GeometryNodeCurveToPoints")
    try:
        pts.mode = "EVALUATED"
    except Exception:
        pass
    objinfo = N("GeometryNodeObjectInfo")
    objinfo.inputs["Object"].default_value = proto
    inst = N("GeometryNodeInstanceOnPoints")
    tree.links.new(gin.outputs["Geometry"], resample.inputs["Curve"])
    tree.links.new(resample.outputs["Curve"], pts.inputs["Curve"])
    tree.links.new(pts.outputs["Points"], inst.inputs["Points"])
    tree.links.new(pts.outputs["Rotation"], inst.inputs["Rotation"])
    tree.links.new(objinfo.outputs["Geometry"], inst.inputs["Instance"])
    real = N("GeometryNodeRealizeInstances")
    tree.links.new(inst.outputs["Instances"], real.inputs["Geometry"])
    tree.links.new(real.outputs["Geometry"], gout.inputs["Geometry"])
    target = curve
else:
    ground = vfx_mesh("grid", "Terrain", size=20, x_subdivisions=40, y_subdivisions=40)
    disp = ground.modifiers.new("Hills", "DISPLACE")
    tex = bpy.data.textures.new("Hills", "CLOUDS")
    tex.noise_scale = 3.0
    disp.texture, disp.strength = tex, 1.2
    tree, gin, gout = gn_tree("Sergio Scatter")
    N = tree.nodes.new
    dist = N("GeometryNodeDistributePointsOnFaces")
    try:
        dist.distribute_method = "POISSON"
    except Exception:
        pass
    put(dist, "Density Max", {p["count"]} / 400.0)
    put(dist, "Density", {p["count"]} / 400.0)
    put(dist, "Distance Min", 0.3)
    put(dist, "Seed", seed)
    objinfo = N("GeometryNodeObjectInfo")
    objinfo.inputs["Object"].default_value = proto
    inst = N("GeometryNodeInstanceOnPoints")
    rot = N("FunctionNodeRandomValue"); rot.data_type = "FLOAT_VECTOR"
    put(rot, "Max", (0.3, 0.3, 6.283)); put(rot, "Seed", seed + 1)
    scl = N("FunctionNodeRandomValue"); scl.data_type = "FLOAT"
    put(scl, "Min", {p["scale_min"]}); put(scl, "Max", {p["scale_max"]}); put(scl, "Seed", seed + 2)
    tree.links.new(gin.outputs["Geometry"], dist.inputs["Mesh"])
    tree.links.new(dist.outputs["Points"], inst.inputs["Points"])
    tree.links.new(objinfo.outputs["Geometry"], inst.inputs["Instance"])
    tree.links.new(rot.outputs["Value"], inst.inputs["Rotation"])
    tree.links.new(scl.outputs["Value"], inst.inputs["Scale"])
    real = N("GeometryNodeRealizeInstances")
    tree.links.new(inst.outputs["Instances"], real.inputs["Geometry"])
    join = N("GeometryNodeJoinGeometry")
    tree.links.new(real.outputs["Geometry"], join.inputs["Geometry"])
    tree.links.new(gin.outputs["Geometry"], join.inputs["Geometry"])
    tree.links.new(join.outputs["Geometry"], gout.inputs["Geometry"])
    target = ground
attach(target, tree)
deps = bpy.context.evaluated_depsgraph_get()
ev = target.evaluated_get(deps)
mesh = ev.to_mesh()
verts = len(mesh.vertices)
ev.to_mesh_clear()
vfx_info(effect="geo_nodes", kind=kind, tree=tree.name, nodes=len(tree.nodes), evaluated_vertices=verts)
"""


__all__ = [
    "build",
    "DESCRIPTION",
    "PARAMS",
]

import math  # noqa: I001 — bpy must come before bmesh (bmesh only exists once bpy is loaded)

import bpy
import bmesh

bpy.ops.wm.read_factory_settings(use_empty=True)

SERGIO_LAYOUT = [
    {"part": "Plato", "center_cm": [0, 0, 0.6], "size_cm": [15, 15, 1.2]},
    {"part": "Cuerpo", "center_cm": [0, 0, 5.7], "size_cm": [8.4, 8.4, 9]},
    {"part": "Asa", "center_cm": [5.6, 0, 6.2], "size_cm": [3.6, 1.2, 5.4]},
]
CM = 0.01


def material(name, color, rough=0.25):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    try:
        bsdf.inputs["Coat Weight"].default_value = 0.6  # glazed ceramic
    except Exception:
        pass
    return mat


CERAMIC = material("Ceramica", (0.92, 0.9, 0.86))


def lathe(name, profile_cm, z0_cm, mat, steps=64):
    """A round object from its half profile (radius, height) spun around z."""
    bm = bmesh.new()
    verts = [bm.verts.new((r * CM, 0, (z + z0_cm) * CM)) for r, z in profile_cm]
    edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
    bmesh.ops.spin(bm, geom=verts + edges, axis=(0, 0, 1), cent=(0, 0, 0), angle=math.tau, steps=steps)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.polygons.foreach_set("use_smooth", [True] * len(obj.data.polygons))
    obj.data.materials.append(mat)
    return obj


def plato():
    lathe("Plato", [(0, 0), (5.5, 0), (7.5, 0.9), (7.5, 1.2), (7.2, 1.2), (5.4, 0.35), (0, 0.35)], 0, CERAMIC)


def cuerpo():
    # outer wall up, lip, inner wall down to a 0.6 cm floor: a closed shell
    lathe("Cuerpo", [(0, 0), (3.2, 0), (3.9, 1.5), (4.2, 9.0), (3.9, 9.0), (3.6, 1.6), (3.0, 0.6), (0, 0.6)],
          1.2, CERAMIC)


def asa():
    curve = bpy.data.curves.new("Asa", "CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(2)
    for point, (x, z) in zip(spline.bezier_points, ((4.0, 8.4), (7.0, 6.2), (4.0, 3.6))):
        point.co = (x * CM, 0, z * CM)
        point.handle_left_type = point.handle_right_type = "AUTO"
    curve.bevel_depth = 0.55 * CM
    curve.bevel_resolution = 4
    obj = bpy.data.objects.new("Asa", curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    bm = bmesh.new()  # close the tube's two open ends: a solid handle
    bm.from_mesh(obj.data)
    bmesh.ops.holes_fill(bm, edges=bm.edges, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.materials.append(CERAMIC)


plato()
cuerpo()
asa()

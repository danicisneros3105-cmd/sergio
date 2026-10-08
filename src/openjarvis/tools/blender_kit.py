"""Sergio's modelling kit: tested Blender helpers every model script can use.

"Blender only makes cubes": Gemini's scripts started from primitive cubes and
then called operators, bmesh or socket names that differ between Blender
versions. When one of those calls failed the step was skipped and the plain
cube stayed. The kit gives the model a small set of functions that build the
real shapes directly with the data API (no operators, no context), checked in
Blender 3.6 to 5.x:

* ``kit_lathe``   round things from a profile (cups, bottles, lampshades, wheels)
* ``kit_extrude`` flat outlines made solid (phone bodies, logos, brackets)
* ``kit_tube``    bent tubes along a path (handles, cables, frames, arms)
* ``kit_box`` / ``kit_cylinder`` / ``kit_sphere`` with bevels and real sizes
* ``kit_material`` a Principled material whatever the Blender version
* ``kit_parent``, ``kit_mirror_x``, ``kit_array_circle``, ``kit_cut``, ``kit_text``

The source below runs inside Blender before the model script (same
namespace), so the script just calls the functions.
"""

from __future__ import annotations

KIT = r'''
import bpy as _kb, bmesh as _kbm, math as _km
from mathutils import Matrix as _KMat, Vector as _KVec, Euler as _KEul


def _k_rot(rot):
    return _KEul(tuple(_km.radians(a) for a in (rot or (0, 0, 0))), "XYZ")


def _k_link(obj):
    coll = _kb.context.scene.collection
    if obj.name not in coll.objects:
        coll.objects.link(obj)
    return obj


def _k_object(name, bm, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, smooth=False):
    bmesh_ops = _kbm.ops
    bmesh_ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh_ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = _kb.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = _kb.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler = _k_rot(rot)
    _k_link(obj)
    if mat is not None:
        mesh.materials.append(mat)
    if smooth:
        kit_smooth(obj)
    return obj


def _k_set(node, names, value):
    for n in names:
        sock = node.inputs.get(n)
        if sock is not None:
            try:
                sock.default_value = value
                return True
            except Exception:
                pass
    return False


def kit_material(name, color=(0.8, 0.8, 0.8), metallic=0.0, roughness=0.5, transmission=0.0,
                 emission=None, strength=1.0, alpha=1.0, ior=1.45, coat=0.0):
    """A Principled BSDF material (any Blender version). color is RGB 0..1."""
    mat = _kb.data.materials.get(name) or _kb.data.materials.new(name)
    rgba = (*tuple(color)[:3], 1.0)
    mat.diffuse_color = rgba
    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            _k_set(bsdf, ["Base Color"], rgba)
            _k_set(bsdf, ["Metallic"], float(metallic))
            _k_set(bsdf, ["Roughness"], float(roughness))
            _k_set(bsdf, ["IOR"], float(ior))
            if transmission:
                _k_set(bsdf, ["Transmission Weight", "Transmission"], float(transmission))
            if coat:
                _k_set(bsdf, ["Coat Weight", "Clearcoat"], float(coat))
            if emission is not None:
                _k_set(bsdf, ["Emission Color", "Emission"], (*tuple(emission)[:3], 1.0))
                _k_set(bsdf, ["Emission Strength"], float(strength))
            if alpha < 1.0:
                _k_set(bsdf, ["Alpha"], float(alpha))
    except Exception as exc:
        print("SERGIO_KIT material %s: %s" % (name, exc))
    return mat


def kit_smooth(obj):
    """Shade smooth (curved parts)."""
    for p in obj.data.polygons:
        p.use_smooth = True
    try:
        obj.data.use_auto_smooth = True  # Blender < 4.1
        obj.data.auto_smooth_angle = _km.radians(35)
    except Exception:
        pass
    return obj


def kit_bevel(obj, width=0.002, segments=3):
    """Rounded edges that catch the light (a modifier, nothing applied)."""
    if width > 0:
        mod = obj.modifiers.new("Bisel", "BEVEL")
        mod.width = width
        mod.segments = segments
        try:
            mod.limit_method = "ANGLE"
        except Exception:
            pass
        try:
            mod.harden_normals = True
        except Exception:
            pass
    return obj


def kit_subsurf(obj, levels=2):
    mod = obj.modifiers.new("Suave", "SUBSURF")
    mod.levels = max(0, min(levels, 3))
    mod.render_levels = max(0, min(levels + 1, 4))
    return obj


def kit_box(name, size, loc=(0, 0, 0), rot=(0, 0, 0), bevel=0.0, mat=None):
    """A box of size (x, y, z) metres centred on loc; bevel = edge radius in metres."""
    bm = _kbm.new()
    _kbm.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = _KVec((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    obj = _k_object(name, bm, loc, rot, mat)
    if bevel:
        kit_bevel(obj, min(bevel, min(size) * 0.49), 4)
    return obj


def kit_cylinder(name, radius, depth, loc=(0, 0, 0), rot=(0, 0, 0), top_radius=None, verts=48,
                 bevel=0.0, mat=None):
    """A cylinder along z (a cone or frustum with top_radius), centred on loc."""
    bm = _kbm.new()
    top = radius if top_radius is None else top_radius
    try:
        _kbm.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=radius,
                             radius2=top, depth=depth)
    except TypeError:  # Blender < 3.0
        _kbm.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, diameter1=radius,
                             diameter2=top, depth=depth)
    obj = _k_object(name, bm, loc, rot, mat, smooth=True)
    if bevel:
        kit_bevel(obj, min(bevel, depth * 0.49, radius * 0.49), 3)
    return obj


def kit_sphere(name, radius, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0), segments=48, mat=None):
    """A UV sphere (an ellipsoid with scale)."""
    bm = _kbm.new()
    try:
        _kbm.ops.create_uvsphere(bm, u_segments=segments, v_segments=max(8, segments // 2), radius=radius)
    except TypeError:
        _kbm.ops.create_uvsphere(bm, u_segments=segments, v_segments=max(8, segments // 2), diameter=radius)
    for v in bm.verts:
        v.co = _KVec((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
    return _k_object(name, bm, loc, rot, mat, smooth=True)


def _k_soften(pts, steps=4):
    """Catmull-Rom through the profile points: a few points give a smooth
    curve instead of facets (end points and points on the axis stay put)."""
    if len(pts) < 3 or steps < 2:
        return pts
    out = []
    n = len(pts)
    for i in range(n - 1):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n - 1)]
        out.append(p1)
        if p1[0] < 1e-6 or p2[0] < 1e-6:
            continue  # a segment touching the axis stays straight (flat bottoms and tops)
        for k in range(1, steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            r = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            z = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((max(r, 1e-5), z))
    out.append(pts[-1])
    return out


def kit_lathe(name, profile, loc=(0, 0, 0), rot=(0, 0, 0), segments=64, mat=None, smooth=True, sharp=False):
    """Turn a profile [(radius, z), ...] (metres, bottom to top) around the z
    axis: cups, bottles, vases, lampshades, lenses, wheels. A point with
    radius 0 closes the shape at the axis. For a hollow cup go up the
    outside and back down the inside: [(0,0), (0.04,0), (0.045,0.1),
    (0.041,0.1), (0.036,0.006), (0,0.006)]. The profile is rounded through
    its points (sharp=True keeps straight segments)."""
    pts = [(max(float(r), 0.0), float(z)) for r, z in profile]
    if len(pts) < 2:
        raise ValueError("kit_lathe needs at least two profile points")
    if not sharp:
        pts = _k_soften(pts)
    bm = _kbm.new()
    rings = []
    for r, z in pts:
        if r < 1e-6:
            rings.append([bm.verts.new((0.0, 0.0, z))])
        else:
            rings.append([bm.verts.new((r * _km.cos(2 * _km.pi * k / segments),
                                        r * _km.sin(2 * _km.pi * k / segments), z))
                          for k in range(segments)])
    for lo, hi in zip(rings, rings[1:]):
        for k in range(segments):
            k2 = (k + 1) % segments
            if len(lo) == 1 and len(hi) == 1:
                continue
            if len(lo) == 1:
                face = (lo[0], hi[k], hi[k2])
            elif len(hi) == 1:
                face = (lo[k], lo[k2], hi[0])
            else:
                face = (lo[k], lo[k2], hi[k2], hi[k])
            try:
                bm.faces.new(face)
            except ValueError:
                pass
    for ring in (rings[0], rings[-1]):  # open ends get a flat cap
        if len(ring) > 2:
            try:
                bm.faces.new(ring)
            except ValueError:
                pass
    return _k_object(name, bm, loc, rot, mat, smooth=smooth)


def kit_rounded_rect(width, height, radius, steps=8):
    """Outline points of a rounded rectangle centred at the origin (for kit_extrude)."""
    r = max(0.0, min(radius, width / 2 - 1e-5, height / 2 - 1e-5))
    w, h = width / 2 - r, height / 2 - r
    pts = []
    for cx, cy, a0 in ((w, h, 0), (-w, h, 90), (-w, -h, 180), (w, -h, 270)):
        for i in range(steps + 1):
            a = _km.radians(a0 + 90 * i / steps)
            pts.append((cx + r * _km.cos(a), cy + r * _km.sin(a)))
    return pts


def kit_circle_points(radius, count=32, cx=0.0, cy=0.0):
    return [(cx + radius * _km.cos(2 * _km.pi * i / count), cy + radius * _km.sin(2 * _km.pi * i / count))
            for i in range(count)]


def _k_soften_closed(pts, steps=4, sharp_deg=50.0):
    """A closed outline rounded through its points (Catmull-Rom), except at
    sharp corners (a turn over *sharp_deg*), which stay crisp."""
    n = len(pts)
    if n < 4:
        return pts

    def turn(i):
        ax, ay = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        bx, by = pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1]
        la, lb = _km.hypot(ax, ay), _km.hypot(bx, by)
        if la < 1e-9 or lb < 1e-9:
            return 0.0
        return _km.degrees(_km.acos(max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))))

    sharp = [turn(i) > sharp_deg for i in range(n)]
    out = []
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        out.append(p1)
        if sharp[i] or sharp[(i + 1) % n]:
            continue
        for k in range(1, steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    return out


def kit_extrude(name, outline, depth, loc=(0, 0, 0), rot=(0, 0, 0), bevel=0.0, mat=None, smooth=True):
    """A closed outline [(x, y), ...] in the xy plane made solid, depth along z
    (centred). Stand it up with rot=(90, 0, 0). The outline is rounded
    through its points (guitar bodies, leaves, car profiles) but sharp
    corners stay sharp; smooth=False keeps it as drawn."""
    pts = [(float(x), float(y)) for x, y in outline]
    if len(pts) > 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if smooth and len(pts) < 200:
        pts = _k_soften_closed(pts)
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    if area < 0:
        pts.reverse()
    bm = _kbm.new()
    bottom = [bm.verts.new((x, y, -depth / 2)) for x, y in pts]
    top = [bm.verts.new((x, y, depth / 2)) for x, y in pts]
    n = len(pts)
    bm.faces.new(list(reversed(bottom)))
    bm.faces.new(top)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bottom[i], bottom[j], top[j], top[i]))
    obj = _k_object(name, bm, loc, rot, mat)
    if bevel:
        kit_bevel(obj, min(bevel, depth * 0.49), 3)
    return obj


def kit_tube(name, points, radius, mat=None, closed=False, resolution=12):
    """A smooth round tube through [(x, y, z), ...] world points (metres):
    handles, cables, bent arms, frames. Converted to a closed mesh."""
    curve = _kb.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = radius
    curve.bevel_resolution = 6
    try:
        curve.use_fill_caps = True
    except Exception:
        pass
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, p in zip(spline.bezier_points, points):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    spline.use_cyclic_u = closed
    tmp = _kb.data.objects.new(name + "_curva", curve)
    _k_link(tmp)
    deps = _kb.context.evaluated_depsgraph_get()
    mesh = _kb.data.meshes.new_from_object(tmp.evaluated_get(deps))
    _kb.data.objects.remove(tmp, do_unlink=True)
    _kb.data.curves.remove(curve)
    mesh.name = name
    obj = _kb.data.objects.new(name, mesh)
    _k_link(obj)
    bm = _kbm.new()
    bm.from_mesh(mesh)
    _kbm.ops.remove_doubles(bm, verts=bm.verts, dist=radius * 0.01)
    _kbm.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    if mat is not None:
        mesh.materials.append(mat)
    return kit_smooth(obj)


def kit_text(name, body, size=0.05, depth=0.004, loc=(0, 0, 0), rot=(90, 0, 0), mat=None):
    """3D text (labels, logos) as a mesh, centred."""
    curve = _kb.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.extrude = depth / 2
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    tmp = _kb.data.objects.new(name + "_texto", curve)
    _k_link(tmp)
    deps = _kb.context.evaluated_depsgraph_get()
    mesh = _kb.data.meshes.new_from_object(tmp.evaluated_get(deps))
    _kb.data.objects.remove(tmp, do_unlink=True)
    mesh.name = name
    bm = _kbm.new()
    bm.from_mesh(mesh)
    _kbm.ops.remove_doubles(bm, verts=bm.verts, dist=min(size, depth) * 0.002)
    _kbm.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = _kb.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler = _k_rot(rot)
    _k_link(obj)
    if mat is not None:
        mesh.materials.append(mat)
    return obj


def kit_parent(name, objects):
    """One empty named after the model holding every part (world places kept)."""
    root = _kb.data.objects.get(name)
    if root is None:
        root = _kb.data.objects.new(name, None)
        _k_link(root)
    _kb.context.view_layer.update()
    for obj in objects:
        if obj is None or obj is root:
            continue
        world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world
    return root


def kit_copy(obj, loc=None, rot=None, name=None):
    """A linked duplicate (shares the mesh) at a new place."""
    dup = obj.copy()
    if name:
        dup.name = name
    if loc is not None:
        dup.location = loc
    if rot is not None:
        dup.rotation_euler = _k_rot(rot)
    return _k_link(dup)


def kit_mirror_x(obj, name=None):
    """The mirror twin across x = 0 (left/right symmetric parts)."""
    dup = kit_copy(obj, name=name or (obj.name + "_R"))
    dup.location.x = -obj.location.x
    dup.rotation_euler = _KEul((obj.rotation_euler.x, -obj.rotation_euler.y, -obj.rotation_euler.z), "XYZ")
    dup.scale.x = -obj.scale.x
    return dup


def kit_array_circle(obj, count, radius, z=None, center=(0, 0), face_out=True):
    """*count* copies of obj around a circle in the xy plane (bolts, spokes, keys)."""
    out = []
    for i in range(count):
        a = 2 * _km.pi * i / count
        dup = obj if i == 0 else kit_copy(obj, name="%s_%d" % (obj.name.split("_")[0], i + 1))
        dup.location = (center[0] + radius * _km.cos(a), center[1] + radius * _km.sin(a),
                        obj.location.z if z is None else z)
        if face_out:
            dup.rotation_euler.z = a
        out.append(dup)
    return out


def kit_cut(obj, cutter):
    """Boolean hole: *cutter* is subtracted from obj (ports, holes, slots).
    The cutter stays hidden from the render."""
    mod = obj.modifiers.new("Corte", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    try:
        mod.solver = "EXACT"
    except Exception:
        pass
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    cutter["sergio_cutter"] = True
    return obj
'''

KIT_DOC = """SERGIO'S MODELLING KIT (already defined: call these, do not import them). \
They build real shapes with the data API and work in every Blender version — use \
them for EVERY part instead of primitive operators (a model made of plain cubes is \
a failure). All sizes in metres, rot in degrees (x, y, z), mat from kit_material:
- kit_material(name, color=(r,g,b), metallic=0, roughness=0.5, transmission=0, \
emission=None, strength=1, alpha=1, ior=1.45, coat=0) -> material
- kit_lathe(name, profile=[(radius, z), ...], loc, rot, segments=64, mat, \
sharp=False) -> round things turned around z (the curve is rounded smoothly \
through 6-14 points; sharp=True keeps straight cuts): cups, bottles, vases, lampshades, bulbs, knobs, wheels, \
lenses. Radius 0 closes at the axis; a hollow cup goes up the outside and back down \
the inside: [(0,0),(0.04,0),(0.045,0.1),(0.041,0.1),(0.036,0.006),(0,0.006)]
- kit_extrude(name, outline=[(x, y), ...], depth, loc, rot, bevel=0, mat, smooth=True) \
-> a closed outline made solid (depth along z; rot=(90,0,0) stands it up); the \
outline is rounded through 8-30 points, sharp corners (> 50 degrees) stay sharp: phone bodies, \
guitar bodies, logos, brackets, leaves. kit_rounded_rect(w, h, r) and \
kit_circle_points(r, n) give outlines.
- kit_tube(name, points=[(x,y,z), ...], radius, mat) -> smooth bent tube through \
WORLD points: handles, cables, frames, bent arms, rails.
- kit_box(name, size=(x,y,z), loc, rot, bevel=0.003, mat) -> only for truly boxy \
parts, ALWAYS with a bevel.
- kit_cylinder(name, radius, depth, loc, rot, top_radius=None, verts=48, bevel, mat) \
(a cone/frustum with top_radius); kit_sphere(name, radius, loc, scale=(1,1,1), rot, mat)
- kit_text(name, body, size, depth, loc, rot=(90,0,0), mat) -> labels and logos
- kit_copy(obj, loc, rot, name) linked duplicate; kit_mirror_x(obj) left/right twin; \
kit_array_circle(obj, count, radius) copies around a circle; kit_cut(obj, cutter) \
boolean hole; kit_bevel(obj, width); kit_subsurf(obj, levels); kit_smooth(obj)
- kit_parent(model_name, [objects]) -> the empty that holds every part (call last).
Every kit function returns the object; its origin is the given loc."""

__all__ = ["KIT", "KIT_DOC"]

"""Editable kinetic typography and a product turntable, in 2D or true 3D.

The scene contains real keyframes, studio lights and a camera. A .blend file
is the deliverable; rendering still requires Blender on the user's computer.
"""

from __future__ import annotations

from openjarvis.vfx._base import params_with_defaults, py

DESCRIPTION = "Keyframed 2D titles or a 3D product reveal with editable text, camera and studio lights."
PARAMS = {
    "title": ("Sergio", "title, at most 80 characters"),
    "mode": ("3d", "2d or 3d"),
    "frames": (72, "animation length, 24-240 frames at 24 fps"),
}


def build(**kw) -> str:
    p = params_with_defaults(PARAMS, kw)
    if p["mode"] not in ("2d", "3d") or not 24 <= p["frames"] <= 240:
        raise ValueError("Use mode 2d/3d and 24-240 frames")
    title = str(p["title"]).strip()
    if not title or len(title) > 80:
        raise ValueError("Use a title of 1-80 characters")
    return f"""
sc = bpy.context.scene
sc.frame_end = {p["frames"]}
sc.render.fps = 24
vfx_engine("EEVEE", 32)
vfx_world((0.92, 0.94, 0.97), 0.8)
blue = vfx_material("Sergio Blue", (0.003, 0.15, 0.98, 1), metallic=0.22, roughness=0.24)
ink = vfx_material("Ink", (0.012, 0.018, 0.03, 1), roughness=0.65)
font = bpy.data.curves.new("Editable Title", "FONT")
font.body = {py(title)}
font.align_x, font.align_y = "CENTER", "CENTER"
font.size = min(0.8, 8 / max(1, len(font.body)))
font.extrude = {0.035 if p["mode"] == "3d" else 0.0}
text = bpy.data.objects.new("Title", font)
sc.collection.objects.link(text)
vfx_assign(text, ink)
text.location = (0, 0, 1.5)
text.scale = (0.05, 0.05, 0.05)
text.keyframe_insert("scale", frame=1)
text.scale = (1, 1, 1)
text.keyframe_insert("scale", frame=18)
text.keyframe_insert("scale", frame={p["frames"]})
if {py(p["mode"])} == "3d":
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=0.7, location=(0, 0, 0))
    product = bpy.context.object
    product.name = "Replace With Product"
    vfx_assign(product, blue)
    bpy.ops.object.shade_smooth()
    product.scale = (0.02, 0.02, 0.02)
    product.keyframe_insert("scale", frame=1)
    product.scale = (1, 1, 1)
    product.keyframe_insert("scale", frame=24)
    product.rotation_euler = (0, 0, 0)
    product.keyframe_insert("rotation_euler", frame=1)
    product.rotation_euler = (0.2, 0.6, math.tau)
    product.keyframe_insert("rotation_euler", frame={p["frames"]})
cam = vfx_camera((0, 0, 9), (0, 0, 0.65), 45)
cam.data.type = "ORTHO"
cam.data.ortho_scale = 6
vfx_light("AREA", 600, (-3, 2, 5))
vfx_light("AREA", 400, (3, -1, 4))
vfx_info(effect="motion_graphics", mode={py(p["mode"])}, frames=sc.frame_end, fps=sc.render.fps)
"""


__all__ = ["DESCRIPTION", "PARAMS", "build"]

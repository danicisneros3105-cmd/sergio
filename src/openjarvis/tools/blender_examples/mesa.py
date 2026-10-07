import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)

SERGIO_LAYOUT = [
    {"part": "Tablero", "center_cm": [0, 0, 73], "size_cm": [120, 70, 4]},
    {"part": "Pata", "center_cm": [0, 0, 35.5], "size_cm": [110, 60, 71]},
    {"part": "Faldon", "center_cm": [0, 0, 67], "size_cm": [104, 54, 8]},
]
CM = 0.01


def material(name, color, rough=0.5, metal=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    try:  # wood grain: a stretched wave texture, never blocking the part
        wave = mat.node_tree.nodes.new("ShaderNodeTexWave")
        wave.inputs["Scale"].default_value = 3.0
        wave.inputs["Distortion"].default_value = 6.0
        ramp = mat.node_tree.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*[c * 0.7 for c in color], 1)
        ramp.color_ramp.elements[1].color = (*color, 1)
        mat.node_tree.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
        mat.node_tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    except Exception:
        pass
    return mat


def box(name, center_cm, size_cm, mat, bevel_cm=0.4):
    bpy.ops.mesh.primitive_cube_add(size=1, location=[c * CM for c in center_cm])
    obj = bpy.context.object
    obj.name = name
    obj.scale = [s * CM for s in size_cm]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)  # keep the origin at the part
    bev = obj.modifiers.new("Bisel", "BEVEL")
    bev.width = bevel_cm * CM
    bev.segments = 3
    obj.data.materials.append(mat)
    return obj


WOOD = material("Roble", (0.55, 0.36, 0.2), 0.45)


def tablero():
    box("Tablero", (0, 0, 73), (120, 70, 4), WOOD, 0.6)


def patas():
    first = box("Pata_1", (-52, -27, 35.5), (6, 6, 71), WOOD)
    for i, (x, y) in enumerate(((52, -27), (-52, 27), (52, 27)), start=2):
        dup = first.copy()  # linked duplicate: shares the mesh, no extra memory
        dup.name = f"Pata_{i}"
        dup.location = (x * CM, y * CM, 35.5 * CM)
        bpy.context.scene.collection.objects.link(dup)


def faldon():
    for name, c, s in (("Faldon_frente", (0, -27, 67), (98, 2.5, 8)), ("Faldon_atras", (0, 27, 67), (98, 2.5, 8)),
                       ("Faldon_izq", (-52, 0, 67), (2.5, 48, 8)), ("Faldon_der", (52, 0, 67), (2.5, 48, 8))):
        box(name, c, s, WOOD, 0.2)


tablero()
patas()
faldon()

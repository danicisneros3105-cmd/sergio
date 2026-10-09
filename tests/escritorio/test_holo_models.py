"""Holograms of anything (designed parts) and the live link to Blender."""

import json

import numpy as np
from sergio_escritorio.holo import (
    HoloScene,
    assemble,
    blender_state,
    recipe_request,
    rot_axis,
    to_bpy,
)
from sergio_escritorio.quick import parse_quick

PHONE = {
    "name": "Teléfono",
    "description": "Un teléfono moderno.",
    "parts": [
        {"name": "Cuerpo", "shape": "rounded_box", "size": [0.072, 0.15, 0.008], "pos": [0, 0, 0],
         "rot": [0, 0, 0], "color": [0.1, 0.1, 0.12]},
        {"name": "Pantalla", "shape": "box", "size": [0.068, 0.145, 0.001], "pos": [0, 0, 0.0045],
         "rot": [0, 0, 0], "color": [0.02, 0.02, 0.03]},
        {"name": "Lente", "shape": "cylinder", "size": [0.012, 0.002, 0.012], "pos": [-0.02, 0.06, -0.005],
         "rot": [90, 0, 0], "color": [0.0, 0.0, 0.0]},
        {"name": "Anillo", "shape": "torus", "size": [0.014, 0.001, 0.014], "pos": [-0.02, 0.06, -0.005],
         "rot": [90, 0, 0], "color": [0.7, 0.7, 0.7]},
    ],
}  # fmt: skip


def test_a_designed_object_keeps_its_parts_colours_and_real_size():
    mesh, base = assemble(PHONE)
    assert len(mesh.colors) == len(mesh.faces) > 100  # every part, every face coloured
    assert {tuple(c) for c in mesh.colors} >= {(0.1, 0.1, 0.12), (0.7, 0.7, 0.7)}
    assert abs(mesh.size() - 1.0) < 1e-6  # shown big enough to work with
    scene = HoloScene()
    phone = scene.add_model(PHONE)
    assert phone.size_cm() == 15  # but it is a 15 cm phone, not a cube
    assert phone.name.startswith("Teléfono")
    faces = scene.render(960, 540)
    assert faces and all(f["model"] for f in faces)


def test_blender_gets_real_size_and_follows_the_hands():
    scene = HoloScene()
    phone = scene.add_model(PHONE)
    first = blender_state(scene.objects)["objects"]["Holo 1"]
    span = np.ptp(np.array(first["verts"]), axis=0)
    assert abs(span.max() - 0.15) < 0.002  # real metres in Blender (z up)
    assert abs(span[2] - 0.15) < 0.002 and len(first["colors"]) == len(first["faces"])
    phone.pos = phone.pos + np.array([0.5, 0.0, 0.0])
    phone.rot = rot_axis((0, 1, 0), 1.0) @ phone.rot
    phone.scale = 2.0
    moved = blender_state(scene.objects)["objects"]["Holo 1"]
    assert (
        moved["matrix"] != first["matrix"] and moved["vh"] == first["vh"]
    )  # moved, not reshaped
    phone.mesh.vertices[0] *= 1.5  # sculpted with the hands
    assert blender_state(scene.objects)["objects"]["Holo 1"]["vh"] != first["vh"]
    script = to_bpy(scene.objects, "C:/x/h.blend", "C:/x/h.sync.json")
    assert "bpy.app.timers.register(_sync" in script and "C:/x/h.sync.json" in script
    json.loads(
        script.split('FIRST = json.loads(r"""')[1].split('""")')[0]
    )  # valid data


def test_blender_pro_gets_the_designed_parts():
    scene = HoloScene()
    phone = scene.add_model(PHONE)
    text = recipe_request(phone)
    assert "Lente: cylinder" in text and "ultra detallado" in text


def test_voice_orders_for_designed_holograms():
    assert parse_quick("haz un modelo de un teléfono").kind == "holo_model"
    assert parse_quick("haz un holograma de una silla gamer").kind == "holo_model"
    assert parse_quick("crea una guitarra eléctrica").kind == "holo_maybe"
    assert parse_quick("crea un cubo rojo").kind == "holo"  # plain shapes: instant
    assert parse_quick("haz una lista de compras") is None
    assert parse_quick("en blender haz un teléfono").kind == "blender_task"

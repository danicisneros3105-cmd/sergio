"""Holograms shaped with the hands (Sergio ve), with synthetic hands."""

from __future__ import annotations

import math
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
from sergio_escritorio import holo

VIEW = (480.0, 270.0)
BASE = {0: (0, 0.0), 1: (-0.25, -0.1), 2: (-0.4, -0.25), 3: (-0.5, -0.4), 4: (-0.55, -0.55),
        5: (-0.2, -0.6), 6: (-0.22, -0.8), 7: (-0.23, -0.95), 8: (-0.24, -1.1),
        9: (0, -0.62), 10: (0, -0.85), 11: (0, -1.0), 12: (0, -1.15),
        13: (0.18, -0.58), 14: (0.2, -0.78), 15: (0.21, -0.92), 16: (0.22, -1.05),
        17: (0.33, -0.5), 18: (0.36, -0.66), 19: (0.38, -0.78), 20: (0.4, -0.9)}  # fmt: skip
PINCH_AT = (-0.36, -0.8)


def hand_at(u, v, size=0.12, angle=0.0, pinch=True):
    """A right hand (MediaPipe landmarks, mirrored view) pinching at view px (u, v)."""
    pts = dict(BASE)
    if pinch:
        pts[4] = pts[8] = PINCH_AT
        pts[3], pts[7] = (-0.45, -0.6), (-0.3, -0.85)
    c, s = math.cos(angle), math.sin(angle)
    rx, ry = PINCH_AT[0] * c - PINCH_AT[1] * s, PINCH_AT[0] * s + PINCH_AT[1] * c
    xn, yn = 1 - u / VIEW[0], v / VIEW[1]
    cx, cy = xn - rx * size * 9 / 16, yn - ry * size
    out = []
    for i in range(21):
        x, y = pts[i]
        x, y = x * c - y * s, x * s + y * c
        out.append((cx + x * size * 9 / 16, cy + y * size, 0.0))
    return out


def scene_with(kind="cubo"):
    sc = holo.HoloScene()
    sc.view = VIEW
    obj = sc.add(kind)
    obj.spin[:] = 0
    ((u, v),) = holo.project(obj.pos[None], *VIEW)[0]
    return sc, obj, u, v


def test_shapes_are_closed_meshes_with_sensible_sizes():
    for kind, make in holo.MAKERS.items():
        mesh = make()
        assert len(mesh.vertices) >= 4 and mesh.faces, kind
        assert all(max(f) < len(mesh.vertices) for f in mesh.faces), kind
        assert 0.2 < mesh.size() < 0.8, kind


def test_pinch_grabs_moves_and_turns_like_the_wrist():
    sc, cube, u, v = scene_with()
    rot0 = cube.rot.copy()
    sc.update_hands([hand_at(u, v)], 1 / 30, True, 0.0)
    assert cube.held and sc.grips[0].target == cube.id
    for k in range(1, 8):
        sc.update_hands(
            [hand_at(u + 10 * k, v - 4 * k, angle=math.radians(4 * k))],
            1 / 30,
            True,
            k / 30,
        )
    k = holo.CAM_Z / (holo.CAM_Z - cube.pos[2]) * (VIEW[0] / 2) / holo.HALF_W
    assert cube.pos[0] - (-1.1) == pytest.approx(70 / k, abs=0.02)
    assert cube.pos[1] - 0.1 == pytest.approx(28 / k, abs=0.02)
    axis, angle = holo.axis_angle(cube.rot @ rot0.T)
    assert abs(axis[2]) > 0.99 and math.degrees(angle) == pytest.approx(28, abs=1.5)


def test_letting_go_in_motion_throws_it():
    sc, cube, u, v = scene_with()
    sc.update_hands([hand_at(u, v)], 1 / 30, True, 0.0)
    for k in range(1, 5):
        sc.update_hands([hand_at(u + 12 * k, v)], 1 / 30, True, k / 30)
    sc.update_hands([hand_at(u + 60, v, pinch=False)], 1 / 30, True, 5 / 30)
    assert not cube.held and cube.vel[0] > 0.5
    x0 = cube.pos[0]
    sc.step(0.1)
    assert cube.pos[0] > x0


def test_hand_towards_the_camera_brings_it_closer():
    sc, cube, u, v = scene_with()
    z0 = cube.pos[2]
    sc.update_hands([hand_at(u, v, size=0.12)], 1 / 30, True, 0.0)
    sc.update_hands([hand_at(u, v, size=0.16)], 1 / 30, True, 0.03)
    assert cube.pos[2] > z0 + 0.1


def test_two_hands_scale_it():
    sc, cube, u, v = scene_with()
    sc.update_hands([hand_at(u - 20, v), hand_at(u + 20, v)], 1 / 30, True, 0.0)
    sc.update_hands([hand_at(u - 40, v), hand_at(u + 40, v)], 1 / 30, True, 0.03)
    assert cube.scale == pytest.approx(2.0, rel=0.05)


def test_sculpting_pulls_the_surface_locally():
    sc, ball, u, v = scene_with("esfera")
    sc.mode = "esculpir"
    before = ball.mesh.vertices.copy()
    sc.update_hands([hand_at(u + 8, v - 8)], 1 / 30, True, 0.0)
    grip = sc.grips[0]
    assert grip.vertex >= 0
    sc.update_hands([hand_at(u + 38, v - 38)], 1 / 30, True, 0.03)
    moved = np.linalg.norm(ball.mesh.vertices - before, axis=1)
    assert moved[grip.vertex] > 0.1  # pulled
    assert np.sum(moved > 0.01) < len(moved) / 2  # only nearby clay follows


def test_drawing_in_the_air_makes_a_tube():
    sc = holo.HoloScene()
    sc.view = VIEW
    sc.command("modo dibujar")
    sc.update_hands([hand_at(100, 150)], 1 / 30, True, 0.0)
    for k in range(1, 15):
        sc.update_hands(
            [hand_at(100 + 15 * k, 150 - 30 * math.sin(k / 3))], 1 / 30, True, k / 30
        )
    assert len(sc.stroke) > 5
    sc.update_hands([hand_at(320, 150, pinch=False)], 1 / 30, True, 0.6)
    (obj,) = sc.objects
    assert obj.kind == "tubo" and len(obj.mesh.vertices) > 40 and not sc.stroke


def test_lathe_and_extrusion_from_strokes():
    profile = [(0.1 + 0.05 * math.sin(i / 3), i * 0.05, 0) for i in range(12)]
    vase = holo.lathe_from_stroke(profile)
    assert vase.size() > 0.4 and vase.smooth
    square = [(0, 0, 0), (0.3, 0, 0), (0.3, 0.3, 0), (0, 0.3, 0)]
    block = holo.extrude_stroke(square, 0.2)
    assert len(block.vertices) == 8 and len(block.faces) == 6


@pytest.mark.parametrize(
    "said, check",
    [
        (
            "crea dos esferas rojas",
            lambda sc, r: (
                len(sc.objects) == 2 and sc.objects[0].color == holo.COLORS["rojo"]
            ),
        ),
        ("crea un jarrón", lambda sc, r: sc.objects[0].kind == "jarron"),
        ("modo esculpir", lambda sc, r: sc.mode == "esculpir"),
        (
            "dibuja un jarrón en el aire con el torno",
            lambda sc, r: sc.mode == "dibujar" and sc.pen == "torno",
        ),
        ("activa la gravedad", lambda sc, r: sc.gravity),
    ],
)
def test_voice_orders(said, check):
    sc = holo.HoloScene()
    reply = sc.command(said)
    assert check(sc, reply), reply


def test_voice_edits_the_current_one():
    sc = holo.HoloScene()
    sc.command("crea un cubo")
    cube = sc.objects[0]
    assert "más grande" in sc.command(
        "hazlo más grande"
    ) and cube.scale == pytest.approx(1.3)
    assert "azul" in sc.command("ponlo azul")
    sc.command("duplícalo")
    assert len(sc.objects) == 2
    sc.command("borra todo")
    assert sc.objects == []


def test_gravity_drops_and_bounces_on_the_floor():
    sc, cube, _u, _v = scene_with()
    sc.gravity = True
    for _ in range(120):
        sc.step(1 / 30)
    assert cube.pos[1] - cube.radius() == pytest.approx(holo.FLOOR, abs=0.05)


def test_render_list_is_far_to_near_with_front_faces():
    sc, _cube, _u, _v = scene_with()
    sc.add("esfera").spin[:] = 0
    faces = sc.render(*VIEW)
    depths = [f["depth"] for f in faces]
    assert depths == sorted(depths, reverse=True)
    assert any(f["front"] for f in faces) and any(not f["front"] for f in faces)


def test_obj_export():
    sc, _cube, _u, _v = scene_with()
    text = holo.to_obj(sc.objects)
    assert text.count("\nv ") == 8 and text.count("\nf ") == 6


BPY = os.environ.get("SERGIO_BPY_PYTHON", "")


@pytest.mark.skipif(
    not (BPY and Path(BPY).exists()), reason="Blender (bpy) not available"
)
def test_holograms_rebuild_in_blender_and_save(tmp_path):
    sc = holo.HoloScene()
    sc.command("crea un cubo rojo")
    sc.command("crea una esfera")
    sc.command("crea un toroide dorado")
    target = tmp_path / "hologramas.blend"
    script = tmp_path / "holo.py"
    script.write_text(holo.to_bpy(sc.objects, str(target)))
    done = subprocess.run(
        [BPY, "-c", f"import runpy; runpy.run_path({str(script)!r})"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert "SERGIO_SAVED" in done.stdout and " 3" in done.stdout, done.stderr[-2000:]
    assert target.exists()


def test_a_pinch_near_a_hologram_grabs_it():
    sc, cube, u, v = scene_with()
    sc.update_hands([hand_at(u + 70, v + 40)], 1 / 30, True, 0.0)  # not on it
    assert cube.held


@pytest.mark.parametrize(
    "said, check",
    [
        ("muévelo a la derecha", lambda o, p0, r0: o.pos[0] > p0[0]),
        ("acércalo", lambda o, p0, r0: o.pos[2] > p0[2]),
        ("gíralo 90 grados", lambda o, p0, r0: not np.allclose(o.rot, r0)),
        ("céntralo", lambda o, p0, r0: np.allclose(o.pos, [0, 0.1, 0])),
    ],
)
def test_voice_moves_and_turns_the_hologram(said, check):
    sc = holo.HoloScene()
    sc.command("crea un cubo")
    obj = sc.objects[0]
    p0, r0 = obj.pos.copy(), obj.rot.copy()
    sc.command(said)
    assert check(obj, p0, r0)


def test_every_shape_is_a_closed_solid_facing_outward():
    from collections import Counter

    for kind, make in holo.MAKERS.items():
        mesh = make()
        _u, ids = np.unique(np.round(mesh.vertices, 6), axis=0, return_inverse=True)
        ids = ids.reshape(-1)
        edges = Counter()
        for face in mesh.faces:
            g = [int(ids[i]) for i in face]
            g = [x for k, x in enumerate(g) if x != g[k - 1]]
            for a, b in zip(g, g[1:] + g[:1]):
                edges[(a, b)] += 1
        assert all(n == 1 and edges.get((b, a)) == 1 for (a, b), n in edges.items()), kind
        v = mesh.vertices
        volume = sum(
            np.dot(v[f[0]], np.cross(v[f[k]], v[f[k + 1]])) / 6
            for f in mesh.faces
            for k in range(1, len(f) - 1)
        )
        assert volume > 0, kind  # outward: Blender and the glass light it right


@pytest.mark.parametrize(
    ("said", "kind", "answer"),
    [
        ("crea una estrella dorada", "estrella", "Creé 1 estrella dorada."),
        ("crea dos corazones", "corazon", "Creé 2 corazones."),
        ("crea una luna", "luna", "Creé 1 luna."),
        ("crea un icosaedro", "icosaedro", "Creé 1 icosaedro."),
    ],
)
def test_new_shapes_by_voice(said, kind, answer):
    sc = holo.HoloScene()
    assert sc.command(said) == answer and sc.objects[-1].kind == kind


def test_glass_style_by_voice_and_its_drawing_data():
    sc = holo.HoloScene()
    assert sc.style == "cristal"
    assert "holograma" in sc.command("estilo holograma") and sc.style == "holograma"
    assert "cristal" in sc.command("estilo cristal") and sc.style == "cristal"
    assert not sc.objects  # "cristal" is a style, not a diamond
    sc.command("crea un cubo")
    sc.command("crea una esfera")
    (cube, ball) = sc.glass(*VIEW)[-2:] if sc.objects[0].pos[2] <= sc.objects[1].pos[2] else sc.glass(*VIEW)
    for ob in (cube, ball):
        assert ob["faces"] and ob["outline"] and ob["radius"] > 10
        assert all(0 <= f["rim"] <= 1 for f in ob["faces"])
    by_name = {o["name"].split()[0]: o for o in sc.glass(*VIEW)}
    assert by_name["Cubo"]["edges"] or by_name["Cubo"]["back_edges"]  # sharp creases
    assert not by_name["Esfera"]["edges"]  # smooth: no wire grid


def test_a_flickering_pinch_does_not_drop_it_but_an_open_hand_does():
    sc, cube, u, v = scene_with()
    sc.update_hands([hand_at(u, v)], 1 / 30, True, 0.0)
    assert cube.held
    sc.update_hands([], 1 / 30, True, 0.03)  # the hand lost for a frame
    assert cube.held and sc.grips
    sc.update_hands([hand_at(u + 10, v)], 1 / 30, True, 0.06)
    assert cube.held
    sc.update_hands([], 1 / 30, True, 0.1)
    sc.update_hands([], 1 / 30, True, 0.3)  # gone for good
    assert not cube.held and not sc.grips


def test_what_a_pinch_would_take_is_highlighted():
    sc, cube, u, v = scene_with()
    sc.update_hands([hand_at(u + 10, v, pinch=False)], 1 / 30, True, 0.0)
    assert sc.hover == {0: cube.id}
    sc.update_hands([hand_at(u, v)], 1 / 30, True, 0.03)
    assert sc.hover == {} and cube.held


def test_a_trembling_wrist_does_not_turn_it():
    sc, cube, u, v = scene_with()
    rot0 = cube.rot.copy()
    sc.update_hands([hand_at(u, v)], 1 / 30, True, 0.0)
    sc.update_hands([hand_at(u, v, angle=math.radians(2))], 1 / 30, True, 0.03)
    assert np.allclose(cube.rot, rot0)


def test_holograms_move_on_springs_like_visionos():
    from sergio_escritorio.holo import HoloScene

    scene = HoloScene()
    cube = scene.add("cubo")
    assert cube.appear == 0.0 and cube.display() < 0.6  # pops in from small
    for _ in range(30):
        scene.step(1 / 60)
    peak = 0.0
    cube.held = True
    for _ in range(90):
        scene.step(1 / 60)
        peak = max(peak, cube.lift)
    assert abs(cube.appear - 1.0) < 0.05 and 1.0 < peak < 1.25  # a soft overshoot
    assert cube.display() > 1.05 and cube.hover_k > 0.9  # held: bigger and glowing
    real = cube.world()
    assert abs(real.max() - cube.world(display=False).max()) < 1e-9  # the real size never changes
    cube.held = False
    for _ in range(120):
        scene.step(1 / 60)
    assert cube.lift < 0.02 and cube.hover_k < 0.05

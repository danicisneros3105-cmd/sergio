"""Physics over the camera: objects with mass, made and thrown by hand."""

import random
from types import SimpleNamespace

import pytest

pytest.importorskip("pymunk")
from sergio_escritorio.physics import COLORS, MAX_OBJECTS, Sandbox  # noqa: E402


def _world():
    return Sandbox(aspect=9 / 16, rng=random.Random(4))


def _run(world, seconds, dt=1 / 60, hands=None, mirror=False):
    t = 0.0
    while t < seconds:
        if hands is not None:
            world.update_hands(hands(t), dt, mirror, now=t)
        world.step(dt)
        t += dt


def _hand(x, y, pinch):
    """21 landmarks (0..1): wrist, palm and fingertips around (x, y)."""
    lm = [(x, y + 0.02, 0.0)] * 21
    lm = [list(p) for p in lm]
    lm[0] = [x, y + 0.18, 0]  # wrist
    lm[9] = [x, y + 0.03, 0]  # middle knuckle: palm size 0.15
    lm[8] = [x + 0.01, y - 0.06, 0]  # index tip
    lm[4] = [x - 0.01, y - 0.05, 0] if pinch else [x - 0.09, y + 0.02, 0]
    lm[12], lm[16], lm[20] = [x + 0.03, y - 0.07, 0], [x + 0.05, y - 0.05, 0], [x + 0.07, y - 0.02, 0]
    return SimpleNamespace(landmarks=[tuple(p) for p in lm])


def test_a_ball_falls_and_rests_on_the_floor():
    world = _world()
    ball = world.add("pelota", at=(500, 100), size=80)
    _run(world, 3.0)
    x, y = ball.position
    assert y == pytest.approx(world.floor - 6 - 40, abs=3)
    assert abs(ball.body.velocity.y) < 5


def test_spoken_orders():
    world = _world()
    assert world.command("crea 5 cubos rojos") == "Ahí van 5 cubos."
    assert len(world.things) == 5
    assert all(t.shape == "cubo" and t.color == COLORS["rojo"] for t in world.things)
    assert world.command("lanza una pelota grande") == "Ahí tiene su pelota."
    assert world.things[-1].size == 120 and world.things[-1].body.velocity.y < 0
    assert "flota" in world.command("gravedad cero")
    assert world.space.gravity == (0, 0)
    assert "arriba" in world.command("gravedad invertida")
    world.command("estrella")
    assert world.things[-1].shape == "estrella" and len(world.things[-1].outline()) == 10
    assert world.command("borra los objetos") == "Listo, quité 7 objetos."
    assert world.things == []


def test_too_many_objects_drop_the_oldest():
    world = _world()
    first = world.add("pelota")
    for _ in range(MAX_OBJECTS):
        world.add("cubo")
    assert len(world.things) == MAX_OBJECTS and first not in world.things


def test_grab_and_throw():
    world = _world()
    ball = world.add("pelota", at=(300, world.floor - 60), size=60)
    _run(world, 1.0)
    bx, by = ball.position

    def hands(t):
        # pinch on the ball, carry it right and up fast, then let go
        x = bx / 1000 + max(0.0, t - 0.3) * 0.9
        y = (by - 10) / world.height - max(0.0, t - 0.3) * 0.5 + 0.05
        return [_hand(x, y, pinch=t < 0.7)]

    _run(world, 0.72, hands=hands)
    assert ball.body.velocity.x > 300  # it flies off with the hand's speed
    assert all(s.grabbed is None for s in world.hands.values())


def test_two_hands_pull_a_box_into_existence():
    world = _world()

    def hands(t):
        spread = min(t, 0.5) * 0.4  # hands move apart while pinching
        pinch = t < 0.6
        return [_hand(0.5 - spread / 2, 0.4, pinch), _hand(0.5 + spread / 2, 0.4, pinch)]

    _run(world, 0.65, hands=hands)
    assert len(world.things) == 1
    box = world.things[0]
    assert box.shape == "cubo" and box.size > 150


def test_hold_a_pinch_in_the_air_to_make_a_ball():
    world = _world()
    _run(world, 1.0, hands=lambda t: [_hand(0.5, 0.3, pinch=True)])
    assert [t.shape for t in world.things] == ["pelota"]
    assert world.hands[0].grabbed is not None  # it is in your fingers


def test_fingertips_push_things():
    world = _world()
    ball = world.add("pelota", at=(500, world.floor - 50), size=70)
    _run(world, 1.0)
    start_x = ball.position[0]

    def hands(t):  # an open hand sweeps from the left through the ball
        return [_hand(0.30 + t * 0.6, (world.floor - 60) / world.height, pinch=False)]

    _run(world, 0.6, hands=hands)
    assert ball.position[0] > start_x + 40


def test_mirror_maps_your_right_to_the_screen_right():
    world = _world()
    assert world.to_world(0.2, 0.5, mirror=True) == (800.0, world.height / 2)
    assert world.to_world(0.2, 0.5, mirror=False) == (200.0, world.height / 2)

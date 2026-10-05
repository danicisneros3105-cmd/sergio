"""Hands: REAL MediaPipe landmarks (saved from photos), smoothing and the
holograms mode (no gesture or air-mouse control of the computer any more)."""

import json
from pathlib import Path

import pytest
from sergio_escritorio.hands import (
    ALIASES,
    MODES,
    Hand,
    HandControl,
    LandmarkSmoother,
    OneEuro,
    gesture,
    main_hand,
)

REAL = json.loads((Path(__file__).parent / "hand_landmarks.json").read_text())


def _hand(name, i=0):
    return Hand([tuple(p) for p in REAL[name][i]])


@pytest.mark.parametrize(
    ("photo", "expected"),
    [
        ("thumb_up", "thumbs_up"),
        ("fist", "fist"),
        ("victory", "victory"),
        ("pointing_up", "point"),
        ("right_hands", "open"),
    ],
)
def test_gestures_on_real_hands(photo, expected):
    assert gesture(REAL[photo][0]) == expected


def pinching():
    """The real pointing hand with the thumb tip brought to the index tip."""
    lm = [list(p) for p in REAL["pointing_up"][0]]
    lm[4] = [lm[8][0] + 0.005, lm[8][1] + 0.005, lm[8][2]]
    return Hand([tuple(p) for p in lm])


def test_pinch_is_not_a_fist():
    assert pinching().gesture == "pinch"
    assert gesture(REAL["fist"][0]) == "fist"


def test_real_pinch_grabs_a_hologram():
    from sergio_escritorio import holo

    hand = pinching()
    pts = holo.hand_points(hand.landmarks, 480, 270, True)
    assert holo.pinch_amount(pts) < holo.PINCH_ON
    assert (
        holo.pinch_amount(holo.hand_points(REAL["right_hands"][0], 480, 270, True))
        > holo.PINCH_OFF
    )


def test_only_holograms_and_off_remain():
    assert set(MODES) == {"off", "ver", "holo"}
    assert ALIASES["3d"] == ALIASES["fisica"] == "holo"
    hc = HandControl(frames=lambda: None, tracker_factory=lambda: None)
    hc.set_mode("gestos")
    assert hc.mode == "off"  # gesture control is gone


def test_one_euro_filter_steadies_jitter():
    f = OneEuro()
    values = [f(100 + (3 if i % 2 else -3), i / 30) for i in range(60)]
    assert max(values[30:]) - min(values[30:]) < 3  # jitter of 6 px shrinks
    fast = OneEuro()
    moved = [fast(i * 20.0, i / 30) for i in range(30)]
    assert moved[-1] > 500  # big real movements still follow


def test_holo_mode_keeps_smoothed_hands():
    hc = HandControl(frames=lambda: None)
    hc.mode = "holo"
    hc.process([pinching(), _hand("fist")], 1.0)
    assert len(hc.hands) == 2 and hc.hands[0].gesture == "pinch"


def test_unavailable_tracker_explains_and_turns_off():
    def broken():
        raise ImportError("No module named 'mediapipe'")

    hc = HandControl(frames=lambda: None, tracker_factory=broken)
    hc.set_mode("holo")
    hc._thread.join(2)
    assert hc.mode == "off" and "mediapipe" in hc.error


def test_blender_with_hands_opens_the_holograms(control_server, desktop):
    from sergio_escritorio.control import Controller

    modes = []
    c = Controller(desktop)
    c.on_hands = lambda mode: modes.append(mode) or "ok"
    c.act({"action": "blender", "script": "import bpy", "hands": True})
    kind, script = desktop.calls[-1]
    assert kind == "blender" and script == "import bpy"
    assert modes == ["holo"]
    assert c.act({"action": "hands", "target": "off"}) == "ok"


def _moved(hand, dx, dy=0.0):
    return Hand([(x + dx, y + dy, z) for x, y, z in hand.landmarks], hand.side)


def test_smoothing_takes_the_jitter_out():
    import random

    rng = random.Random(1)
    still = _hand("right_hands")
    smoother = LandmarkSmoother()
    raw_x, smooth_x = [], []
    for i in range(60):
        jitter = Hand([(x + rng.gauss(0, 0.004), y, z) for x, y, z in still.landmarks])
        raw_x.append(jitter.landmarks[8][0])
        smooth_x.append(smoother([jitter], i / 30)[0].landmarks[8][0])

    def spread(values):
        mean = sum(values) / len(values)
        return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5

    assert spread(smooth_x[10:]) < spread(raw_x[10:]) / 2


def test_the_closest_hand_leads():
    far = Hand(
        [
            (0.5 + (x - 0.5) * 0.5, 0.5 + (y - 0.5) * 0.5, z)
            for x, y, z in REAL["fist"][0]
        ]
    )
    near = _hand("victory")
    assert main_hand([far, near]) is near and main_hand([]) is None

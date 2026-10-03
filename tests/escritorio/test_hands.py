"""Hands: gestures from REAL MediaPipe landmarks (saved from photos), the air
mouse, gesture actions and the Blender stream."""

import json
import socket
from pathlib import Path

import pytest
from sergio_escritorio.hands import (
    BLENDER_BRIDGE,
    BLENDER_PORT,
    AirMouse,
    Debounce,
    Hand,
    HandControl,
    OneEuro,
    Vote,
    blender_packet,
    gesture,
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


def test_debounce_needs_a_steady_gesture():
    d = Debounce(hold=0.5)
    assert d.update("thumbs_up", 0.0) is None
    assert d.update("thumbs_up", 0.3) is None
    assert d.update("thumbs_up", 0.6) == "thumbs_up"
    assert d.update("thumbs_up", 1.5) is None  # fires once per hold
    assert d.update("none", 1.6) is None


def touching(tip):
    """The real victory hand (index and middle out) with the thumb on a tip."""
    lm = [list(p) for p in REAL["victory"][0]]
    lm[4] = [lm[tip][0] + 0.004, lm[tip][1] + 0.004, lm[tip][2]]
    return Hand([tuple(p) for p in lm])


def test_air_mouse_move_click_drag_and_clutch():
    m = AirMouse((1000, 800), smooth=False)
    point = _hand("pointing_up")
    events = m.step(point, 0.0)
    assert events[0][0] == "move" and 0 <= events[0][1] < 1000
    assert [e[0] for e in m.step(pinching(), 0.1)] == ["move"]
    assert [e[0] for e in m.step(point, 0.2)] == ["move", "click"]  # quick pinch
    m.step(pinching(), 1.0)
    assert [e[0] for e in m.step(pinching(), 1.7)] == ["move", "down"]  # held
    assert [e[0] for e in m.step(point, 1.8)] == ["move", "up"]
    assert m.step(_hand("fist"), 2.0) == []  # fist: clutch, no movement


def test_pinch_does_not_move_the_pointer():
    """The pointer follows the knuckles, so pinching does not jump it."""
    m = AirMouse((1000, 800), smooth=False)
    before = m.step(_hand("pointing_up"), 0.0)[0][1:]
    during = m.step(pinching(), 0.1)[0][1:]
    assert before == during


def test_right_click_and_scroll():
    m = AirMouse((1000, 800), smooth=False)
    # A plain pointing hand rests the thumb on the curled middle: no click.
    assert [e[0] for e in m.step(_hand("pointing_up"), 0.0)] == ["move"]
    assert [e[0] for e in m.step(touching(12), 0.1)] == ["move", "right"]
    assert [e[0] for e in m.step(touching(12), 0.2)] == ["move"]  # once
    up = [list(p) for p in REAL["victory"][0]]
    m.step(Hand([tuple(p) for p in up]), 1.0)
    lifted = [(x, y - 0.1, z) for x, y, z in up]
    events = m.step(Hand(lifted), 1.1)
    assert events and events[0][0] == "scroll" and events[0][1] > 0  # up = scroll up


def test_air_mouse_is_mirrored_and_clamped():
    m = AirMouse((1000, 800), smooth=False)
    assert m.target((0.25, 0.2)) == (999, 0)  # left of the frame = right of screen
    assert m.target((-1, 2)) == (999, 799)


def test_one_euro_filter_steadies_jitter():
    f = OneEuro()
    values = [f(100 + (3 if i % 2 else -3), i / 30) for i in range(60)]
    assert max(values[30:]) - min(values[30:]) < 3  # jitter of 6 px shrinks
    fast = OneEuro()
    moved = [fast(i * 20.0, i / 30) for i in range(30)]
    assert moved[-1] > 500  # big real movements still follow


def test_vote_ignores_single_frame_flickers():
    v = Vote(5)
    seen = [v(g) for g in ["open", "open", "fist", "open", "open"]]
    assert seen[-1] == "open" and "fist" not in seen[2:]


def test_gesture_mode_fires_actions():
    fired = []
    hc = HandControl(frames=lambda: None, on_gesture=fired.append)
    hc.mode = "gestos"
    d, m = Debounce(hold=0.5), AirMouse((100, 100))
    for t in (0.0, 0.3, 0.6, 0.9):
        hc.process([_hand("thumb_up")], t, d, m)
    assert fired == ["thumbs_up"]


def test_mouse_mode_sends_pointer_events():
    sent = []
    hc = HandControl(frames=lambda: None, mouse_events=sent.append)
    hc.mode = "mouse"
    hc.process([_hand("pointing_up")], 0.0, Debounce(), AirMouse((100, 100)))
    assert sent and sent[0][0][0] == "move"


def test_3d_mode_streams_to_blender():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        rx.bind(("127.0.0.1", BLENDER_PORT))
    except OSError:
        pytest.skip("port busy")
    rx.settimeout(2)
    hc = HandControl(frames=lambda: None)
    hc.mode = "3d"
    hc.process([pinching(), _hand("fist")], 1.0, Debounce(), AirMouse((10, 10)))
    packet = json.loads(rx.recvfrom(65536)[0])
    rx.close()
    assert [h["gesture"] for h in packet["hands"]] == ["pinch", "fist"]
    assert 0 <= packet["hands"][0]["x"] <= 1


def test_blender_packet_and_bridge_script():
    packet = blender_packet([_hand("victory")], 3.0)
    assert packet["hands"][0]["gesture"] == "victory"
    compile(BLENDER_BRIDGE, "bridge", "exec")  # valid Python for Blender
    assert str(BLENDER_PORT) in BLENDER_BRIDGE and "bpy.app.timers" in BLENDER_BRIDGE


def test_unavailable_tracker_explains_and_turns_off():
    def broken():
        raise ImportError("No module named 'mediapipe'")

    hc = HandControl(frames=lambda: None, tracker_factory=broken)
    hc.set_mode("gestos")
    hc._thread.join(2)
    assert hc.mode == "off" and "mediapipe" in hc.error


def test_blender_with_hands_appends_the_bridge(control_server, desktop):
    from sergio_escritorio.control import Controller

    modes = []
    c = Controller(desktop)
    c.on_hands = lambda mode: modes.append(mode) or "ok"
    c.act({"action": "blender", "script": "import bpy", "hands": True})
    kind, script = desktop.calls[-1]
    assert kind == "blender" and "bpy.app.timers.register" in script
    assert modes == ["3d"]
    assert c.act({"action": "hands", "target": "off"}) == "ok"

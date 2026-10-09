"""More of you, measured: hands, face (blinks, gaze, distance) and posture."""

import json
from pathlib import Path

from sergio_escritorio.body import (
    FaceStats,
    Posture,
    gaze,
    hand_summary,
    iris_distance_cm,
)
from sergio_escritorio.vision import Seen, clean_detections, hand_box

REAL = json.loads((Path(__file__).parent / "hand_landmarks.json").read_text())


def test_hand_summary_on_real_hands():
    text = hand_summary(REAL["pointing_up"][0], "Left")
    assert text.startswith("Derecha · 1 dedo · señala")
    assert hand_summary(REAL["right_hands"][0], "Right").endswith("mano abierta")


def test_your_hand_is_not_a_banana_nor_another_person_nor_a_thing():
    hand = hand_box(REAL["pointing_up"][0])
    x, y, w, h = hand
    found = [
        Seen("plátano", "objeto", "", 0.6, (x + 0.01, y + 0.02, w * 0.9, h * 0.9)),
        Seen("persona", "persona", "humano", 0.5, (x, y + h * 0.3, w * 1.1, h * 1.2)),
        Seen(
            "objeto", "objeto", "", 0.5, (x + w * 0.4, y + 0.01, w * 0.1, h * 0.3)
        ),  # a finger
        Seen("persona", "persona", "humano", 0.9, (0.0, 0.0, 1.0, 1.0)),  # you
        Seen(
            "celular", "objeto", "", 0.8, (x + w * 0.5, y + h * 0.5, w * 0.8, h * 0.6)
        ),  # held
    ]
    kept = clean_detections(found, [hand])
    assert [(k.label, k.held) for k in kept] == [("persona", False), ("celular", True)]


def test_blinks_tiredness_and_gaze():
    stats = FaceStats()
    t = 0.0
    for _ in range(12):  # 12 blinks in a minute
        stats.feed({"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9}, t)
        stats.feed({}, t + 0.15)
        t += 5
    assert 11 <= stats.last["blinks_per_min"] <= 14 and not stats.last["tired"]
    for k in range(40):  # eyes closed a long time
        stats.feed({"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9}, t + k * 0.1)
    assert stats.last["tired"] and "ojos cansados" in stats.summary()
    assert gaze({"eyeLookDownLeft": 0.8, "eyeLookDownRight": 0.8}) == "abajo"
    assert gaze({}) == "a la pantalla"


def test_distance_from_the_iris():
    pts = [(0.5, 0.5)] * 478
    pts = list(pts)
    pts[469], pts[471] = (0.50, 0.5), (0.52, 0.5)  # 2 % of a 1280 px frame
    assert 50 < iris_distance_cm(pts, 1280) < 60  # 11.7 mm iris, 25.6 px


def _pose(nose_y, knee_bend=0.0):
    lm = [(0.5, 0.5, 0.0, 1.0)] * 33
    lm = list(lm)
    lm[0] = (0.5, nose_y, 0, 1)
    lm[11], lm[12] = (0.4, 0.5, 0, 1), (0.6, 0.5, 0, 1)
    for hip, knee, ankle, x in ((23, 25, 27, 0.45), (24, 26, 28, 0.55)):
        lm[hip] = (x, 0.7, 0, 1)
        lm[knee] = (x + knee_bend, 0.8, 0, 1)
        lm[ankle] = (x, 0.9, 0, 1)
    return lm


def test_posture_and_squats():
    posture = Posture()
    posture.feed(_pose(0.30))  # upright: the baseline
    posture.feed(_pose(0.36))
    assert posture.last["slouch"] and "encorvado" in posture.summary()
    for _ in range(3):
        posture.feed(_pose(0.30, knee_bend=0.12))  # down
        posture.feed(_pose(0.30, knee_bend=0.0))  # up
    assert posture.squats == 3

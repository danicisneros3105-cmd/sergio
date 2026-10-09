"""Sergio's camera vision: species and objects, tracking, names, face mesh."""

import math
import os
from pathlib import Path

import pytest
from sergio_escritorio.vision import (
    HeadGestures,
    Seen,
    Tracker,
    expressions,
    head_angles,
    iou,
    label_es,
    summary,
)


def test_spanish_labels_and_species():
    assert label_es("person") == ("persona", "persona", "humano")
    assert label_es("dog") == ("perro", "animal", "perro")
    assert label_es("cat") == ("gato", "animal", "gato")
    assert label_es("cell phone") == ("celular", "objeto", "")
    assert label_es("cup") == ("taza", "objeto", "")


def test_iou():
    assert iou((0, 0, 1, 1), (0, 0, 1, 1)) == pytest.approx(1)
    assert iou((0, 0, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)) == 0
    assert iou((0, 0, 0.4, 0.4), (0.2, 0.2, 0.4, 0.4)) == pytest.approx(0.04 / 0.28)


def _person(x, score=0.9):
    return Seen("persona", "persona", "humano", score, (x, 0.2, 0.2, 0.6))


def test_tracks_keep_their_number_and_move_smoothly():
    t = Tracker(keep=1.0)
    first = t.update(
        [_person(0.10), Seen("perro", "animal", "perro", 0.8, (0.6, 0.5, 0.3, 0.3))],
        0.0,
    )
    ids = {tr.label: tr.id for tr in first}
    t.update(
        [_person(0.14), Seen("perro", "animal", "perro", 0.8, (0.62, 0.5, 0.3, 0.3))],
        0.2,
    )
    now = t.update(
        [_person(0.18), Seen("perro", "animal", "perro", 0.8, (0.64, 0.5, 0.3, 0.3))],
        0.4,
    )
    assert {tr.label: tr.id for tr in now} == ids  # same numbers
    person = next(tr for tr in now if tr.kind == "persona")
    assert 0.12 < person.box[0] < 0.18  # smoothed, no jumps
    assert len(t.visible(0.4)) == 2
    assert t.update([], 2.0) == []  # gone after a while


def test_one_frame_ghosts_are_hidden():
    t = Tracker()
    t.update([Seen("taza", "objeto", "", 0.5, (0.1, 0.1, 0.1, 0.1))], 0.0)
    assert t.visible(0.0) == []


def test_names_need_two_of_three_looks():
    t = Tracker()
    t.update([_person(0.1)], 0.0)
    face = {"box": (0.15, 0.25, 0.08, 0.1), "score": 0.8}
    assert t.add_faces([dict(face, name="Dani")], 0.1) == []  # one look: not yet
    person = t.tracks[0]
    assert person.name == "" and person.title(0.1) == "Persona"
    assert t.add_faces([dict(face, name="Dani")], 1.6) == ["Dani"]  # confirmed
    assert person.title(1.6) == "Dani"
    t.add_faces([dict(face, name="")], 3.0)  # a blurry look: no vote
    assert person.name == "Dani"
    t.add_faces([dict(face, name="", guest=2)], 4.5)  # clearly someone else
    assert (
        person.name == "" and person.title(4.5) == "Persona 2"
    )  # never inherits "Dani"
    t.add_faces([dict(face, name="", guest=2)], 6.0)
    assert person.name == ""


def test_each_face_goes_to_its_own_body():
    from sergio_escritorio.vision import Seen

    t = Tracker()
    big = Seen("persona", "persona", "humano", 0.9, (0.0, 0.0, 0.9, 1.0))  # Dani, close
    side = Seen(
        "persona", "persona", "humano", 0.9, (0.55, 0.1, 0.3, 0.8)
    )  # a friend behind
    for now in (0.0, 0.1):
        t.update([big, side], now)
    dani_face = {"box": (0.2, 0.1, 0.15, 0.2), "score": 0.8, "name": "Dani"}
    friend_face = {"box": (0.65, 0.15, 0.08, 0.1), "score": 0.6, "name": "", "guest": 3}
    for now in (0.2, 1.7):
        t.add_faces([dani_face, friend_face], now)
    by_box = {tr.box[0]: tr for tr in t.tracks}
    assert by_box[0.0].name == "Dani"
    assert by_box[0.55].title(1.7) == "Persona 3"  # not "Dani"


def test_strangers_get_a_number_and_faces_without_body_count():
    t = Tracker()
    t.update([], 0.0)
    t.add_faces([{"box": (0.4, 0.3, 0.2, 0.25), "name": "", "guest": 2}], 0.0)
    assert t.tracks[0].title(0.0) == "Persona 2"


def test_scene_details_attach_or_add_things():
    t = Tracker()
    t.update([Seen("perro", "animal", "perro", 0.9, (0.5, 0.5, 0.3, 0.3))] * 1, 0.0)
    t.add_scene(
        [
            {
                "box": [0.5, 0.5, 0.3, 0.3],
                "kind": "animal",
                "label": "perro",
                "detail": "corgi",
            },
            {
                "box": [0.05, 0.1, 0.1, 0.2],
                "kind": "objeto",
                "label": "guitarra",
                "detail": "acústica",
            },
        ],
        1.0,
    )
    titles = sorted(tr.title(1.0) for tr in t.tracks)
    assert titles == ["Guitarra · acústica", "Perro · corgi"]
    t.update([Seen("perro", "animal", "perro", 0.9, (0.5, 0.5, 0.3, 0.3))], 5.0)
    assert any(tr.label == "guitarra" for tr in t.tracks)  # still shown a while
    assert not any(tr.label == "guitarra" for tr in t.update([], 14.0))


def test_summary_sentence():
    t = Tracker()
    t.update(
        [
            _person(0.1),
            _person(0.5),
            Seen("perro", "animal", "perro", 0.9, (0.7, 0.6, 0.2, 0.2)),
            Seen("gato", "animal", "gato", 0.9, (0.75, 0.1, 0.1, 0.1)),
            Seen("taza", "objeto", "", 0.9, (0.3, 0.8, 0.1, 0.1)),
        ],
        0.0,
    )
    t.tracks[0].names.extend(["Dani", "Dani"])
    text = summary(t.tracks, 0.0)
    assert text.startswith("Veo Dani y una persona que no conozco")
    assert "un perro" in text and "un gato" in text and "objetos: taza" in text
    assert summary([], 0.0) == "No veo a nadie ni nada en particular."


def test_expressions_from_blendshapes():
    assert expressions({"mouthSmileLeft": 0.9, "mouthSmileRight": 0.85}) == [
        "sonriendo"
    ]
    assert "sorprendido" in expressions({"browInnerUp": 0.7, "jawOpen": 0.5})
    assert expressions({"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.1}) == ["guiño"]
    assert expressions({"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9}) == ["ojos cerrados"]
    assert expressions({}) == []


def _rot_y(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]]


def test_head_angles():
    assert head_angles([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) == (
        0,
        0,
        0,
    )
    yaw, pitch, roll = head_angles(_rot_y(25))
    assert yaw == pytest.approx(25) and abs(pitch) < 1e-6 and abs(roll) < 1e-6


def _feed(gestures, values, axis, start=0.0, step=0.1):
    said = None
    for i, v in enumerate(values):
        yaw, pitch = (v, 0.0) if axis == "yaw" else (0.0, v)
        said = gestures.feed(start + i * step, yaw, pitch) or said
    return said


def test_nod_is_yes_and_shake_is_no():
    nod = [0, 6, 13, 6, 0, 7, 14, 7, 0]
    shake = [0, -8, -15, -5, 5, 15, 5, -8, -15]
    assert _feed(HeadGestures(), nod, "pitch") == "si"
    assert _feed(HeadGestures(), shake, "yaw") == "no"
    # turning to look somewhere else is neither
    assert _feed(HeadGestures(), [0, 5, 10, 15, 20, 25, 30, 30, 30], "yaw") is None
    # small wobbles while talking are not answers
    assert _feed(HeadGestures(), [0, 3, -2, 4, -3, 2, 0], "pitch") is None


# -- with the real MediaPipe models (when installed) ---------------------------
ASSETS = Path(os.environ.get("SERGIO_TEST_ASSETS", "/tmp/claude-0"))


@pytest.mark.skipif(
    not (ASSETS / "cats_and_dogs.jpg").exists(), reason="needs test photos"
)
def test_real_detector_finds_dogs_and_cats(monkeypatch):
    pytest.importorskip("mediapipe")
    cv2 = pytest.importorskip("cv2")
    from sergio_escritorio import vision

    monkeypatch.setattr(vision, "MODELS_DIR", ASSETS)
    monkeypatch.setattr(
        vision, "ensure_model", lambda name, folder=ASSETS: ASSETS / name
    )
    finder = vision.ObjectFinder()
    found = finder.find(cv2.imread(str(ASSETS / "cats_and_dogs.jpg")))
    labels = sorted(s.label for s in found)
    assert labels.count("perro") >= 2 and labels.count("gato") >= 2
    assert all(s.kind == "animal" for s in found if s.label in ("perro", "gato"))
    person = finder.find(cv2.imread(str(ASSETS / "pose.jpg")))
    assert [s.label for s in person] == ["persona"]


@pytest.mark.skipif(not (ASSETS / "portrait.jpg").exists(), reason="needs a portrait")
def test_real_face_mesh_reads_a_smile(monkeypatch):
    pytest.importorskip("mediapipe")
    cv2 = pytest.importorskip("cv2")
    from sergio_escritorio import vision

    monkeypatch.setattr(
        vision, "ensure_model", lambda name, folder=ASSETS: ASSETS / name
    )
    faces = vision.FaceMesh().find(cv2.imread(str(ASSETS / "portrait.jpg")))
    assert len(faces) == 1 and len(faces[0].points) == 478
    assert "sonriendo" in faces[0].expressions
    assert abs(faces[0].yaw) < 20 and abs(faces[0].pitch) < 20


def test_auto_namer_asks_gemini_only_for_new_things_and_rarely():
    from sergio_escritorio.vision import AutoNamer, Seen, Tracker

    tracker = Tracker()
    namer = AutoNamer(gap=20, daily=3, settle=1.5)
    cup = Seen("taza", "objeto", "", 0.7, (0.1, 0.1, 0.2, 0.2))
    person = Seen("persona", "persona", "humano", 0.9, (0.5, 0.1, 0.3, 0.8))
    for t in (0.0, 0.2, 0.4):
        tracker.update([cup, person], t)
    assert not namer.due(tracker.visible(0.4), 0.4, day="d1")  # not settled yet
    tracker.update([cup, person], 2.0)
    assert namer.due(tracker.visible(2.0), 2.0, day="d1")
    namer.asked(tracker.visible(2.0), 2.0)
    tracker.update([cup, person], 30.0)
    assert not namer.due(tracker.visible(30.0), 30.0, day="d1")  # nothing new
    ball = Seen("pelota", "objeto", "", 0.6, (0.7, 0.7, 0.1, 0.1))
    for t in (30.0, 31.0, 32.0):
        tracker.update([cup, person, ball], t)
    assert namer.due(tracker.visible(32.0), 32.0, day="d1")
    namer.asked(tracker.visible(32.0), 32.0)
    assert not namer.due(tracker.visible(40.0), 40.0, holding=True, day="d1")  # gap
    namer._count = 3
    assert not namer.due(
        tracker.visible(80.0), 80.0, holding=True, day="d1"
    )  # daily cap
    assert namer.due(tracker.visible(80.0), 80.0, holding=True, day="d2")  # a new day


def test_object_finder_prefers_the_better_model(monkeypatch):
    from sergio_escritorio import vision

    assert vision.ObjectFinder.MODELS[0] == "efficientdet_lite2.tflite"
    assert (
        "efficientdet_lite2/float16" in vision.MODEL_URLS["efficientdet_lite2.tflite"]
    )


# -- one label per thing; unsure look-alikes are not named -------------------
def test_three_labels_on_one_lipstick_become_one_unsure_object():
    from sergio_escritorio.vision import Seen, clean_detections

    lipstick = (0.45, 0.4, 0.05, 0.16)
    found = [
        Seen("objeto", "objeto", "", 0.52, lipstick),  # "remote" below SURE
        Seen("celular", "objeto", "", 0.49, (0.448, 0.41, 0.052, 0.15)),
        Seen("silla", "objeto", "", 0.33, (0.3, 0.3, 0.4, 0.6)),  # too weak
        Seen("persona", "persona", "humano", 0.9, (0.2, 0.0, 0.6, 1.0)),
    ]
    kept = clean_detections(found)
    assert [k.label for k in kept] == ["persona", "objeto"]


def test_a_cup_on_a_laptop_stays_two_things():
    from sergio_escritorio.vision import Seen, clean_detections

    kept = clean_detections(
        [
            Seen("laptop", "objeto", "", 0.8, (0.2, 0.3, 0.5, 0.4)),
            Seen("taza", "objeto", "", 0.7, (0.3, 0.35, 0.08, 0.1)),
        ]
    )
    assert len(kept) == 2


def test_a_flickering_label_is_one_track_and_the_vote_wins():
    from sergio_escritorio.vision import Seen

    t = Tracker()
    box = (0.4, 0.4, 0.1, 0.1)
    for i, label in enumerate(["celular", "control remoto", "celular", "celular"]):
        t.update([Seen(label, "objeto", "", 0.7, box)], i * 0.1)
    (track,) = t.visible(0.3)
    assert track.label == "celular" and track.hits == 4


def test_gemini_names_the_held_thing_and_it_sticks():
    from sergio_escritorio.vision import AutoNamer, Seen

    t = Tracker()
    for i in range(3):
        t.update([Seen("objeto", "objeto", "", 0.55, (0.4, 0.4, 0.05, 0.15))], i * 0.5)
    (track,) = t.visible(1.0)
    assert track.title(1.0) == "Objeto"
    namer = AutoNamer()
    assert namer.due([track], 2.0) and namer.pick([track], 2.0) is track
    namer.tried(track)
    assert namer.pick([track], 2.1) is None  # one close-up per thing
    assert t.name_track(track.id, "Labial", "rojo, metálico")
    t.update([Seen("celular", "objeto", "", 0.6, (0.4, 0.4, 0.05, 0.15))], 1.5)
    assert t.visible(1.5)[0].title(1.5) == "Labial · rojo, metálico"


def test_close_up_crop_stays_in_the_frame():
    from sergio_escritorio.vision import crop_box

    x, y, w, h = crop_box((0.95, 0.9, 0.04, 0.08))
    assert 0 <= x and 0 <= y and x + w <= 1.0001 and y + h <= 1.0001
    assert w >= 0.18 and h >= 0.18


def test_open_vocabulary_names_need_to_be_sure_unless_in_your_hand():
    from sergio_escritorio.vision import Seen, vocab_sure

    hand = (0.4, 0.4, 0.2, 0.2)
    lipstick = Seen("labial", "objeto", "", 0.45, (0.45, 0.45, 0.05, 0.08))
    assert vocab_sure(lipstick, [hand])  # held: what YOLOE is for
    assert not vocab_sure(lipstick)  # a "lipstick" on a smile across the room: no
    assert not vocab_sure(Seen("anillo", "objeto", "", 0.79, (0.1, 0.1, 0.05, 0.05)))
    assert vocab_sure(Seen("lámpara", "objeto", "", 0.6, (0.1, 0.1, 0.2, 0.2)))
    assert vocab_sure(Seen("sombrero", "objeto", "", 0.9, (0.1, 0.1, 0.2, 0.2)))


def test_clean_view_shows_people_held_and_named_things_only():
    from sergio_escritorio.vision import Seen, Tracker, salient

    t = Tracker()
    seen = [
        Seen("persona", "persona", "humano", 0.9, (0.3, 0.1, 0.4, 0.9)),
        Seen("taza", "objeto", "", 0.8, (0.45, 0.5, 0.05, 0.06), held=True),
        Seen("objeto", "objeto", "", 0.6, (0.8, 0.8, 0.05, 0.05)),
        Seen("silla", "objeto", "", 0.9, (0.0, 0.5, 0.3, 0.5)),
        Seen("botella", "objeto", "", 0.9, (0.75, 0.2, 0.04, 0.1)),
    ]
    for now in (0.0, 0.1):
        t.update(seen, now)
    shown = {tr.title(0.1, clean=True) for tr in salient(t.visible(0.1), clean=True)}
    assert shown == {"Persona", "Taza · en tu mano"}
    assert len(salient(t.visible(0.1))) > len(shown)  # the detailed view shows more


def test_vision_moves_to_the_cpu_when_the_card_has_no_kernels():
    from sergio_escritorio import vision

    calls = []

    class Model:
        def predict(self, frame, **kw):
            calls.append(kw["device"])
            if kw["device"] != "cpu":
                raise RuntimeError(
                    "CUDA error: no kernel image is available for execution"
                )

            class Boxes:
                cls = conf = xyxyn = type("T", (), {"tolist": lambda self: []})()

            return [type("R", (), {"names": {}, "boxes": Boxes()})()]

    finder = vision.YoloFinder.__new__(vision.YoloFinder)
    finder._model, finder._device, finder._half, finder.gpu = Model(), 0, True, True
    finder._size, finder._score, finder._vocab, finder.model = (
        640,
        0.4,
        None,
        "yolo11m.pt (GPU)",
    )
    assert finder.find(object()) == []
    assert finder.find(object()) == []
    assert calls == [0, "cpu", "cpu"]
    assert finder.model == "yolo11m.pt (CPU)" and finder._half is False


def test_cuda_works_is_false_without_a_usable_card():
    from sergio_escritorio import vision

    assert vision.gpu_broken(RuntimeError("CUDA error: no kernel image is available"))
    assert not vision.gpu_broken(ValueError("bad frame"))
    assert vision.cuda_works() in (True, False)  # never raises


def test_a_sure_face_is_named_on_the_first_look_and_settles():
    """Naming used to take two looks 1.5 s apart; a strong match is enough."""
    t = Tracker()
    t.update([_person(0.1)], 0.0)
    face = {"box": (0.15, 0.25, 0.08, 0.1), "score": 0.71}
    assert t.add_faces([dict(face, name="Dani", strong=True, owner=True)], 0.1) == [
        "Dani"
    ]
    person = t.tracks[0]
    assert person.name == "Dani" and person.settled and person.owner
    assert person.named_at == 0.1
    # a stranger needs two clear looks before the analysis is "done"
    t2 = Tracker()
    t2.update([_person(0.1)], 0.0)
    t2.add_faces([dict(face, name="", guest=1)], 0.1)
    assert not t2.tracks[0].settled
    t2.add_faces([dict(face, name="", guest=1)], 0.35)
    assert t2.tracks[0].settled and t2.tracks[0].name == "" and not t2.tracks[0].owner


def test_face_watcher_looks_fast_until_everyone_is_named():
    pytest.importorskip("PySide6")
    from sergio_escritorio.camera import FaceWatcher

    w = FaceWatcher(lambda: None, lambda _jpeg: [], interval=1.5, fast=0.25, empty=0.6)
    assert w.wait() == 0.6  # nobody: keep an eye out
    w.faces = [{"name": "", "score": 0.3}]
    assert w.wait() == 0.25  # someone unnamed: look again quickly
    w.faces = [{"name": "Dani", "score": 0.8}]
    assert w.wait() == 1.5  # all known: relax
    w.poke()
    assert w._wake.is_set()

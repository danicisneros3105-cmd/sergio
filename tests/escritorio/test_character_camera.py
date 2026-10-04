"""Muse-style character, living companion and the "Sergio ve" window (Qt)."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qt():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(str(exc))
    return QApplication.instance() or QApplication([])


def test_every_look_and_mood_draws(qt):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QImage, QPainter
    from sergio_escritorio import character as ch

    img = QImage(120, 120, QImage.Format.Format_ARGB32)
    try:
        for style in ch.STYLES:
            for accessory in ch.ACCESSORIES:
                for eye in ch.EYE_STYLES:
                    ch.set_look(
                        style=style, accessory=accessory, eye_style=eye, mouth="sonrisa"
                    )
                    for mood in ("", "happy", "sleep", "curious", "surprised"):
                        for state in (
                            "idle",
                            "listening",
                            "thinking",
                            "speaking",
                            "paused",
                        ):
                            img.fill(QColor(0, 0, 0, 0))
                            p = QPainter(img)
                            ch.draw_character(
                                p,
                                QPointF(60, 60),
                                30,
                                state,
                                1.3,
                                level=0.4,
                                mood=mood,
                                squash=1.1,
                            )
                            p.end()
    finally:
        ch.apply_config(
            {
                "theme": "Océano",
                "eyes": True,
                "style": "orbe",
                "mouth": "ninguna",
                "accessory": "ninguno",
                "eye_style": "ovalos",
            }
        )


def test_set_look_ignores_unknown_values():
    pytest.importorskip("PySide6")
    from sergio_escritorio import character as ch

    before = dict(ch.SETTINGS)
    ch.set_look(style="dragon", body="no-es-color", accessory="capa", mouth="?")
    assert ch.SETTINGS == before
    ch.set_look(body="#ff0000")
    assert ch.SETTINGS["body"] == "#ff0000"
    ch.SETTINGS.update(before)


def test_companion_sleeps_wakes_smiles_and_hops(qt, monkeypatch):
    from sergio_escritorio import companion as comp

    c = comp.Companion(follow=False)
    now = c._last_move + comp.SLEEP_AFTER + 1
    assert c.life(now)[0] == "sleep"
    c._wake()  # mouse moved
    mood, squash, hop = c.life(c._bounce_at + 0.15)
    assert mood == "" and hop > 0 and squash != 1.0  # woke up with a hop
    c.set_state("speaking")
    c.set_state("idle")
    assert c.life(c._happy_until - 1)[0] == "happy"  # smiles after answering
    c.point_at(100, 100, "Aquí", physical=False)
    assert c.life(c._target_until - 1)[0] == "curious"
    c.set_state("listening")
    c.set_level(0.8)
    assert not c.grab().isNull()


class Feed:
    keep_on = False
    error = ""

    def __init__(self):
        import numpy as np

        self.f = np.full((480, 640, 3), 90, np.uint8)

    def start(self):
        pass

    def frame(self):
        return self.f.copy()


def test_camera_window_has_no_buttons_and_shows_holograms(qt, tmp_path, monkeypatch):
    pytest.importorskip("cv2")

    from sergio_escritorio import camera

    monkeypatch.setattr(camera.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(camera, "detect_faces", lambda frame: [(10, 10, 50, 50)])
    w = camera.CameraWindow(Feed())
    w.open()
    w._ticks = 4
    w._tick()
    assert w._faces == [(10, 10, 50, 50)]
    assert not hasattr(w, "button_rects")  # the toolbar is gone

    class Hands:
        mode = "off"
        hands = []

        def set_mode(self, mode):
            self.mode = mode

    w.hands = Hands()
    assert "Creé 1 cubo" in w.hologram("crea un cubo rojo")
    assert w.hands.mode == "holo" and len(w.holo.objects) == 1
    w.grab()  # paints once so the hands map onto the picture
    w._tick()
    assert w.holo.view == (w.card().width(), w.card().height())
    image = w.grab().toImage()
    assert not image.isNull()
    w.mirror = False
    path = w.save_photo()
    assert path.endswith(".jpg") and os.path.exists(path)
    assert "Foto guardada" in w.overlay
    w.close_camera()
    assert w.hands.mode == "off"


def test_face_detector_runs_on_a_blank_frame():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    pytest.importorskip("PySide6")
    from sergio_escritorio.camera import detect_faces

    assert detect_faces(np.zeros((480, 640, 3), np.uint8)) == []

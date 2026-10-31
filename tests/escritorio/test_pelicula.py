"""Owner, 1 Nov 2026: «debe darte imágenes de lo que está haciendo»."""

import io

from PIL import Image
from sergio_escritorio.operador import Operator
from sergio_escritorio.pelicula import MAX_FRAMES, Film, thumbnail


def _png(w=1920, h=1080):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 120, 220)).save(buf, "PNG")
    return buf.getvalue()


def test_a_screen_becomes_a_small_jpeg():
    import base64

    small = Image.open(io.BytesIO(base64.b64decode(thumbnail(_png()))))
    assert small.format == "JPEG" and small.width == 480
    assert thumbnail(b"not an image") == ""


def test_the_film_keeps_the_last_frames_and_sends_only_new_ones():
    film = Film(clock=lambda: 1.0)
    film.start("buscar en Amazon")
    for i in range(MAX_FRAMES + 3):
        film.frame(b"x", f"paso {i}")
    data = film.to_dict()
    assert data["state"] == "working" and len(data["frames"]) == MAX_FRAMES
    last = data["frames"][-1]["n"]
    assert film.to_dict(since=last)["frames"] == []
    film.end("done", "Hecho.")
    assert film.to_dict()["state"] == "done"


class _Controller:
    enabled = True

    def __init__(self):
        self.backend = object()
        self.done = []

    def snapshot(self):
        return _png(320, 200), [], 1.0

    def act(self, action):
        self.done.append(action)
        return "ok"


def test_every_operator_step_leaves_a_picture_and_a_line():
    steps = iter(
        [
            {"action": "click", "x": 10, "y": 10, "say": "Abro el buscador"},
            {"action": "type", "text": "audífonos"},
            {"action": "done", "say": "Listo."},
        ]
    )
    op = Operator(_Controller(), lambda *a: next(steps), sleep=lambda s: None)
    out = op.run("busca audífonos en Amazon")
    film = op.film.to_dict()
    assert out.startswith("Hecho") and film["state"] == "done"
    assert [f["caption"] for f in film["frames"]] == [
        "Abro el buscador",
        "typed 'audífonos'",
        "Listo.",
    ]
    assert all(f["jpeg_b64"] for f in film["frames"])


def test_a_game_project_is_unpacked_and_opened_and_never_writes_outside(tmp_path):
    import io
    import zipfile

    import pytest
    from sergio_escritorio import creator_apps

    good = tmp_path / "Juego.zip"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("Juego/Juego.uproject", "{}")
    opened = []
    msg = creator_apps.open_unreal_project(good, starter=opened.append)
    assert opened and opened[0].endswith("Juego.uproject") and "Unreal" in msg
    bad = tmp_path / "Malo.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../fuera.txt", "x")
    bad.write_bytes(buf.getvalue())
    with pytest.raises(ValueError):
        creator_apps.unpack_project(bad)
    assert not (tmp_path / "fuera.txt").exists()

"""Effects in stereo that land on the cut, and pictures checked before they are used."""

from __future__ import annotations

import io
import wave

import numpy as np

from openjarvis.video_essay import assets, audio


def _side(x):
    left, right = x[:, 0], x[:, 1]
    return float(np.abs(left - right).mean() / (np.abs(left + right).mean() + 1e-9))


def test_new_effects_are_clean():
    for name in ("subdrop", "reverse", "glitch", "shutter", "swipe"):
        x = audio.EFFECTS[name]()
        assert np.isfinite(x).all() and 0.2 < np.abs(x).max() <= 1.0, name


def test_effects_in_stereo_move_and_land_on_the_cut():
    fx = audio.effects_stereo(
        [(1.0, "whoosh"), (3.0, "whoosh"), (5.0, "impact"), (7.0, "riser")], 9.0
    )
    assert fx.shape == (9 * audio.SR, 2) and np.abs(fx).max() <= 1.0

    # the whoosh crosses: from the left before the cut to the right after it (the next one the other way)
    def lr(a, b):
        part = fx[int(a * audio.SR) : int(b * audio.SR)]
        return np.abs(part[:, 0]).mean(), np.abs(part[:, 1]).mean()

    left, right = lr(0.8, 0.95)
    assert left > 1.5 * right
    left, right = lr(1.05, 1.2)
    assert right > 1.5 * left
    left, right = lr(2.8, 2.95)
    assert right > 1.5 * left
    # its loudest moment is the cut (within 40 ms)
    env = np.abs(fx[int(0.5 * audio.SR) : int(1.5 * audio.SR)]).sum(axis=1)
    w = int(0.01 * audio.SR)
    env = np.convolve(env, np.ones(w) / w, mode="same")
    assert abs(0.5 + np.argmax(env) / audio.SR - 1.0) < 0.04
    # the hit: punch in the centre, its tail around you; it starts on the cut
    hit = fx[int(5.0 * audio.SR) - int(0.02 * audio.SR) : int(5.9 * audio.SR)]
    assert np.abs(fx[int(4.9 * audio.SR) : int(4.98 * audio.SR)]).max() < 0.02
    assert _side(hit[: int(0.03 * audio.SR)]) < 0.05 < _side(hit[int(0.3 * audio.SR) :])
    # the riser ends on its cut
    assert np.abs(fx[int(6.9 * audio.SR) : int(6.99 * audio.SR)]).max() > 0.1
    assert np.abs(fx[int(7.05 * audio.SR) : int(7.3 * audio.SR)]).max() < 0.02


def test_stereo_wav():
    data = audio.write_wav(audio.effects_stereo([(0.5, "pop")], 1.0))
    with wave.open(io.BytesIO(data)) as w:
        assert w.getnchannels() == 2 and w.getnframes() == audio.SR
    assert len(audio.read_wav(data)) == audio.SR  # read back as mono still works


def _png(rgb):
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(rgb.astype("uint8")).save(buf, "PNG")
    return buf.getvalue()


def _good():
    y, x = np.mgrid[0:256, 0:256]
    base = np.stack([x * 0.4 + 40, x * 0.35 + 40, x * 0.3 + 50], -1)
    base[60:200, 150:220] = (225, 190, 150)  # a subject on the right third
    return _png(base)


def test_picture_check():
    points, fixes = assets.picture_check(_good())
    assert points == 100 and fixes == []
    flat = _png(np.full((256, 256, 3), 128))
    points, fixes = assets.picture_check(flat)
    assert points < 100 and any("contrast" in f for f in fixes)
    blown = _png(
        np.where(np.arange(256)[None, :, None] > 100, 255, 30) * np.ones((256, 256, 3))
    )
    assert any("highlights" in f for f in assets.picture_check(blown)[1])
    assert assets.picture_check(b"not a picture") == (100, [])


def test_a_cheap_picture_is_made_again_once(tmp_path, monkeypatch):
    monkeypatch.delenv("SERGIO_IMAGEN_REVISION", raising=False)
    asked = []

    def make(prompt):
        asked.append(prompt)
        return _png(np.full((256, 256, 3), 128)) if len(asked) == 1 else _good()

    path = assets.generated("a lighthouse at dusk", tmp_path / "x", make)
    assert len(asked) == 2 and "Fix:" in asked[1] and "Composition" in asked[0]
    assert assets.picture_check(open(path, "rb").read())[0] == 100

    asked.clear()  # the budget says no: the first one stays
    assets.generated("a lighthouse at dusk", tmp_path / "y", make, retry=lambda: False)
    assert len(asked) == 1

    asked.clear()
    monkeypatch.setenv("SERGIO_IMAGEN_REVISION", "0")
    assets.generated("a lighthouse at dusk", tmp_path / "z", make)
    assert len(asked) == 1

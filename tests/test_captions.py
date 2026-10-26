"""Captions that move (video_essay/captions.py) and the quick video using them."""

from __future__ import annotations

import io
import shutil
import subprocess

import pytest

from openjarvis.video_essay import captions


def test_words_take_time_by_length_and_fill_the_sentence():
    timed = captions.word_times("Hola extraordinario", 1.0, 2.0)
    assert timed[0][1] == 1.0 and timed[-1][2] == pytest.approx(3.0)
    assert (timed[1][2] - timed[1][1]) > (timed[0][2] - timed[0][1])
    assert (
        captions.word_times("", 0, 2) == [] and captions.word_times("a b", 0, 0) == []
    )


def test_chunks_are_short_and_end_at_punctuation():
    timed = captions.word_times("Uno dos, tres cuatro cinco seis.", 0, 3)
    groups = [[w for w, _s, _e in c] for c in captions.chunks(timed)]
    assert groups == [["Uno", "dos,"], ["tres", "cuatro", "cinco"], ["seis."]]


def test_the_word_being_said_lights_up_and_never_one_long_line():
    doc = captions.ass_document(["Mira cómo se mueven las palabras."], [3.0], 720, 1280)
    events = [line for line in doc.splitlines() if line.startswith("Dialogue:")]
    assert len(events) == 6  # one slice per word
    assert all(captions.ACCENT in e for e in events)
    assert all(
        len(e.split(",,")[-1].replace(captions.ACCENT, "").split()) <= 6 for e in events
    )
    assert "\\t(0,90" in events[0]  # the chunk pops in
    assert "{" not in captions._escape("a{b}c")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_quick_video_burns_the_animated_captions(tmp_path):
    from PIL import Image

    from openjarvis.tools.video_create import render

    pics = []
    for colour in ((20, 60, 120), (120, 40, 40)):
        buf = io.BytesIO()
        Image.new("RGB", (640, 360), colour).save(buf, "JPEG")
        pics.append(buf.getvalue())
    out = render(
        pics,
        ["Hola, esto es Sergio.", "Palabras que se mueven."],
        [1.5, 1.5],
        tmp_path / "v.mp4",
    )
    assert out.stat().st_size > 1000
    frame = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.8", "-i", str(out), "-frames:v", "1", str(frame)],
                   check=True)  # fmt: skip
    img = Image.open(frame).convert("RGB")
    # The lit word is yellow somewhere in the lower part of the picture.
    w, h = img.size
    yellow = sum(
        1
        for x in range(0, w, 2)
        for y in range(h // 2, h, 2)
        if (lambda p: p[0] > 200 and p[1] > 170 and p[2] < 90)(img.getpixel((x, y)))
    )
    assert yellow > 20

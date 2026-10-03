"""Utterance detection and the 'Sergio' wake word."""

import numpy as np
import pytest
from sergio_escritorio.listen import FRAME, Segmenter, parse_wake


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Sergio, abre Spotify.", (True, "abre Spotify")),
        ("oye sergio ¿qué hora es?", (True, "qué hora es")),
        ("Hey, Sergio: escribe ñandú", (True, "escribe ñandú")),
        ("Cergio pon música", (True, "pon música")),
        ("Sergió", (True, "")),
        ("Le dije a Sergio que viniera", (False, "")),
        ("sergeant pepper", (False, "")),
        ("", (False, "")),
    ],
)
def test_parse_wake(text, expected):
    assert parse_wake(text) == expected


def _tone(seconds, amp, rng=None):
    n = int(16000 * seconds)
    if rng is not None:
        return (rng.normal(0, amp, n)).clip(-32000, 32000).astype(np.int16).tobytes()
    t = np.arange(n) / 16000
    return (amp * np.sin(2 * np.pi * 180 * t)).astype(np.int16).tobytes()


def _run(seg, raw):
    step = FRAME * 2
    out = []
    for i in range(0, len(raw) - step + 1, step):
        u = seg.feed(raw[i : i + step])
        if u:
            out.append(u)
    return out


def test_two_sentences_in_a_noisy_room():
    rng = np.random.default_rng(1)
    seg = Segmenter()
    raw = (
        _tone(1.5, 150, rng)  # fan noise: learn the floor
        + _tone(1.2, 5000)
        + _tone(1.0, 150, rng)
        + _tone(0.8, 5000)
        + _tone(1.0, 150, rng)
    )
    utterances = _run(seg, raw)
    assert len(utterances) == 2
    seconds = [len(u) / 2 / 16000 for u in utterances]
    assert 1.2 < seconds[0] < 2.4 and 0.8 < seconds[1] < 2.0  # speech + pre-roll + tail


def test_short_clicks_are_not_speech_and_long_talk_is_cut():
    seg = Segmenter(max_seconds=3.0)
    assert _run(seg, _tone(0.05, 8000) + _tone(1.0, 50)) == []
    long = _run(seg, _tone(5.0, 5000))
    assert long and len(long[0]) / 2 / 16000 <= 3.1


def test_steady_loud_noise_is_learned_and_dropped_but_speech_still_heard():
    rng = np.random.default_rng(2)
    seg = Segmenter(max_seconds=2.0)
    assert _run(seg, _tone(3.0, 900, rng)) == []  # loud steady TV: dropped
    assert seg.threshold() > 1500
    assert _run(seg, _tone(1.0, 900, rng)) == []
    spoken = _run(seg, _tone(0.8, 9000) + _tone(1.0, 900, rng))
    assert len(spoken) == 1

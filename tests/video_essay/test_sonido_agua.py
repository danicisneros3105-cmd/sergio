"""«El sonido de los videos parece bajo el agua»: the music had no highs, the
voice was up-sampled by linear interpolation and denoised for noise it never had."""

from __future__ import annotations

import numpy as np

from openjarvis.video_essay import audio, pro

SR = audio.SR


def _octaves(sig):
    sp = np.abs(np.fft.rfft(sig)) ** 2
    f = np.fft.rfftfreq(len(sig), 1 / SR)
    edges = [62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
    e = [sp[(f >= a) & (f < b)].sum() for a, b in zip(edges, edges[1:])]
    return {a: 10 * np.log10(max(x, 1e-12) / max(e)) for a, x in zip(edges, e)}


def test_the_music_has_mids_and_highs_not_just_a_low_wash():
    for mood in audio.MOODS:
        m = audio.music_bed(20.0, mood=mood)
        o = _octaves(m)
        assert o[1000] > -22 and o[2000] > -28, (
            mood,
            o,
        )  # the old bed was at -60 and below
        assert o[4000] > -32 and o[8000] > -34, (mood, o)  # hats, plucks and snare
        assert 0.4 < float(np.abs(m).max()) <= 0.61 and np.isfinite(m).all()


def test_the_beat_follows_the_asked_tempo_and_the_drums_come_in_late():
    m = audio.music_bed(30.0, bpm=120, mood="calm")
    assert len(m) == 30 * SR
    first, last = m[: 8 * SR], m[-8 * SR :]
    assert np.abs(last).mean() > 1.05 * np.abs(first).mean()  # it builds


def test_resampling_keeps_the_voice_band_and_adds_no_images():
    sr = 24000
    t = np.arange(sr) / sr
    x = (np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 9000 * t)).astype(
        np.float32
    )
    y = audio.resample(x, sr, SR)
    assert len(y) == SR
    sp = np.abs(np.fft.rfft(y))
    f = np.fft.rfftfreq(len(y), 1 / SR)
    nine = sp[np.argmin(abs(f - 9000))]
    four = sp[np.argmin(abs(f - 440))]
    assert (
        nine / four > 0.45
    )  # linear interpolation kept about 0.7 of it and added images
    assert sp[(f > 13000)].max() / four < 0.01  # nothing above the original band
    assert np.allclose(audio.resample(x, sr, sr), x)


def test_the_narration_chain_does_not_denoise_a_clean_voice():
    assert not any(f.startswith("afftdn") for f in pro.VOICE_FILTERS)
    assert any(f.startswith("highshelf") for f in pro.VOICE_FILTERS)

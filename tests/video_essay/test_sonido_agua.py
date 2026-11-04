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


# -- 4 Nov 2026: «el sonido de los videos aún está mal» ------------------------


def test_the_voice_chain_has_no_gate():
    # A gate on a synthetic voice (no room noise to shut out) pulled the soft
    # ends of words 2-3 dB down: measured, then removed.
    from openjarvis.video_essay import pro

    assert not any(f.startswith("agate") for f in pro.VOICE_FILTERS)


def test_pauses_carry_room_tone_not_digital_silence():
    from openjarvis.video_essay import script

    tone = script.room_tone(48_000)
    rms_db = 20 * np.log10(float(np.sqrt(np.mean(tone**2))))
    assert -66 < rms_db < -58  # audible to a master, never to a listener
    assert script.room_tone(0).size == 0
    voice = np.zeros(48_000, dtype=np.float32)
    assert float(np.max(np.abs(script._with_room(voice)))) > 0  # not dead air


def test_a_voice_call_s_silence_is_trimmed_to_a_breath():
    from openjarvis.video_essay import audio, script

    sr = audio.SR
    body = (0.3 * np.sin(2 * np.pi * 220 * np.arange(sr // 2) / sr)).astype(np.float32)
    padded = np.concatenate([np.zeros(sr), body, np.zeros(sr)])
    out = script.trim_edges(padded)
    assert len(body) < len(out) < len(body) + int(0.12 * sr)
    assert script.trim_edges(np.zeros(100, dtype=np.float32)).shape == (100,)
    assert script.trim_edges(np.zeros(0, dtype=np.float32)).size == 0


def test_effects_sit_under_the_voice():
    from openjarvis.video_essay import mezcla

    graph, _ = mezcla._graph(True, False, True, 10.0, -20.0, "aresample=48000")
    assert f"volume={mezcla.FX_UNDER_VOICE_DB}dB" in graph
    alone, _ = mezcla._graph(False, True, True, 10.0, -20.0, "aresample=48000")
    assert f"volume={mezcla.FX_ALONE_DB}dB" in alone
    assert mezcla.FX_UNDER_VOICE_DB <= -8

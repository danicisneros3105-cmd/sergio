"""The measured Shorts formats, the clip-rights review and the music cues."""

from __future__ import annotations

import numpy as np

from openjarvis.video_essay import derechos, montaje, viral


def test_formats_are_picked_from_the_idea():
    assert viral.pick("cosas raras pero legales en un avión") == "lista-de-datos-raros"
    assert (
        viral.pick("la historia de una estafa en la escuela")
        == "mini-historia-con-giro"
    )
    assert viral.pick("ranking de los saltos más locos") == "ranking-sin-narrador"
    assert viral.pick("lo que sea", genre="animacion") == "animacion-musical"


def test_the_guide_carries_real_measures_and_the_music_map():
    note = viral.guide("datos raros de los cruceros")
    assert (
        note.startswith("<shorts_virales")
        and "1.8 M vistas" in note
        and "3.0 palabras" in note
    )
    assert "silencio" in note and "SAY = SHOW" in note
    assert viral.guide("un documental largo", vertical=False) == ""


def test_every_reference_number_is_whole_and_every_format_has_proof():
    for r in viral.REFERENCIAS:
        assert int(r["vistas"]) > 0 and 0 < int(r["segundos"]) < 600
    for key in (
        "lista-de-datos-raros",
        "mini-historia-con-giro",
        "ranking-sin-narrador",
        "animacion-musical",
    ):
        assert viral.evidence(key), key
    assert "Las cinco referencias ya fueron descargadas" in viral.report()


def test_clip_review_never_says_legal():
    none = derechos.review([], narrated=True)
    assert none["riesgo"] == "ninguno" and derechos.line(none) == ""
    low = derechos.review(
        [
            {"film": "Rocky (1976)", "seconds": 3},
            {"film": "Rocky (1976)", "seconds": 4},
        ],
        True,
    )
    assert low["riesgo"] == "bajo"
    high = derechos.review([{"film": "Rocky (1976)", "seconds": 9}] * 3, narrated=False)
    assert high["riesgo"] == "alto" and len(high["avisos"]) == 3
    text = derechos.line(high).lower()
    assert "reclamo" in text and "legal" not in text and "seguro" not in text
    assert (
        derechos.review([{"film": "Sintel", "seconds": 30, "free": True}], False)[
            "riesgo"
        ]
        == "ninguno"
    )


def test_music_cues_hook_silence_and_drop():
    sr = 1000
    shots = [(1.0, "whoosh"), (2.0, ""), (1.0, "silencio"), (1.0, "drop")]
    g = montaje.music_cues(shots, 5.0, sr)
    assert len(g) == 5 * sr
    assert abs(np.median(g[100:900]) - 0.25) < 1e-4  # the hook speaks first
    assert abs(np.median(g[1200:2900]) - 1.0) < 1e-4
    assert g[3100:3900].max() < 0.05  # out before the payoff
    assert abs(np.median(g[4100:4900]) - 1.5) < 1e-4

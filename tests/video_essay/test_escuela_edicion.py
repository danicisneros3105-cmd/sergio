"""Telling the four channels' editing apart: zooms, punch-ins, kinds of shot,
the rhythm curve, cuts on sound hits and pauses."""

from __future__ import annotations

import numpy as np

from openjarvis.video_essay import escuela as e


def _scene(h=54, w=96, seed=1):
    rng = np.random.default_rng(seed)
    g = rng.random((h, w)).astype("float32") * 0.2 + 0.4
    g[15:40, 30:70] += 0.3  # something in the middle
    return np.clip(g, 0, 1)


def test_a_push_in_is_found_and_a_still_is_not():
    a = _scene()
    assert e.scale_between(a, a) == 1.0
    assert e.scale_between(a, e._zoomed(a, 1.06)) == 1.06
    assert e.scale_between(e._zoomed(a, 1.06), a) == 0.94


def test_a_punch_in_cut_is_the_same_picture_closer():
    a = _scene()
    assert e.punch_in(a, e._zoomed(a, 1.3))
    assert not e.punch_in(a, _scene(seed=7))  # a real cut to another picture


def test_kinds_of_shot():
    flat = np.zeros((54, 96, 3), dtype="uint8")
    flat[:, :48] = (230, 200, 60)
    flat[:, 48:] = (40, 90, 200)
    filmed = (np.random.default_rng(3).random((54, 96, 3)) * 255).astype("uint8")
    assert e.flatness(flat) > 0.9 and e.flatness(filmed) < 0.1
    assert e.kind_of_shot(flat, 0, {}) == "grafico"
    assert e.kind_of_shot(flat, 0, {"centro": 0.3}) == "texto"
    assert e.kind_of_shot(filmed, 1, {}) == "cara"
    assert e.kind_of_shot(filmed, 0, {}) == "real"


def test_rhythm_hits_and_pauses():
    assert e.rhythm([1, 2, 9.5], 10, parts=10) == [0, 1, 1, 0, 0, 0, 0, 0, 0, 1]
    assert e.on_hits([1.0, 2.0, 3.0], [1.05, 2.5]) == 0.33
    words = [{"t": 0}, {"t": 0.4}, {"t": 2.0}, {"t": 2.3}, {"t": 4.0}]
    assert e.silences(words, 60) == 2


def test_the_grammar_line_names_the_edit():
    vlog = {"planos": {"cara": 0.6, "real": 0.4, "texto": 0, "grafico": 0}, "toma_mediana_s": 2.1,
            "punch_ins_por_min": 4, "cortes_en_golpe": 0.5}  # fmt: skip
    line = e.editing_type(vlog)
    assert (
        line.startswith("a cámara")
        and "acercamientos de golpe" in line
        and "golpes de sonido" in line
    )
    anim = {"planos": {"grafico": 0.9}, "toma_mediana_s": 0.9, "texto_en_pantalla": 0.8}
    assert e.editing_type(anim).startswith(
        "animación"
    ) and "muy rápidos" in e.editing_type(anim)
    rules = e.rules_from_numbers({**vlog, "toma_mediana_s": 2.1, "cortes_por_segundo": 0.5, "cortes_primeros_3s": 2,
                                  "duracion_s": 600, "tipo_de_edicion": line,
                                  "ritmo_por_tramo": [1, 0.5, 0.5, 0.4, 0.4, 0.5, 0.6, 0.8, 1, 1.4]})  # fmt: skip
    text = "\n".join(rules)
    assert (
        "Editing grammar" in text
        and "punch-ins" in text
        and "fastest in tenth 10" in text
    )


def test_compare_lists_the_studied_categories(tmp_path):
    import json

    d = tmp_path / "superskills" / "reto-narrado"
    d.mkdir(parents=True)
    (d / "medido.json").write_text(
        json.dumps({"tipo_de_edicion": "a cámara", "toma_mediana_s": 2.1, "videos": 20})
    )
    rows = e.compare(["reto-narrado", "shorts-animados"], root=tmp_path)
    assert len(rows) == 1 and rows[0]["categoria"] == "reto-narrado"
    assert (
        rows[0]["tipo"] == "a cámara"
        and rows[0]["toma_s"] == 2.1
        and rows[0]["videos"] == 20
    )

"""The school: every second measured by code, one superskill per category."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from openjarvis.video_essay import escuela

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sin ffmpeg")


def _video(path: Path) -> Path:
    """6 s vertical: cuts at 1.5, 2.5 and 4.5 s, a click every second."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "color=red:s=180x320:d=1.5", "-f", "lavfi", "-i", "color=blue:s=180x320:d=1",
         "-f", "lavfi", "-i", "color=green:s=180x320:d=2", "-f", "lavfi", "-i", "color=white:s=180x320:d=1.5",
         "-f", "lavfi", "-i",
         "aevalsrc='0.02*sin(2*PI*220*t)+if(lt(mod(t\\,1)\\,0.03)\\,0.9*sin(2*PI*1500*t)\\,0)':d=6:s=8000",
         "-filter_complex", "[0][1][2][3]concat=n=4:v=1:a=0[v]", "-map", "[v]", "-map", "4", "-shortest",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    return path


def test_links_are_cleaned_and_deduplicated(tmp_path):
    refs = escuela.references()
    shorts = refs["shorts-virales"]["links"]
    assert len(shorts) == len(set(shorts)) == 14
    assert all(
        refs[k]["fps"] == 32
        for k in ("shorts-virales", "animacion", "explicativo-entretenido")
    )
    assert "https://www.youtube.com/watch?v=7sKAk3sAAmc" in shorts
    assert "https://www.youtube.com/watch?v=p7LDk4D3Q3U" in refs["animacion"]["links"]
    assert escuela.clean_link("https://www.instagram.com/reels/DdjwUyxBc5k/?hl=es") == (
        "https://www.instagram.com/reel/DdjwUyxBc5k/"
    )


@needs_ffmpeg
def test_every_second_is_measured(tmp_path):
    m = escuela.measure(
        _video(tmp_path / "v.mp4"),
        words=[{"t": 0.2, "w": "Nadie"}, {"t": 0.6, "w": "sabe"}],
    )
    assert m["cortes"] == [1.5, 2.5, 4.5]
    assert m["tomas"] == [1.5, 1.0, 2.0, 1.5]
    assert [s["golpes"] for s in m["segundos"]] == [1] * 6
    assert len(m["fotogramas"]) == 24
    assert m["fotogramas"][6]["t"] == 1.5
    assert m["fotogramas"][6]["corte"]
    assert not m["fotogramas"][5]["corte"]
    assert m["fotogramas"][0]["volumen_db"] < 0
    r = m["resumen"]
    assert (
        r["vertical"] and r["cortes_primeros_3s"] == 2 and r["gancho"] == "Nadie sabe"
    )
    assert r["movimiento_medio"] == 0.0
    assert r["intervalo_fotograma_s"] == 0.25
    json.dumps(m)  # NumPy comparisons must not leak into the saved study.


def test_transcription_uses_cpu_and_returns_json_numbers(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import numpy as np

    class FakeModel:
        def __init__(self, *args, **kwargs):
            assert kwargs["device"] == "cpu"

        def transcribe(self, *args, **kwargs):
            segment = SimpleNamespace(
                words=[SimpleNamespace(start=np.float64(0.25), word=" Hola")]
            )
            return [segment], None

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)
    escuela._whisper_model.cache_clear()
    words, status = escuela.transcribe_detailed(tmp_path / "v.mp4")
    assert status == "ok" and words == [{"t": 0.25, "w": "Hola"}]
    json.dumps(words)
    escuela._whisper_model.cache_clear()


def test_youtube_vtt_supplies_word_times_before_whisper(tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    video.with_suffix(".en.vtt").write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHola <00:00:00.250>mundo\n",
        "utf-8",
    )
    words, status = escuela.transcribe_detailed(video)
    assert status == "subtitulos_youtube"
    assert words == [{"t": 0.0, "w": "Hola"}, {"t": 0.25, "w": "mundo"}]


@needs_ffmpeg
def test_study_synthesize_and_guide(tmp_path, monkeypatch):
    monkeypatch.setattr(escuela, "home", lambda: tmp_path / "escuela")
    monkeypatch.setattr(
        "openjarvis.video_essay.style.learned_dir", lambda: tmp_path / "estilos"
    )
    video = _video(tmp_path / "v.mp4")
    shots = {"summary": "ranking of crazy moments", "shots": [{"t": 0, "dur": 1.5, "visual": "clip", "effect": "zoom"}],
             "typography": {"fonts": "bold"}, "recurring_effects": ["punch-in zoom"]}  # fmt: skip
    data = escuela.study("https://www.youtube.com/watch?v=abcdefghijk", "shorts-virales",
                         watcher=lambda p: shots, fetch=lambda url, d: video)  # fmt: skip
    assert data["medido"]["resumen"]["tomas"] == 4 and data["tomas_modelo"]["summary"]
    rules = "\n".join(
        f"{i}. Rule number {i} measured from the data." for i in range(1, 9)
    )
    res = escuela.synthesize("shorts-virales", ask=lambda p: rules)
    assert res["por"].startswith("modelo") and res["reglas"][0].startswith(
        "Editing grammar"
    )
    assert sum(1 for r in res["reglas"] if r.startswith("Rule number")) == 8
    prof = json.loads((tmp_path / "estilos" / "ref-shorts-virales.json").read_text())
    assert (
        prof["median_shot_s"] == 1.5
        and prof["aspect"] == "9:16"
        and "punch-in zoom" in prof["effects"]
    )
    assert res["cerebro"]["entrenado"]
    text = escuela.guidance("un ranking de momentos locos", "pesada")
    assert "OWNER'S REFERENCE SUPERSKILL" in text and "Rule number 3" in text


def test_rules_by_code_carry_the_numbers():
    m = {"toma_mediana_s": 0.9, "cortes_por_segundo": 1.1, "cortes_primeros_3s": 4, "duracion_s": 31,
         "texto_en_pantalla": 0.8, "texto_donde": "centro", "golpes_por_segundo": 1.4,
         "palabras_por_segundo": 3.2, "caras": 0.6, "vertical": True}  # fmt: skip
    text = " ".join(escuela.rules_from_numbers(m))
    assert (
        "0.9 s" in text
        and "4 cuts in the first 3 seconds" in text
        and "in the middle" in text
    )


def test_no_superskill_no_guidance(tmp_path, monkeypatch):
    monkeypatch.setattr(escuela, "home", lambda: tmp_path)
    assert escuela.guidance("algo", "pesada") == ""


def test_owner_adds_links(tmp_path, monkeypatch):
    monkeypatch.setattr(escuela, "home", lambda: tmp_path)
    r = escuela.add(
        ["https://youtu.be/abcdefghijk", "no es un enlace"], "Mis favoritos"
    )
    assert r == {"categoria": "mis-favoritos", "agregados": 1}
    assert escuela.references()["mis-favoritos"]["links"] == [
        "https://www.youtube.com/watch?v=abcdefghijk"
    ]


def _studied(root: Path) -> None:
    """A studied reference: 6 s vertical, cuts at 1.5/2.5/4.5, text at the bottom of second 2."""
    secs = [{"t": t, "cortes": 0, "brillo": 0.5, "color": 0.3, "principal": "#ffffff", "movimiento": 0.1,
             "caras": 0, "texto": {"arriba": 0.0, "centro": 0.0, "abajo": 0.3 if t == 2 else 0.0},
             "volumen_db": -20, "golpes": 1, "palabras": 2, "dice": "hola"} for t in range(6)]  # fmt: skip
    data = {
        "url": "https://www.youtube.com/watch?v=abcdefghijk",
        "categoria": "shorts-virales",
        "medido": {"cortes": [1.5, 2.5, 4.5], "tomas": [1.5, 1.0, 2.0, 1.5], "segundos": secs,
                   "fotogramas": [{"i": 0, "t": 0.0, "corte": False}, {"i": 32, "t": 1.0, "corte": True}],
                   "resumen": {"duracion_s": 6.0, "vertical": True, "tomas": 4, "toma_mediana_s": 1.5,
                               "cortes_primeros_3s": 2, "texto_en_pantalla": 0.17, "texto_donde": "abajo",
                               "golpes_por_segundo": 1.0, "palabras_por_segundo": 2.0, "gancho": "Nadie sabe esto",
                               "fps_medido": 32, "fps": 24, "fotogramas_muestreados": 192,
                               "intervalo_fotograma_s": 0.03125}},
        "tomas_modelo": {"shots": [{"t": 2.5, "dur": 2.0, "effect": "zoom", "transition_in": "whip", "sfx": "whoosh"}]},
    }  # fmt: skip
    (root / "shorts-virales").mkdir(parents=True)
    (root / "shorts-virales" / "abcdefghijk.json").write_text(json.dumps(data))


def test_blueprint_scales_and_recut_follows_it(tmp_path):
    from openjarvis.video_essay import plan as P

    _studied(tmp_path)
    bp = escuela.blueprint("https://youtube.com/shorts/abcdefghijk", 12, root=tmp_path)
    assert [t["desde"] for t in bp["tomas"]] == [0.0, 3.0, 5.0, 9.0] and bp[
        "aspect"
    ] == "9:16"
    assert bp["tomas"][1]["posicion"] == "lower" and bp["tomas"][2]["efecto"] == "zoom"
    words = [
        P.Word(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(24)
    ]  # 12 s of speech
    shots = [
        P.Shot(first=0, last=12, visual="city"),
        P.Shot(first=12, last=24, visual="sea"),
    ]
    for s in shots:
        P._times(s, words)
    out = escuela.recut(shots, words, bp)
    assert [round(s.start, 1) for s in out] == [0.0, 3.0, 5.0, 9.0]
    assert (
        out[1].position == "lower"
        and out[2].effect == "zoom"
        and out[2].transition == "whip"
    )
    assert (
        out[0].visual == "city" and out[3].visual == "sea"
    )  # what the editor chose to show stays
    note = escuela.blueprint_note(bp)
    assert "RECREATE THIS EDIT EXACTLY" in note and "4 shots in 12" in note


def test_ficha_tells_every_second(tmp_path):
    _studied(tmp_path)
    text = escuela.ficha("abcdefghijk", root=tmp_path)
    assert "6.0 s, vertical" in text and "Gancho (0-3 s): «Nadie sabe esto»" in text
    assert "2s · texto abajo · 1 golpes · «hola»" in text and "efecto: zoom" in text
    assert "192 fotogramas a 32 FPS" in text


def test_frame_ficha_returns_a_bounded_json_timeline(tmp_path):
    _studied(tmp_path)
    data = json.loads(escuela.frame_ficha("abcdefghijk", 0.5, 1.5, root=tmp_path))
    assert data["fps_analisis"] == 32
    assert data["fotogramas"] == [{"i": 32, "t": 1.0, "corte": True}]
    with pytest.raises(ValueError, match="60 segundos"):
        escuela.frame_ficha("abcdefghijk", 0, 61, root=tmp_path)


def test_unknown_reference_says_to_study_first(tmp_path):
    with pytest.raises(RuntimeError, match="estudia las referencias"):
        escuela.find("zzzzzzzzzzz", root=tmp_path)

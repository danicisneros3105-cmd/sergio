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
    assert len(shorts) == len(set(shorts)) == 9  # tFiLRzIjvM4 was twice
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
    r = m["resumen"]
    assert (
        r["vertical"] and r["cortes_primeros_3s"] == 2 and r["gancho"] == "Nadie sabe"
    )
    assert r["movimiento_medio"] == 0.0  # a cut is not motion


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
    assert res["por"].startswith("modelo") and len(res["reglas"]) == 8
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

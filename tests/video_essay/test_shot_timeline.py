"""A shot plan and its preview agree, and a stale study is not a new measurement."""

import json
import shutil
import subprocess

import pytest

from openjarvis.video_essay import escuela, plan, planear


def test_shots_respect_frame_budget_and_keep_animation_direction():
    doc = planear.clean_plan(
        {
            "tomas": [
                None,
                {"segundos": float("inf"), "funcion": "gancho"},
                {"segundos": 0.8, "animacion": "Gira hasta mostrar el mecanismo"},
                {"segundos": 2, "funcion": "cierre"},
            ]
        },
        4.1,
    )
    a, b, c = doc["tomas"]
    assert a["inicio_fotograma"] == 0
    assert a["fin_fotograma"] == b["inicio_fotograma"]
    assert b["fin_fotograma"] == c["inicio_fotograma"]
    assert c["fin_fotograma"] == doc["fotogramas"] == 123
    assert b["animacion"] == "Gira hasta mostrar el mecanismo"
    with pytest.raises(ValueError, match="no cubren"):
        planear.clean_plan({"tomas": [{"segundos": 2}]}, 45)


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg and ffprobe required",
)
def test_animatic_uses_the_same_30_fps_timeline(tmp_path):
    doc = planear.clean_plan(
        {
            "tomas": [
                {"segundos": 1.23, "movimiento": "push in"},
                {"segundos": 0.67, "movimiento": "pan izquierda"},
            ]
        },
        1.9,
    )
    out = planear.animatic(
        doc, tmp_path / "animatic.mp4", vertical=True, ffmpeg="ffmpeg"
    )
    streams = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate,nb_frames,width,height",
                "-of",
                "json",
                str(out),
            ]
        )
    )["streams"]
    assert streams == [
        {"r_frame_rate": "30/1", "nb_frames": "57", "width": 720, "height": 1280}
    ]
    measured = escuela.measure(out, words=[], fps=30)
    assert measured["resumen"]["fps_medido"] == 30


def test_explainer_reference_is_remeasured_before_cache_reuse(tmp_path, monkeypatch):
    cat = escuela.references()["explicativo-entretenido"]
    assert cat["fps"] == 30 and len(cat["links"]) == 5
    url = cat["links"][0]
    assert "/p/" in url
    target = tmp_path / "explicativo-entretenido" / f"{escuela.video_id(url)}.json"
    target.parent.mkdir()
    target.write_text(json.dumps({"medido": {"resumen": {"fps_medido": 4}}}))
    with pytest.raises(RuntimeError, match="Todavía no estudié"):
        escuela.find(url, root=tmp_path)
    calls = []

    def measure(_, *, fps):
        calls.append(fps)
        return {"resumen": {"fps_medido": fps}}

    monkeypatch.setattr(escuela, "measure", measure)
    kwargs = {
        "root": tmp_path,
        "fetch": lambda *_: tmp_path / "source.mp4",
        "watcher": lambda _: {},
    }
    escuela.study(url, "explicativo-entretenido", fps=30, **kwargs)
    escuela.study(url, "explicativo-entretenido", fps=30, **kwargs)
    assert escuela.find(url, root=tmp_path)["medido"]["resumen"]["fps_medido"] == 30
    assert calls == [30]


def test_animation_fallback_does_not_add_archive_cards():
    words = [plan.Word(f"Plano {i}.", i, i + 0.8) for i in range(6)]
    shots = plan.plan_shots(words, {"production": "3d"}, sources=["3d"])
    assert all(
        s.kind == "broll" and s.source == "3d" and s.frame == "none" for s in shots
    )
    assert len({s.camera for s in shots}) > 1

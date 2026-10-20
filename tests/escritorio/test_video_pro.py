"""Video Pro's render: cuts, cross fades, captions, loudness, music ducking."""

from pathlib import Path

from sergio_escritorio.quick import parse_quick
from sergio_escritorio.video_pro import FADE, render_command


def test_render_command_for_a_plan():
    plan = {
        "aspect": "9:16",
        "title_overlay": "Prueba",
        "segments": [
            {"clip": 0, "start": 1, "end": 3.5, "caption": "Hola"},
            {"clip": 1, "start": 0.5, "end": 3, "caption": ""},
        ],
    }
    cmd = render_command(
        [Path("a.mp4"), Path("b.mp4")],
        plan,
        Path("o.mp4"),
        has_audio=[True, False],
        music="m.mp3",
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert (
        "crop=1080:1920" in graph
        and f"xfade=transition=fade:duration={FADE}:offset=2.150" in graph
    )
    assert (
        "loudnorm=I=-14" in graph
        and "sidechaincompress" in graph
        and "text='Hola'" in graph
    )
    assert "[2:a]atrim=start=0:end=2.5" in graph  # silent clip: silence of its length
    assert cmd[-1] == "o.mp4"


def test_video_orders():
    q = parse_quick("edita un video con la carpeta Viaje para YouTube Shorts")
    assert q.kind == "video_pro" and q.say == "viaje"
    assert parse_quick("súbelo a YouTube").kind == "video_upload"
    assert parse_quick("en blender hazme una casa low poly").kind == "blender_task"


def test_the_video_is_tagged_rec709_and_hdr_clips_are_tone_mapped():
    plan = {
        "segments": [
            {"clip": 0, "start": 0, "end": 2},
            {"clip": 1, "start": 0, "end": 2},
        ]
    }
    cmd = render_command(
        [Path("a.mp4"), Path("b.mov")],
        plan,
        Path("o.mp4"),
        has_audio=[True, True],
        hdr=[False, True],
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert (
        cmd[cmd.index("-color_trc") + 1] == "bt709"
        and cmd[cmd.index("-colorspace") + 1] == "bt709"
    )
    first, second = graph.split("[v0]")[0], graph.split(";")[2]
    assert "tonemap" not in first and "tonemap=hable" in second


def test_the_pipeline_runs_sources_cut_and_finishing_in_order(tmp_path, monkeypatch):
    from sergio_escritorio import video_master, video_pro

    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.jpg").write_bytes(b"x")
    (tmp_path / "notas.txt").write_text("no")
    seen = {}

    def prepare(folder, clips, *, silences, log):
        seen["sources"] = [c.name for c in clips]
        seen["silences"] = silences
        log("fuentes listas")
        return [folder / "a.mp4", folder / "b-foto.mp4"]

    def edit(source, request, planner, *, music="", clips=None):
        seen["clips"] = [c.name for c in clips]
        return {"path": str(tmp_path / "corte.mp4"), "plan": {"segments": [1, 2]}}

    def finish(video, opts, *, grade, log):
        seen["opts"] = opts
        return {"master": str(tmp_path / "corte-master.mov"), "master_label": "DNxHR"}

    monkeypatch.setattr(video_master, "prepare_sources", prepare)
    monkeypatch.setattr(video_pro, "edit", edit)
    monkeypatch.setattr(video_master, "finish", finish)
    steps = []
    done = video_master.pipeline(
        str(tmp_path),
        "quita los silencios y pásalo a 60 fps, máster prores",
        planner=lambda *a: {},
        opts={"master": "dnxhr", "lut": ""},
        log=steps.append,
    )
    assert seen["sources"] == ["a.mp4", "b.jpg"] and seen["silences"] is True
    assert seen["clips"] == ["a.mp4", "b-foto.mp4"]
    assert (
        seen["opts"]["fps"] == 60 and seen["opts"]["master"] == "dnxhr"
    )  # explicit wins
    assert done["master_label"] == "DNxHR" and steps[0] == "fuentes listas"


def test_the_pipeline_refuses_an_unknown_master_and_an_empty_folder(tmp_path):
    import pytest
    from sergio_escritorio import video_master

    with pytest.raises(ValueError, match="Máster desconocido"):
        video_master.pipeline(
            str(tmp_path), "x", planner=lambda *a: {}, opts={"master": "mpeg1"}
        )
    with pytest.raises(RuntimeError, match="No encontré"):
        video_master.pipeline(str(tmp_path), "x", planner=lambda *a: {})

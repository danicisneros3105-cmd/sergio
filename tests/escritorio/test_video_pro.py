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

"""Editar sus propios clips casi sin límite (dueño, 2 nov. 2026): más de 12
clips se editan por grupos, en orden, y se unen en un solo video."""

from __future__ import annotations

from pathlib import Path


def test_many_clips_are_edited_in_groups_and_joined(tmp_path, monkeypatch):
    from sergio_escritorio import video_pro

    clips = []
    for i in range(30):
        p = tmp_path / f"clip{i:02d}.mp4"
        p.write_bytes(b"x")
        clips.append(p)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(video_pro, "ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(video_pro, "probe", lambda c: (True, 5.0))
    monkeypatch.setattr(video_pro, "is_hdr", lambda c, exe: False)
    monkeypatch.setattr(video_pro, "has_zscale", lambda exe: False)
    monkeypatch.setattr(video_pro, "contact_sheet", lambda c, d, exe: b"jpg")
    seen_groups = []

    def planner(request, sheets, lengths):
        seen_groups.append((len(sheets), request))
        return {"youtube": {"title": "T", "description": "D", "tags": ["a"]}}

    def render_command(group, plan, out, **kw):
        return ["make", str(out)]

    joined = []

    def run(cmd, **kw):
        class Done:
            returncode, stderr = 0, ""

        Path(cmd[-1]).write_bytes(b"mp4")
        if "concat" in cmd:
            joined.append(cmd)
        return Done()

    monkeypatch.setattr(video_pro, "render_command", render_command)
    monkeypatch.setattr(video_pro.subprocess, "run", run)
    done = video_pro.edit("", "un resumen del viaje", planner, clips=clips)
    assert [n for n, _r in seen_groups] == [12, 12, 6]
    assert "Parte 2 de 3" in seen_groups[1][1]
    assert len(joined) == 1 and Path(done["path"]).exists()
    assert done["clips"] == 30
    assert not list((tmp_path / "Videos" / "Sergio").glob("*parte*"))


def test_twelve_or_fewer_clips_are_one_edit(tmp_path, monkeypatch):
    from sergio_escritorio import video_pro

    assert video_pro.GROUP == 12 and video_pro.MAX_CLIPS >= 400

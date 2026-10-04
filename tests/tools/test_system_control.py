"""Tests for system-control command building (pure functions, no execution)."""

from openjarvis.tools.system_control import _ffmpeg_cmd


class TestFfmpegCmd:
    def test_cut(self):
        cmd = _ffmpeg_cmd("cortar", ["in.mp4"], "out.mp4", start="00:01:00",
                          end="00:02:00")
        assert cmd[:2] == ["ffmpeg", "-y"]
        assert "-ss" in cmd and "00:01:00" in cmd
        assert "-to" in cmd and "00:02:00" in cmd
        assert cmd[-1] == "out.mp4"

    def test_concat(self):
        cmd = _ffmpeg_cmd("unir", ["lista.txt"], "out.mp4")
        assert "concat" in cmd
        assert "-c" in cmd and "copy" in cmd

    def test_style_filter_applied(self):
        cmd = _ffmpeg_cmd("estilo", ["in.mp4"], "out.mp4", style="cinematico")
        joined = " ".join(cmd)
        assert "-vf" in cmd and "vignette" in joined

    def test_unknown_style_ignored(self):
        cmd = _ffmpeg_cmd("estilo", ["in.mp4"], "out.mp4", style="inexistente")
        assert "-vf" not in cmd

    def test_text_overlay_escaped(self):
        cmd = _ffmpeg_cmd("estilo", ["in.mp4"], "out.mp4", text="Hola: qué tal")
        joined = " ".join(cmd)
        assert "drawtext" in joined
        assert "Hola\\:" in joined  # colons escaped for ffmpeg filter syntax

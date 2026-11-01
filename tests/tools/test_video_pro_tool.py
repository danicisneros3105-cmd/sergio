"""The agents' professional video edit calls the desktop's video_pro skill."""

from openjarvis.tools.desktop_tools import VideoProTool


def test_video_pro_sends_the_brief_and_reports_every_deliverable(monkeypatch):
    tool = VideoProTool()
    sent = {}

    def call(method, path, **kw):
        sent.update(method=method, path=path, **kw)
        return {
            "ok": True,
            "result": {
                "path": "C:/Videos/Sergio/video-pro.mp4",
                "title": "Mi viaje",
                "segments": 9,
                "aspect": "9:16",
                "master": "C:/Videos/Sergio/video-pro-master.mov",
                "master_label": "Apple ProRes 422 HQ, 10 bits",
                "steps": ["silencios quitados de a.mp4"],
            },
        }

    monkeypatch.setattr(tool, "_call", call)
    result = tool.execute(
        source="Viaje", request="Reel enérgico", aspect="9:16", master="prores", lut=""
    )
    assert sent["path"] == "/skill" and sent["json"]["name"] == "video_pro"
    assert sent["json"]["args"] == {
        "source": "Viaje",
        "request": "Reel enérgico",
        "aspect": "9:16",
        "master": "prores",
    }
    assert (
        result.success
        and "ProRes" in result.content
        and "face_approval" in result.content
    )
    assert (
        "video_pro" in tool.spec.name and tool.spec.timeout_seconds == 6 * 3600
    )  # long edits of his own clips


def test_video_pro_reports_a_failure_plainly(monkeypatch):
    tool = VideoProTool()

    def call(*_a, **_k):
        raise RuntimeError("ffmpeg falló")

    monkeypatch.setattr(tool, "_call", call)
    result = tool.execute(source="x", request="y")
    assert not result.success and "ffmpeg falló" in result.content

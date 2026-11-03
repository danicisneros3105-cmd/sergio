"""A video the browser cannot play is converted, and the page is told."""

from __future__ import annotations

import shutil
import subprocess
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.creator import routes, studio
from openjarvis.server.auth_middleware import _OPEN_MEDIA
from openjarvis.tools.video_create import ffmpeg_exe

pytestmark = pytest.mark.skipif(not ffmpeg_exe(), reason="needs ffmpeg")

NAME = "video-" + "ab" * 12 + ".mp4"


def _clip(path, codec):
    args = {
        "h264": ["-c:v", "libx264", "-pix_fmt", "yuv420p"],
        "hevc10": ["-c:v", "libx265", "-pix_fmt", "yuv420p10le"],
    }[codec]
    subprocess.run(
        [ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i",
         "testsrc=d=1:s=160x120:r=12", *args, str(path)],
        check=True, capture_output=True,
    )  # fmt: skip


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "projects_root", lambda root=None: tmp_path)
    (tmp_path / "videos").mkdir(exist_ok=True)
    routes._WEB_JOBS.clear()
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_a_normal_video_plays_as_it_is(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    _clip(tmp_path / "videos" / NAME, "h264")
    got = c.get(f"/v1/creator/video-listo/{NAME}").json()
    assert got == {"estado": "listo", "url": f"/v1/creator/media/{NAME}"}


def test_a_10_bit_master_is_converted_then_served(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    _clip(tmp_path / "videos" / NAME, "hevc10")
    assert routes.web_playable(tmp_path / "videos" / NAME) is False
    first = c.get(f"/v1/creator/video-listo/{NAME}").json()
    assert first["estado"] in ("preparando", "listo")
    for _ in range(100):
        got = c.get(f"/v1/creator/video-listo/{NAME}").json()
        if got["estado"] != "preparando":
            break
        time.sleep(0.3)
    assert got == {"estado": "listo", "url": f"/v1/creator/reproducir/{NAME}"}
    assert routes.web_playable(tmp_path / ".web" / NAME) is True
    r = c.get(got["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"


def test_the_copy_is_only_open_for_the_player_by_its_random_name():
    assert _OPEN_MEDIA.fullmatch(f"/v1/creator/reproducir/{NAME}")
    assert not _OPEN_MEDIA.fullmatch("/v1/creator/reproducir/x.mp4")
    assert not _OPEN_MEDIA.fullmatch(f"/v1/creator/video-listo/{NAME}")


def test_bad_or_missing_names(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/v1/creator/video-listo/..%2Fx.mp4").status_code in (400, 404)
    assert c.get(f"/v1/creator/video-listo/{NAME}").status_code == 404
    assert c.get(f"/v1/creator/reproducir/{NAME}").status_code == 404


def test_tools_present():
    assert shutil.which("ffmpeg") or ffmpeg_exe()

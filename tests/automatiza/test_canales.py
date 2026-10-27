"""Channels: uploads through the official APIs, the daily cap, Shorts, the
Instagram flow, replies only when he approves, and automatic posting once."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openjarvis.automatiza import canales


class Resp:
    def __init__(self, data=None, headers=None, status=200):
        self._data = data if data is not None else {}
        self.headers = headers or {}
        self.status_code = status
        self.text = json.dumps(self._data)

    def json(self):
        return self._data


class FakeHttp:
    """Answers like YouTube and Instagram; remembers every call."""

    def __init__(self, ig_states=("IN_PROGRESS", "FINISHED"), comment_status=200):
        self.calls = []
        self.ig_states = list(ig_states)
        self.comment_status = comment_status

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        if url == canales.YT_TOKEN:
            return Resp({"access_token": "tok", "expires_in": 3600})
        if url == canales.YT_UPLOAD:
            return Resp(headers={"location": "https://upload.example/session"})
        if url.endswith("/comments"):
            return Resp({"id": "r1"}, status=self.comment_status)
        if url.endswith("/media"):
            return Resp({"id": "container1"})
        if url.endswith("/media_publish"):
            return Resp({"id": "reel1"})
        raise AssertionError(url)

    def put(self, url, **kw):
        self.calls.append(("PUT", url, kw))
        return Resp({"id": "vid123", "status": {"privacyStatus": "private"}})

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        if "container1" in url:
            return Resp({"status_code": self.ig_states.pop(0)})
        return Resp({"username": "mi_canal"})


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SERGIO_PUBLIC_URL", "https://sergio.example")
    monkeypatch.delenv("SERGIO_PUBLICAR_DIA", raising=False)
    return tmp_path


def _video(tmp_path: Path) -> Path:
    v = tmp_path / "v.mp4"
    v.write_bytes(b"\x00" * 64)
    return v


def test_accounts_are_sealed_on_disk(home):
    canales.save_account("youtube", {"refresh_token": "SECRETO-123"}, home)
    raw = (home / "canales" / "youtube.json").read_text()
    assert "SECRETO-123" not in raw
    assert canales.account("youtube", home)["refresh_token"] == "SECRETO-123"
    assert canales.forget("youtube", home) and canales.account("youtube", home) == {}


def test_a_short_goes_up_with_the_tag_and_counts_for_the_day(home, tmp_path):
    canales.save_account("youtube", {"refresh_token": "r"}, home)
    http = FakeHttp()
    out = canales.youtube_upload(
        _video(tmp_path), "Datos raros", "desc", short=True, home=home, http=http
    )
    assert out["id"] == "vid123" and out["short"] is True
    body = json.loads(
        next(kw["content"] for m, u, kw in http.calls if u == canales.YT_UPLOAD)
    )
    assert body["snippet"]["title"].endswith("#Shorts")
    assert body["status"]["containsSyntheticMedia"] is True
    assert canales.account("youtube", home)["subidos_hoy"] == 1


def test_the_daily_cap_stops_the_next_upload(home, tmp_path, monkeypatch):
    monkeypatch.setenv("SERGIO_PUBLICAR_DIA", "1")
    canales.save_account("youtube", {"refresh_token": "r"}, home)
    canales.youtube_upload(_video(tmp_path), "Uno", "", home=home, http=FakeHttp())
    with pytest.raises(RuntimeError, match="SERGIO_PUBLICAR_DIA"):
        canales.youtube_upload(_video(tmp_path), "Dos", "", home=home, http=FakeHttp())


def test_is_short_only_for_vertical_and_short():
    assert canales.is_short("9:16", 59)
    assert not canales.is_short("16:9", 59)
    assert not canales.is_short("9:16", 600)


def test_instagram_reel_waits_for_processing_then_publishes(home, tmp_path):
    canales.save_account("instagram", {"user_id": "42", "token": "t"}, home)
    http = FakeHttp()
    waits = []
    out = canales.instagram_publish(
        _video(tmp_path), "texto", home=home, http=http, wait=waits.append
    )
    assert out == {"canal": "instagram", "id": "reel1"}
    assert waits == [15]  # one wait while «IN_PROGRESS»
    link = next(
        kw["data"]["video_url"] for m, u, kw in http.calls if u.endswith("/media")
    )
    token = link.rsplit("/", 1)[1]
    assert (
        canales.take_shared(token) is not None and canales.take_shared(token) is None
    )  # once


def test_instagram_needs_a_public_https_link(home, tmp_path, monkeypatch):
    monkeypatch.setenv("SERGIO_PUBLIC_URL", "http://insecure")
    canales.save_account("instagram", {"user_id": "42", "token": "t"}, home)
    with pytest.raises(RuntimeError, match="https"):
        canales.instagram_publish(_video(tmp_path), "x", home=home, http=FakeHttp())


def test_replies_are_drafted_and_only_approved_ones_are_sent(home):
    comments = [{"id": "c1", "texto": "¡Genial!"}, {"id": "c2", "texto": "¿Fuente?"}]
    replies = [
        {"id": "c1", "reply": "¡Gracias!"},
        {"id": "c2", "reply": "En la descripción."},
        {"id": "zz", "reply": "inventado"},
    ]

    def ask(p, **k):
        return json.dumps({"replies": replies})

    drafts = canales.draft_replies(comments, ask=ask, home=home)
    assert [d["id"] for d in drafts] == ["c1", "c2"]  # nothing invented
    canales.save_account("youtube", {"refresh_token": "r"}, home)
    http = FakeHttp()
    assert canales.send_replies(["c2"], home=home, http=http) == 1
    sent = [
        kw["json"]["snippet"]["parentId"]
        for m, u, kw in http.calls
        if u.endswith("/comments")
    ]
    assert sent == ["c2"]
    assert [d["id"] for d in canales.pending_replies(home)] == ["c1"]


def test_a_refused_reply_stays_pending(home):
    canales.draft_replies(
        [{"id": "c1", "texto": "hola"}],
        ask=lambda p, **k: json.dumps({"replies": [{"id": "c1", "reply": "hola"}]}),
        home=home,
    )
    canales.save_account("youtube", {"refresh_token": "r"}, home)
    assert (
        canales.send_replies(["c1"], home=home, http=FakeHttp(comment_status=403)) == 0
    )
    assert [d["id"] for d in canales.pending_replies(home)] == ["c1"]


def _finished_job(home, root, auto=True, where=("youtube", "instagram")):
    from openjarvis.video_essay import job as jobs
    from openjarvis.video_essay import schedule

    item = schedule.add(
        "datos curiosos", every_hours=6, publish_to=list(where), auto=auto, home=home
    )
    j = jobs.create({"brief": "x"}, root)
    video = root / "final.mp4"
    video.write_bytes(b"\x00")
    j.update(
        status="listo",
        result={
            "path": str(video),
            "package": {"title": "T", "description": "D", "tags": ["a b"]},
        },
    )
    items = schedule.load(home)
    items[0]["hechos"] = [j.id]
    schedule._save(items, home)
    return item, j


def test_auto_schedules_post_once_and_manual_ones_wait(home, tmp_path):
    root = tmp_path / "jobs"
    root.mkdir()
    _, j = _finished_job(home, root)
    calls = []
    ups = {
        "youtube": lambda *a, **k: calls.append("yt") or {"id": "y"},
        "instagram": lambda *a, **k: calls.append("ig") or {"id": "i"},
    }
    canales.post_ready(home, root, ups)
    canales.post_ready(home, root, ups)  # second pass: already posted
    assert calls == ["yt", "ig"]
    assert j.state()["publicado"]["youtube"] == {"id": "y"}

    home2 = tmp_path / "h2"
    home2.mkdir()
    root2 = tmp_path / "jobs2"
    root2.mkdir()
    _finished_job(home2, root2, auto=False)
    assert canales.post_ready(home2, root2, ups) == []  # waits for his «Publicar»


def test_a_failed_channel_is_retried_without_reposting_the_other(home, tmp_path):
    root = tmp_path / "jobs"
    root.mkdir()
    _, j = _finished_job(home, root)
    calls = []
    fail = {"on": True}

    def ig(*a, **k):
        calls.append("ig")
        if fail["on"]:
            raise RuntimeError("Instagram caído")
        return {"id": "i"}

    ups = {
        "youtube": lambda *a, **k: calls.append("yt") or {"id": "y"},
        "instagram": ig,
    }
    canales.post_ready(home, root, ups)
    assert "error" in j.state()["publicacion_error"]["instagram"]
    fail["on"] = False
    canales.post_ready(home, root, ups)
    assert calls == ["yt", "ig", "ig"]  # YouTube got it once
    assert j.state()["publicado"]["instagram"] == {"id": "i"}

"""Three trending videos for a brief, one per creator, and the choice saved."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from openjarvis.automatiza import canales
from openjarvis.video_essay import inspiracion


class _R:
    def __init__(self, data=None, content=b""):
        self._data = data or {}
        self.content = content

    def json(self):
        return self._data


def _ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


SEARCH = {"items": [{"id": {"videoId": v}} for v in ("a1", "a2", "a3", "a4")]}
STATS = {
    "items": [
        {"id": "a1", "snippet": {"title": "Receta de pasta en 30 segundos", "channelTitle": "Cocina Rápida",
                                 "publishedAt": _ago(10), "thumbnails": {"high": {"url": "https://i.ytimg.com/a1.jpg"}}},
         "statistics": {"viewCount": "2000000", "likeCount": "90000"}, "contentDetails": {"duration": "PT32S"}},
        {"id": "a2", "snippet": {"title": "Pasta cremosa receta fácil", "channelTitle": "Cocina Rápida",
                                 "publishedAt": _ago(5), "thumbnails": {"high": {"url": "https://i.ytimg.com/a2.jpg"}}},
         "statistics": {"viewCount": "1500000"}, "contentDetails": {"duration": "PT45S"}},
        {"id": "a3", "snippet": {"title": "Pasta receta italiana de la abuela", "channelTitle": "Nonna",
                                 "publishedAt": _ago(30), "thumbnails": {"high": {"url": "https://i.ytimg.com/a3.jpg"}}},
         "statistics": {"viewCount": "800000"}, "contentDetails": {"duration": "PT58S"}},
        {"id": "a4", "snippet": {"title": "Unboxing de un teléfono", "channelTitle": "Tech",
                                 "publishedAt": _ago(2), "thumbnails": {"high": {"url": "https://i.ytimg.com/a4.jpg"}}},
         "statistics": {"viewCount": "900000"}, "contentDetails": {"duration": "PT40S"}},
    ]
}  # fmt: skip
IG_MEDIA = {
    "data": [
        {"id": "m1", "media_type": "VIDEO", "caption": "Pasta receta en un minuto #pasta", "like_count": 40000,
         "permalink": "https://www.instagram.com/reel/m1/", "timestamp": _ago(3),
         "thumbnail_url": "https://scontent.cdninstagram.com/m1.jpg"},
        {"id": "m2", "media_type": "IMAGE", "caption": "Pasta foto", "like_count": 99999,
         "permalink": "https://www.instagram.com/p/m2/"},
    ]
}  # fmt: skip


def _get(url, **kw):
    if url.endswith("/search"):
        assert kw["params"]["order"] == "viewCount"
        return _R(SEARCH)
    if url.endswith("/videos"):
        return _R(STATS)
    if url.endswith("/ig_hashtag_search"):
        return _R({"data": [{"id": "h1"}]})
    if url.endswith("/top_media"):
        return _R(IG_MEDIA)
    if url.startswith("https://"):  # a thumbnail
        return _R(content=b"\xff\xd8" + b"0" * 2000)
    raise AssertionError(url)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(inspiracion, "home", lambda: tmp_path)
    monkeypatch.setattr(inspiracion, "_yt_auth", lambda: {"params": {"key": "k"}})
    monkeypatch.setattr(
        canales,
        "account",
        lambda name, home=None: (
            {"user_id": "9", "token": "t"} if name == "instagram" else {}
        ),
    )
    return tmp_path


def test_queries_brief_alone_and_with_a_model():
    assert inspiracion.queries("Una receta de pasta cremosa") == [
        "receta pasta cremosa"
    ]
    asked = inspiracion.queries(
        "Una receta de pasta cremosa",
        ask=lambda p, **kw: json.dumps(
            {"q": ["pasta cremosa", "creamy pasta recipe", "pasta hack"]}
        ),
    )
    assert asked[1:] == ["pasta cremosa", "creamy pasta recipe", "pasta hack"]
    broken = inspiracion.queries("pasta", ask=lambda p, **kw: "no json")
    assert len(broken) == 1  # a model that fails leaves the brief alone


def test_youtube_api_reads_real_numbers():
    out = inspiracion.youtube_api("pasta", True, _get, {"params": {"key": "k"}})
    assert [v["vistas"] for v in out] == [2_000_000, 1_500_000, 800_000, 900_000]
    assert out[0]["url"] == "https://www.youtube.com/shorts/a1"
    assert out[0]["segundos"] == 32


def test_ytdlp_search_skips_long_videos_for_shorts():
    lines = "\n".join(
        json.dumps(v)
        for v in (
            {
                "id": "x1",
                "title": "Pasta",
                "channel": "A",
                "view_count": 10,
                "duration": 40,
            },
            {
                "id": "x2",
                "title": "Pasta larga",
                "channel": "B",
                "view_count": 10,
                "duration": 900,
            },
            {"title": "sin id"},
        )
    )
    seen = []
    out = inspiracion.youtube_ytdlp(
        "pasta", True, runner=lambda args: seen.append(args) or lines
    )
    assert [v["url"] for v in out] == ["https://www.youtube.com/watch?v=x1"]
    assert seen[0][-1].startswith("ytsearch20:pasta")


def test_three_from_different_creators_and_another_platform(home):
    cands = inspiracion.youtube_api("pasta", True, _get, {"params": {"key": "k"}})
    cands += inspiracion.instagram("pasta", _get)
    three = inspiracion.pick_three(cands, "receta de pasta")
    assert len(three) == 3
    assert len({v["canal"] or v["url"] for v in three}) == 3  # one per creator
    assert {"YouTube", "Instagram"} <= {v["plataforma"] for v in three}
    assert all("teléfono" not in v["titulo"] for v in three)  # off topic loses


def test_instagram_only_with_his_account(monkeypatch):
    monkeypatch.setattr(canales, "account", lambda name, home=None: {})
    assert inspiracion.instagram("pasta", _get) == []


def test_search_saves_choose_and_card(home):
    data = inspiracion.search(
        "receta de pasta",
        get=_get,
        tiktok=lambda url: {"texto": "Trending #pastatok #recetas #fyp"},
    )
    assert len(data["opciones"]) == 3 and data["tiktok"][:2] == ["pastatok", "recetas"]
    assert all(
        v["mini"].startswith(f"/v1/creator/inspiracion/{data['id']}/miniatura/")
        for v in data["opciones"]
    )
    assert (home / data["id"] / "0.jpg").is_file()
    assert all(
        ("vistas" in v["por_que"]) or ("me gusta" in v["por_que"])
        for v in data["opciones"]
    )
    text = inspiracion.card(data)
    assert f"[[inspiracion:{data['id']}]]" in text and "#pastatok" in text

    chosen = inspiracion.choose(data["id"], 1)
    assert chosen["elegida"] == 1
    assert (
        chosen["opciones"][1]["url"] in chosen["mensaje"]
        and "receta de pasta" in chosen["mensaje"]
    )
    assert inspiracion.load(data["id"])["elegida"] == 1
    with pytest.raises(IndexError):
        inspiracion.choose(data["id"], 5)
    with pytest.raises(KeyError):
        inspiracion.load("../../etc")


def test_nothing_found_says_so(home, monkeypatch):
    monkeypatch.setattr(canales, "account", lambda name, home=None: {})
    data = inspiracion.search(
        "pasta", get=lambda url, **kw: _R({}), tiktok=lambda url: {}
    )
    assert data["opciones"] == [] and data["id"] == ""
    assert "No encontré" in inspiracion.card(data)


def test_never_invents_views():
    v = {
        "plataforma": "Instagram",
        "titulo": "pasta",
        "url": "u",
        "vistas": 0,
        "me_gusta": 0,
    }
    assert "vistas" not in inspiracion.why(v, {"pasta"})


def test_tool_and_routes(home):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.creator import routes
    from openjarvis.server.auth_middleware import _OPEN_MEDIA

    data = inspiracion.search("receta de pasta", get=_get, tiktok=lambda url: {})
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    assert (
        client.get(f"/v1/creator/inspiracion/{data['id']}").json()["encargo"]
        == "receta de pasta"
    )
    assert (
        client.get(f"/v1/creator/inspiracion/{data['id']}/miniatura/0.jpg").status_code
        == 200
    )
    assert (
        client.get(f"/v1/creator/inspiracion/{data['id']}/miniatura/x.jpg").status_code
        == 404
    )
    r = client.post(f"/v1/creator/inspiracion/{data['id']}/elegir", json={"opcion": 2})
    assert r.status_code == 200 and r.json()["elegida"] == 2
    assert (
        client.post(
            f"/v1/creator/inspiracion/{data['id']}/elegir", json={"opcion": 9}
        ).status_code
        == 404
    )
    assert _OPEN_MEDIA.fullmatch(
        f"/v1/creator/inspiracion/{data['id']}/miniatura/0.jpg"
    )
    assert not _OPEN_MEDIA.fullmatch(f"/v1/creator/inspiracion/{data['id']}")

    from openjarvis.tools.inspiracion_tool import InspiracionTool

    out = InspiracionTool().execute(action="elegir", id=data["id"], opcion=1)
    assert out.success and data["opciones"][0]["url"] in out.content
    assert not InspiracionTool().execute(action="buscar", idea="").success

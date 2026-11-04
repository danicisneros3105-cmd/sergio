"""Creator regressions: provenance, numerical anchors and valid clip boundaries."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from openjarvis.automatiza import tendencias
from openjarvis.estudio import recortes
from openjarvis.vfx import build_scene
from openjarvis.video_essay import partes


def test_authorized_trends_request_merges_headers(monkeypatch):
    import httpx

    calls = []

    class Response:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: calls.append(kw) or Response())
    tendencias._get("https://example.com", headers={"Authorization": "Bearer test"})
    assert calls[0]["headers"]["Authorization"] == "Bearer test"
    assert "User-Agent" in calls[0]["headers"]


def test_trend_rank_ignores_duplicate_echoes_and_one_generic_word():
    signals = [
        {"tema": "video cámaras nuevas", "fuente": "A", "cifra": 20},
        {"tema": "video receta pan", "fuente": "B", "cifra": 100},
        {"tema": "video cámaras nuevas", "fuente": "A", "cifra": 20},
    ]
    before = json.dumps(signals)
    result = tendencias.rank(signals)
    assert len(result) == 2
    assert all(len(s["fuentes"]) == 1 for s in result)
    assert json.dumps(signals) == before


def test_trends_prefer_recent_equal_popularity_and_handle_invalid_counts():
    now = datetime.now(timezone.utc)
    signals = [
        {
            "tema": "older",
            "fuente": "A",
            "cifra": 100,
            "publicado_en": (now - timedelta(days=100)).isoformat(),
        },
        {"tema": "newer", "fuente": "A", "cifra": 100, "publicado_en": now.isoformat()},
        {"tema": "bad", "fuente": "A", "cifra": "NaN"},
    ]
    result = tendencias.rank(signals)
    assert result[0]["tema"] == "newer"
    assert next(s for s in result if s["tema"] == "bad")["cifra"] == 0


def test_rewrite_cannot_add_facts_to_get_a_better_score():
    source = "Hoy en día todo cambia. Es importante destacar que hay ideas nuevas. Las cosas pasan. Todo sigue."
    invented = "En 1998 Marta perdió 4 archivos. Pero guardaba 2 copias. Nadie lo esperaba. Por eso recuperó todo."
    script = {"beats": [{"text": source}]}
    result, report = partes.improve(
        script, lambda *a, **kw: json.dumps({"beats": [{"text": invented}]}), passes=1
    )
    assert result["beats"] == script["beats"]
    assert report["rejected_facts"] == 1


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1])
def test_words_reject_invalid_timestamps(bad):
    with pytest.raises(ValueError):
        recortes.sentences([{"text": "word", "start": bad, "end": 2}])


def test_zero_picks_and_duration_padding():
    words = [{"text": "En 2020 cambió todo.", "start": 0, "end": 20}]
    assert recortes.moments(words, n=0) == []
    moment = recortes.moments(words, min_s=20, max_s=20)[0]
    assert moment.end - moment.start == 20
    parsed = recortes.from_srt("1\n00:00:00,5 --> 00:00:01,5\n<i>Hola</i>\n")
    assert parsed[0].text == "Hola" and parsed[0].start == 0.5


@pytest.mark.parametrize("mode", ["2d", "3d"])
def test_editable_motion_scene_compiles_and_is_bounded(mode):
    script = build_scene(
        [("motion_graphics", {"mode": mode, "title": 'Blue "Studio"'})]
    )
    compile(script, "<motion_scene>", "exec")
    assert "keyframe_insert" in script and "Editable Title" in script
    with pytest.raises(ValueError):
        build_scene([("motion_graphics", {"frames": 100000})])


def test_the_same_clip_is_not_downloaded_twice_through_url_aliases():
    from openjarvis.video_essay.sources import Candidate, rank

    clips = [
        Candidate("https://youtu.be/example", "web", title="Rocky training"),
        Candidate(
            "https://www.youtube.com/watch?v=example&feature=share",
            "web",
            title="Rocky training",
        ),
        Candidate(
            "https://www.youtube.com/shorts/another", "web", title="Rocky training"
        ),
    ]
    assert len(rank(clips, "Rocky training")) == 2

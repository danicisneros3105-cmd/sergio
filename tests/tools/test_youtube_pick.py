"""Finding the YouTube video the user describes."""

import json
from types import SimpleNamespace as NS

import pytest

from openjarvis.tools import youtube_pick as yp


def _page(videos):
    data = {"contents": {"twoColumnSearchResultsRenderer": {"primaryContents": {"sectionListRenderer": {
        "contents": [{"itemSectionRenderer": {"contents": [
            {"videoRenderer": {"videoId": v, "title": {"runs": [{"text": t}]},
                               "ownerText": {"runs": [{"text": "MrBeast"}]},
                               "lengthText": {"simpleText": "12:01"}}}
            for v, t in videos
        ]}}]}}}}}
    return f"<script>var ytInitialData = {json.dumps(data)};</script>"


def test_the_request_becomes_a_short_search():
    assert yp.search_query("Sergio, pon un video de MrBeast en el que salga con traje negro") == "mrbeast traje negro"
    assert yp.wants_looks("MrBeast con traje negro") and not yp.wants_looks("el último video de MrBeast")


def test_parse_results():
    html = _page([("aaa", "Uno"), ("bbb", "Dos"), ("aaa", "Uno")])
    assert [v["id"] for v in yp.parse_results(html)] == ["aaa", "bbb"]
    assert yp.parse_results("<html></html>") == []


def test_gemini_picks_by_the_thumbnails():
    pytest.importorskip("google.genai")
    html = _page([("aaa", "I Spent 50 Hours Buried Alive"), ("bbb", "Last To Leave Wins"), ("ccc", "Suit Up!")])
    asked = []

    def get(url):
        return NS(text=html, content=b"not an image")

    def ask(image, prompt):
        asked.append(prompt)
        assert image[:2] == b"\xff\xd8"  # a JPEG contact sheet
        return '{"n": 3, "por_que": "lleva traje negro"}'

    video = yp.pick("pon un video de MrBeast con traje negro", get, ask)
    assert video["id"] == "ccc" and video["url"].endswith("v=ccc") and "traje" in video["why"]
    assert "3. Suit Up!" in asked[0]
    plain = yp.pick("pon el último video de MrBeast", get, ask)
    assert plain["id"] == "aaa" and len(asked) == 1  # nothing visual: no Gemini

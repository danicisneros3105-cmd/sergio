"""Video Pro learns editing styles from real videos and edits with them."""

from __future__ import annotations

import json

from openjarvis.tools import video_pro
from openjarvis.tools import video_style as vs

WATCH = {
    "title": "Anuncio",
    "channel": "Dyson",
    "length_s": 40,
    "cuts": 30,
    "avg_shot_s": 1.2,
    "pace": "very fast",
    "hook": "producto en macro",
    "structure": ["gancho", "detalle", "cierre"],
    "transitions": {"cut": 9, "flash": 1},
    "punch_in": 0.4,
    "speed_ramps": 0.1,
    "slow_motion": 2,
    "text": {
        "style": "bold white sans caps",
        "position": "center | lower third",
        "words_per_caption": 2,
        "kinetic": True,
        "color": "#ffffff",
        "accent": "nope",
    },
    "grade": {
        "look": "frío clínico",
        "contrast": 9,
        "saturation": 0.9,
        "warmth": -0.3,
        "vignette": True,
    },
    "audio": {"music": "electrónica", "beat_synced_cuts": True, "sfx": ["click"]},
    "aspect": "9:16",
    "signature": ["cortes de 1 s", "macro"],
}


def test_one_video_analysis_is_checked_and_clamped():
    got = vs.parse_watch(json.dumps(WATCH))
    assert got["transitions"]["cut"] == 0.9 and got["transitions"]["flash"] == 0.1
    assert got["slow_motion"] == 1.0 and got["grade"]["contrast"] == 1.5  # clamped
    assert (
        got["text"]["position"] == "center"
        and got["text"]["color"] == "#FFFFFF"
        and got["text"]["accent"] == "#FFD400"
    )
    assert got["aspect"] == "9:16" and got["channel"] == "Dyson"


def test_learning_from_links_merges_every_video(tmp_path):
    other = dict(WATCH, avg_shot_s=2.0, title="Short")
    answers = {
        "https://www.youtube.com/watch?v=AAAAAAAAAAA": json.dumps(WATCH),
        "https://www.youtube.com/watch?v=BBBBBBBBBBB": json.dumps(other),
    }
    style = vs.learn(
        "anuncio https://youtu.be/AAAAAAAAAAA y https://www.youtube.com/shorts/BBBBBBBBBBB",
        name="Dyson",
        watch=answers.__getitem__,
        folder=tmp_path,
    )
    assert style["avg_shot_s"] == 1.6 and len(style["sources"]) == 2
    assert (tmp_path / "dyson.json").exists() and "cortes de 1 s" in style["signature"]


def test_searched_videos_must_belong_to_the_channel(tmp_path):
    found = "https://www.youtube.com/watch?v=AAAAAAAAAAA https://www.youtube.com/watch?v=BBBBBBBBBBB"
    authors = {
        "https://www.youtube.com/watch?v=AAAAAAAAAAA": "NextCore",
        "https://www.youtube.com/watch?v=BBBBBBBBBBB": "ProductivityPulse",
    }
    watched = []

    def watch(url):
        watched.append(url)
        return json.dumps(dict(WATCH, channel=""))

    style = vs.learn(
        "NextCore",
        find=lambda s, n: found,
        watch=watch,
        author=authors.__getitem__,
        folder=tmp_path,
    )
    assert (
        watched == ["https://www.youtube.com/watch?v=AAAAAAAAAAA"]
        and style["name"] == "NextCore"
    )
    assert vs.belongs("NextCore", "-") is False and vs.belongs("x", "") is True


def test_the_shipped_styles_are_found_by_name():
    assert vs.find_style("dyson")["name"] == "Dyson CameraJet"
    assert (
        vs.find_style("al estilo del anuncio de dyson camerajet")["name"]
        == "Dyson CameraJet"
    )
    assert vs.find_style("next core")["name"] == "NextCore"
    assert vs.find_style("mrbeast") is None
    for style in vs.available():
        assert (
            style["sources"]
            and style["avg_shot_s"] > 0
            and "Aprendido de" in vs.describe(style)
        )


def test_the_editor_plans_in_the_style_with_transitions_zooms_and_speed():
    seen = {}

    def ask(sheets, prompt):
        seen["prompt"] = prompt
        return json.dumps(
            {
                "aspect": "9:16",
                "segments": [
                    {
                        "clip": 1,
                        "start": 0,
                        "end": 1.2,
                        "transition": "flash",
                        "zoom": "punch",
                        "speed": 1.5,
                        "caption": "YA",
                    },
                    {
                        "clip": 1,
                        "start": 2,
                        "end": 3,
                        "transition": "teleport",
                        "zoom": "spin",
                        "speed": 7,
                    },
                ],
                "youtube": {"title": "t"},
            }
        )

    style = vs.find_style("dyson")
    got = video_pro.plan("un short", [b"x"], [10.0], ask=ask, style=style)
    assert (
        "EDIT IN THIS STYLE" in seen["prompt"] and "Dyson CameraJet" in seen["prompt"]
    )
    first, second = got["segments"]
    assert (first["transition"], first["zoom"], first["speed"]) == (
        "flash",
        "punch",
        1.5,
    )
    assert (second["transition"], second["zoom"], second["speed"]) == (
        "fade",
        "none",
        2.0,
    )
    assert (
        got["style"]["name"] == "Dyson CameraJet"
        and "contrast" in got["style"]["grade"]
    )


def test_youtube_links_are_recognised_in_any_form():
    text = "mira https://youtu.be/abcdefghijk, https://www.youtube.com/shorts/ABCDEFGHIJK y https://youtu.be/abcdefghijk"
    assert vs.youtube_urls(text) == [
        "https://www.youtube.com/watch?v=abcdefghijk",
        "https://www.youtube.com/watch?v=ABCDEFGHIJK",
    ]

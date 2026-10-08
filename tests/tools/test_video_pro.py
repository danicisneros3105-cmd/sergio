"""Video Pro: Gemini plans the edit from contact sheets."""

import pytest

from openjarvis.tools.video_pro import parse_plan, plan


def test_plan_is_checked_against_the_real_clips():
    text = """{"aspect": "9:16", "title_overlay": "Mi viaje", "segments": [
        {"clip": 1, "start": 1, "end": 4, "caption": "La llegada"},
        {"clip": 2, "start": 9, "end": 30, "caption": ""},
        {"clip": 7, "start": 0, "end": 3},
        {"clip": 1, "start": 2, "end": 2.2}],
      "youtube": {"title": "Un viaje increíble", "description": "Día uno.", "tags": ["viaje", "vlog"]}}"""
    got = parse_plan(text, [10.0, 12.0])
    assert got["aspect"] == "9:16" and got["title_overlay"] == "Mi viaje"
    plain = {"transition": "fade", "zoom": "none", "speed": 1.0}  # what an unstyled cut gets
    assert got["segments"] == [
        {"clip": 0, "start": 1.0, "end": 4.0, "caption": "La llegada", **plain},
        {"clip": 1, "start": 9.0, "end": 12.0, "caption": "", **plain},  # clipped to the clip
    ]
    assert got["youtube"]["tags"] == ["viaje", "vlog"]
    with pytest.raises(RuntimeError):
        parse_plan("{}", [10.0])


def test_plan_asks_with_one_sheet_per_clip():
    seen = {}

    def ask(sheets, prompt):
        seen["n"], seen["prompt"] = len(sheets), prompt
        return '{"segments": [{"clip": 1, "start": 0, "end": 2}], "youtube": {}}'

    got = plan("un short de mi viaje", [b"a", b"b"], [5.0, 6.0], ask)
    assert seen["n"] == 2 and "short vertical" in seen["prompt"] and got["aspect"] == "16:9"

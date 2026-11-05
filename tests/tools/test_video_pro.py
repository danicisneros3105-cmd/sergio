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
    plain = {
        "transition": "fade",
        "zoom": "none",
        "speed": 1.0,
    }  # what an unstyled cut gets
    assert got["segments"] == [
        {"clip": 0, "start": 1.0, "end": 4.0, "caption": "La llegada", **plain},
        {
            "clip": 1,
            "start": 9.0,
            "end": 12.0,
            "caption": "",
            **plain,
        },  # clipped to the clip
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
    assert (
        seen["n"] == 2
        and "short vertical" in seen["prompt"]
        and got["aspect"] == "9:16"
    )


@pytest.mark.parametrize("model", ["gpt-4o-mini", "qwen2.5vl:7b"])
def test_video_vision_sends_all_sheets_and_uses_configured_provider(monkeypatch, model):
    import base64
    import json

    import httpx

    from openjarvis.tools.vision_look import ask_images

    monkeypatch.setenv("SERGIO_VISION_MODEL", model)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MOONSHOT_API_KEY", "other-test-key")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    frames = [base64.b64encode(image).decode() for image in (b"first", b"second")]

    def handle(request):
        body = json.loads(request.content)
        assert body["model"] == model
        message = body["messages"][0]
        if model.startswith("gpt-"):
            assert request.url.host == "api.openai.com"
            assert [
                part["image_url"]["url"].split(",")[1]
                for part in message["content"][:-1]
            ] == frames
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "plan"}}]}
            )
        assert request.url.host == "localhost"
        assert message["images"] == frames
        return httpx.Response(200, json={"message": {"content": "plan"}})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert ask_images([b"first", b"second"], "montaje", client) == "plan"


def test_local_video_vision_does_not_upload_on_failure(monkeypatch):
    import httpx

    from openjarvis.tools.vision_look import ask_images

    monkeypatch.setenv("SERGIO_VISION_MODEL", "qwen2.5vl:7b")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    requests = []

    def handle(request):
        requests.append(request.url.host)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(RuntimeError, match="Ollama"):
            ask_images([b"frame"], "montaje", client)
    assert requests == ["localhost"]


def test_video_plan_drops_repeated_ranges_and_honors_requested_aspect():
    def ask(_sheets, _prompt):
        return """{"aspect": "9:16", "segments": [
          {"clip": 1, "start": 0, "end": 2},
          {"clip": 1, "start": 1, "end": 3},
          {"clip": 1, "start": 2, "end": 4}
        ], "youtube": {"tags": "invalid"}}"""

    result = plan("Un reel horizontal 16:9", [b"sheet"], [4.0], ask)
    assert result["aspect"] == "16:9"
    assert [(cut["start"], cut["end"]) for cut in result["segments"]] == [(0, 2), (2, 4)]
    assert result["youtube"]["tags"] == []

"""Skills from GitHub, delivery (tone and pauses), other companies' models
and real footage first."""

from __future__ import annotations

import io
import json
import wave

import numpy as np
import pytest

from openjarvis.creator import llm
from openjarvis.video_essay import director, media, script, skillbook
from openjarvis.video_essay.plan import Shot


def test_the_catalog_has_the_skills_the_owner_asked_for():
    c = skillbook.counts()
    assert c["guion"] >= 20 and c["motion"] >= 25
    usable = [e for e in skillbook.catalog()["guion"] if e.get("usable", True)]
    assert len(usable) >= 20
    for kind, entries in skillbook.catalog().items():
        for e in entries:
            assert e["repo"].count("/") == 1 and e["path"] and e["licence"], e
            assert skillbook.raw_url(e).startswith("https://raw.githubusercontent.com/")


def test_sync_downloads_and_keeps_old_copies_when_a_download_fails(tmp_path):
    got = skillbook.sync(tmp_path, get=lambda url: "# Hook\nOpen with a question.")
    total = sum(skillbook.counts().values())
    assert got == {"bajadas": total, "fallidas": 0}

    def broken(url):
        raise OSError("sin red")

    assert skillbook.sync(tmp_path, get=broken)["fallidas"] == total
    assert any((tmp_path / "video_skills" / "guion").iterdir())  # still there


def test_guidance_fits_the_budget_and_carries_the_delivery_rules(tmp_path):
    skillbook.sync(
        tmp_path, get=lambda url: "---\nname: x\n---\nHook in 3 seconds. " * 200
    )
    text = skillbook.guidance(
        "guion", "video viral de ciencia", home=tmp_path, budget=4000
    )
    assert len(text) <= 4000 and "SKILLS FROM GITHUB" in text and "DELIVERY" in text
    motion = skillbook.guidance("motion", "kinetic typography", home=tmp_path)
    assert "DELIVERY" not in motion and "---" not in motion.split("\n", 1)[1][:10]


def test_delivery_is_cleaned():
    assert director._delivery({"tone": "Serious", "pause": 9}) == {
        "tone": "serious",
        "pause": 1.6,
    }
    assert director._delivery({"tone": "made-up", "pause": "x"}) == {
        "tone": "",
        "pause": 0.0,
    }
    assert director._delivery(None) == {"tone": "", "pause": 0.0}


def test_beats_with_the_same_tone_are_read_together():
    beats = [
        {"text": "Uno.", "delivery": {"tone": "calm", "pause": 0}},
        {"text": "Dos.", "delivery": {"tone": "calm", "pause": 0.8}},
        {"text": "Tres.", "delivery": {"tone": "urgent", "pause": 0}},
    ]
    g = script.groups(beats)
    assert [x["text"] for x in g] == ["Uno. Dos.", "Tres."]
    assert g[0]["pause"] == 0.8 and g[1]["tone"] == "urgent"


def _wav(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes((np.ones(int(24000 * seconds)) * 3000).astype("<i2").tobytes())
    return buf.getvalue()


def test_a_pause_is_real_silence_in_the_narration():
    from openjarvis.video_essay import audio

    beats = [
        {"text": "Primero.", "delivery": {"tone": "calm", "pause": 1.2}},
        {"text": "Después.", "delivery": {"tone": "urgent", "pause": 0}},
    ]
    out = audio.read_wav(script.narrate_beats(beats, speak=lambda t: _wav(0.5)))
    silent = np.abs(out) < 1e-4
    run = best = 0
    for s in silent:
        run = run + 1 if s else 0
        best = max(best, run)
    assert best / audio.SR >= 1.15  # the 1.2 s pause, not the 0.22 s breath


def test_real_footage_always_comes_before_a_generated_picture():
    order = media.order_for(
        Shot(0, 1, source="ai"), ["library", "stock", "web", "ai", "image"]
    )
    assert order.index("library") < order.index("ai") and order[-2:] == ["ai", "image"]
    assert media.order_for(Shot(0, 1), ["image", "stock"])[0] == "stock"


def test_other_companies_answer_when_gemini_cannot(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
    monkeypatch.delenv("SERGIO_VIDEO_MODELO", raising=False)

    def no_quota(*a, **k):
        raise llm.CreatorError("429 sin cuota")

    asked = []

    class Engine:
        def generate(self, messages, model, **kw):
            asked.append(model)
            return {"content": '```json\n{"ok": true}\n```'}

    monkeypatch.setattr(llm, "_ask_gemini", no_quota)
    monkeypatch.setattr("openjarvis.engine.cloud.CloudEngine", Engine)
    assert json.loads(llm.ask("hola", json_mode=True)) == {"ok": True}
    assert asked == ["claude-sonnet-5-5"]


def test_the_owners_chosen_model_goes_first(monkeypatch):
    monkeypatch.setenv("SERGIO_VIDEO_MODELO", "gpt-5.6-terra")
    monkeypatch.setenv("OPENAI_API_KEY", "z")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    seen = []

    class Engine:
        def generate(self, messages, model, **kw):
            seen.append(model)
            return {"content": "listo"}

    monkeypatch.setattr(
        llm, "_ask_gemini", lambda *a, **k: pytest.fail("Gemini was not chosen")
    )
    monkeypatch.setattr("openjarvis.engine.cloud.CloudEngine", Engine)
    assert llm.ask("hola") == "listo" and seen[0] == "gpt-5.6-terra"


def test_pictures_still_go_to_gemini(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(llm, "_ask_gemini", lambda *a, **k: "visto")
    assert llm.ask(["mira", b"img"]) == "visto"

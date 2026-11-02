"""Public edition: what is the owner's own risk is never on for customers."""

from __future__ import annotations

from openjarvis import edicion


def test_personal_is_the_default_and_keeps_the_owners_switches(monkeypatch):
    monkeypatch.delenv("SERGIO_EDICION", raising=False)
    assert not edicion.publica()
    monkeypatch.delenv("SERGIO_CLIPS_WEB", raising=False)
    assert edicion.allowed("SERGIO_CLIPS_WEB")
    monkeypatch.setenv("SERGIO_CLIPS_WEB", "0")
    assert not edicion.allowed("SERGIO_CLIPS_WEB")


def test_public_edition_cannot_be_switched_back_on(monkeypatch):
    monkeypatch.setenv("SERGIO_EDICION", "publica")
    monkeypatch.setenv("SERGIO_CLIPS_WEB", "1")
    monkeypatch.setenv("SERGIO_PROMPT_LIBRARY", "1")
    from openjarvis.prompt_library import guidance
    from openjarvis.video_essay import sources

    assert edicion.publica()
    assert not sources.web_allowed()
    assert not guidance._enabled()


def test_public_edition_drops_jamendo_opensky_and_named_songs(monkeypatch):
    monkeypatch.setenv("SERGIO_EDICION", "publica")
    monkeypatch.setenv("JAMENDO_CLIENT_ID", "x")
    from openjarvis.video_essay import music

    assert music.search_jamendo("epic", 3) == []
    called = []
    got = music.pick(
        "canción: algo",
        {},
        __import__("pathlib").Path("."),
        10,
        "ffmpeg",
        song=lambda q, n: called.append(q) or [],
    )
    assert got is None and not called

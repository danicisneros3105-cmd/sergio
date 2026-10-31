"""Scenes of real films chosen per moment, clips whose title fits, captions
cut where people cut, and narration parts at one loudness."""

from __future__ import annotations

import json

import numpy as np

from openjarvis.video_essay import films, render, script, sources
from openjarvis.video_essay.plan import Shot, Word


def _shots():
    words = [
        Word(w, i, i + 0.9)
        for i, w in enumerate("nunca dejes de correr aunque duela".split())
    ]
    shots = [
        Shot(i, i + 1, kind="broll", source="film" if i % 2 == 0 else "stock")
        for i in range(6)
    ]
    return shots, words


def test_each_film_shot_gets_a_named_scene():
    shots, words = _shots()
    answer = {"scenes": [
        {"shot": 0, "film": "Rocky", "year": 1976, "scene": "running up the museum steps"},
        {"shot": 2, "film": "Forrest Gump", "year": 1994, "scene": "he starts running across America"},
        {"shot": 1, "film": "Inventada", "year": 2020, "scene": "not a film shot"},  # not a film shot
        {"shot": 4, "film": "Rocky", "year": "mil", "scene": "bad year"},  # no real year
    ]}  # fmt: skip
    asked = []
    n = films.plan_scenes(
        shots,
        words,
        "Correr",
        "No rendirse",
        lambda p: asked.append(p) or json.dumps(answer),
    )
    assert n == 2
    assert shots[0].search == "Rocky (1976) running up the museum steps"
    assert shots[1].search == "" and shots[4].search == ""
    assert "REAL" in asked[0] and "nunca" in asked[0]
    assert films.films_in(shots) == ["Rocky (1976)", "Forrest Gump (1994)"]


def test_no_more_than_two_shots_from_one_film():
    shots = [Shot(i, i + 1, source="film") for i in range(4)]
    scenes = [
        {"shot": i, "film": "Rocky", "year": 1976, "scene": f"scene {i}"}
        for i in range(4)
    ]
    assert films.apply(shots, scenes, {0, 1, 2, 3}) == 2


def test_a_model_failure_never_invents_a_film(monkeypatch):
    # Since 28 Oct 2026 a busy model is asked again, and when it never
    # answers the film shots may get a famous REAL scene from
    # films.KNOWN_SCENES (owner: «faltan clips de películas»); never anything
    # else, and the shots that are not film shots stay alone.
    monkeypatch.setattr(films, "sleep", lambda s: None)
    shots, words = _shots()
    films.plan_scenes(shots, words, "t", "l", lambda p: "no es json")
    known = {f"{name} ({year})" for _, name, year, _ in films.KNOWN_SCENES}
    for s in shots:
        if s.source != "film":
            assert s.search == ""
        elif s.search:
            assert any(s.search.startswith(k) for k in known)


def test_a_named_scene_is_searched_first():
    from openjarvis.video_essay import media

    s = Shot(0, 1, visual="a runner on steps", search="Rocky (1976) museum steps")
    assert media.queries(s)[0] == "Rocky (1976) museum steps"


def _runner(titles):
    def run(args):
        return "\n".join(
            json.dumps({"id": f"v{i}", "title": t, "duration": 120})
            for i, t in enumerate(titles)
        )

    return run


def test_scene_search_keeps_only_clips_of_that_film():
    run = _runner(
        [
            "Rocky (1976) - Training Montage Scene",
            "Easy pasta recipe",
            "Rocky Balboa steps HD",
        ]
    )
    got = sources.search_scenes(
        "Rocky (1976) running up the museum steps", 5, runner=run
    )
    assert got and all("rocky" in c.title.lower() for c in got)


def test_a_clip_whose_title_has_nothing_to_do_is_dropped():
    c = sources.Candidate("u", "web", title="Top 10 cat fails")
    assert not sources.fits(c, "astronaut floating in space station")
    assert sources.fits(
        sources.Candidate("u", "web", title="Space station astronaut view"),
        "astronaut space station",
    )
    assert sources.fits(
        sources.Candidate("u", "web"), "anything"
    )  # no title: the editor's eyes check it


def test_captions_never_end_on_a_little_word():
    words = "y entonces me di cuenta de que la vida era otra cosa".split()
    chunks = render.chunks_of(words, size=4)
    for c in chunks[:-1]:
        assert words[c[-1]].lower() not in render.WEAK, [words[i] for i in c]
    assert sorted(i for c in chunks for i in c) == list(range(len(words)))


def test_narration_parts_come_out_at_one_loudness_without_clicks():
    loud = np.full(24000, 0.15, dtype=np.float32)
    soft = np.full(24000, 0.05, dtype=np.float32)
    a, b = script.even(loud), script.even(soft)
    mid = slice(5000, 19000)
    assert (
        abs(float(np.sqrt(np.mean(a[mid] ** 2))) - float(np.sqrt(np.mean(b[mid] ** 2))))
        < 0.03
    )
    assert abs(a[0]) < 0.01 and abs(a[-1]) < 0.01  # faded at the seams

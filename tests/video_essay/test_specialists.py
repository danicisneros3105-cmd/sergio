"""The film and creator specialists, trained on the fly brain."""

from __future__ import annotations

from openjarvis.connectome.core import Core
from openjarvis.video_essay import specialists as S


def test_every_card_has_training_and_held_out_requests():
    for kind, cards in S.SPECIALISTS.items():
        keys = [c.key for c in cards]
        assert len(keys) == len(set(keys)) >= 15, kind
        for c in cards:
            assert len(c.train) >= 5 and len(c.held) >= 2 and c.how and c.school
            assert not set(c.train) & set(c.held)
    assert {c.school for c in S.CINE} >= {"Christopher Nolan", "Stanley Kubrick"}
    assert "MrBeast" in {c.school for c in S.CREADORES}


def test_the_style_or_the_brief_picks_the_specialist():
    assert S.which("corto-3d") == "cine"
    assert S.which("reto-viral") == "creadores"
    assert S.which("", "un cortometraje de ciencia ficción") == "cine"
    assert S.which("", "un video para mi canal de recetas") == "creadores"


def test_it_is_born_knowing_its_craft(tmp_path):
    core = Core(tmp_path)
    for kind, cards in S.SPECIALISTS.items():
        hits = 0
        for c in cards:
            got = [a[0] for a in S.advise(kind, c.train[0], core)]
            hits += c.key in got
        assert hits >= len(cards) * 0.8, kind
        assert core.brain(f"especialista:{kind}").meta["specialist"]["cards"] == len(
            cards
        )


def test_the_learning_curve_starts_at_chance_and_climbs(tmp_path):
    curve = S.learning_curve("cine", Core(tmp_path), epochs=3)
    assert curve[0]["top3"] == curve[0]["chance_top3"] and curve[0]["changed"] == 0
    assert curve[-1]["changed"] > 0 and curve[-1]["grown"] > 0
    assert curve[-1]["top3"] >= curve[0]["top3"]


def test_finished_videos_and_the_owners_taste_retrain_it(tmp_path):
    core = Core(tmp_path)
    brief = "un video sobre mi viaje a Galápagos"

    def strength(key):
        return dict(
            (k, v) for k, _s, _h, v in S.advise("creadores", brief, core, k=16)
        )[key]

    start = strength("timelapse")
    assert S.learn_from_video("creadores", brief, ["timelapse"], 9.5, core) > 0
    assert strength("timelapse") > start
    high = strength("timelapse")
    assert S.learn_from_video("creadores", brief, ["timelapse"], 4, core) < 0
    assert strength("timelapse") < high
    assert S.learn_from_video("creadores", brief, ["timelapse"], 7, core) == 0.0
    assert S.teach("creadores", brief, "mapas", True, core)
    assert not S.teach("creadores", brief, "no-existe", True, core)


def test_its_advice_reads_as_craft_without_names_on_screen(tmp_path):
    core = Core(tmp_path)
    advice = S.advise(
        "cine", "una carrera contra el tiempo para desactivar la bomba", core
    )
    block = S.prompt_block(advice, "cine")
    assert "film specialist" in block and "do not name anyone on screen" in block
    assert len(advice) == 3 and all(a[2] for a in advice)
    assert S.prompt_block([], "cine") == ""

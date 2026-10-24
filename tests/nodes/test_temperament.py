"""Each Node has its own fly brain, born with a temperament and shaped by its work."""

from __future__ import annotations

from openjarvis.connectome.core import Core
from openjarvis.nodes import temperament as T


def test_each_node_is_born_with_its_own_instincts(tmp_path):
    core = Core(tmp_path)
    for key, temp in T.TEMPERAMENTS.items():
        for request, move in temp.curriculum[:3]:
            got = [m for m, _how, _v in T.instinct(key, request, core)]
            assert move in got, (key, request, got)
        assert core.brain(f"node:{key}").meta["temperament"]["examples"] == len(
            temp.curriculum
        )


def test_the_same_request_gets_a_different_answer_from_each_node(tmp_path):
    core = Core(tmp_path)
    request = "quiero lanzar una marca de café"
    firsts = {k: T.instinct(k, request, core)[0][0] for k in T.TEMPERAMENTS}
    assert len(set(firsts.values())) == 4  # four temperaments, four instincts
    block = T.prompt_block("tennessee", "¿vale la pena abrir una cafetería?", core)
    assert "instinto" in block and "veredicto" in block


def test_its_own_work_retrains_it_and_the_brains_drift_apart(tmp_path):
    core = Core(tmp_path)
    request = "prepara la reunión con el banco"
    before = dict((m, v) for m, _h, v in T.instinct("rihno", request, core, k=5))
    for _ in range(4):
        T.learn_from_turn("rihno", request, ["resumen"], True, core)
    after = dict((m, v) for m, _h, v in T.instinct("rihno", request, core, k=5))
    assert after["resumen"] > before.get("resumen", 0)
    for _ in range(4):
        T.learn_from_turn("rihno", request, ["resumen"], False, core)
    punished = dict((m, v) for m, _h, v in T.instinct("rihno", request, core, k=5))
    assert punished.get("resumen", 0) < after["resumen"]

    div = T.divergence(core)
    assert set(div) == set(T.TEMPERAMENTS)
    assert all(0 < d <= 1 for row in div.values() for d in row.values())


def test_tennessee_feels_mistakes_more_than_hous(tmp_path):
    core = Core(tmp_path)
    request = "revisa mi plan"
    T.brain_for("tennessee", core)
    T.brain_for("hous", core)
    t0 = core.brain("node:tennessee").stats()["memory"]["rapida"]
    h0 = core.brain("node:hous").stats()["memory"]["rapida"]
    T.learn_from_turn("tennessee", request, ["riesgos"], False, core)
    T.learn_from_turn("hous", request, ["pulir"], False, core)
    t_drop = abs(core.brain("node:tennessee").stats()["memory"]["rapida"] - t0)
    h_drop = abs(core.brain("node:hous").stats()["memory"]["rapida"] - h0)
    assert T.TEMPERAMENTS["tennessee"].punish_gain > T.TEMPERAMENTS["hous"].punish_gain
    assert t_drop > h_drop

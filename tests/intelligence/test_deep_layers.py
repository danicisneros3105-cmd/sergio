"""The ten reasoning layers, driven by scripted models (no network)."""

from __future__ import annotations

import json
import random

import pytest

from openjarvis.intelligence._llm import LLM, clamp, parse_json
from openjarvis.intelligence.causal import (
    CausalGraph,
    analyse,
    causal_answer,
    graph_from_json,
)
from openjarvis.intelligence.consistency import (
    extract_final,
    normalise,
    self_consistency,
)
from openjarvis.intelligence.constitution import enforce, rule_check
from openjarvis.intelligence.counterfactual import counterfactual, minimal_changes
from openjarvis.intelligence.deep import deep_think
from openjarvis.intelligence.reflection import reflect
from openjarvis.intelligence.tot import tree_of_thoughts
from openjarvis.intelligence.uncertainty import (
    Calibrator,
    decide,
    estimate,
    hedge_score,
)
from openjarvis.learning.meta_learner import MetaLearner, task_kind
from openjarvis.learning.recursive import RecursiveImprover
from openjarvis.learning.self_play import (
    GENERATORS,
    Curriculum,
    Problem,
    practice,
    propose_and_solve,
    run_code_tests,
    verify,
)


def scripted(rules):
    """A fake model: the first (substring, reply) whose substring is in the prompt answers.
    A reply may be a list (consumed in order) or a callable(prompt)."""
    state = {k: list(v) if isinstance(v, list) else v for k, v in rules}

    def fn(prompt, system=None, temperature=0.7, max_tokens=2048):
        for key, _ in rules:
            if key in prompt:
                reply = state[key]
                if isinstance(reply, list):
                    return reply.pop(0) if len(reply) > 1 else reply[0]
                return reply(prompt) if callable(reply) else reply
        return "ok"

    return LLM(fn)


# -- shared helpers ------------------------------------------------------------
def test_parse_json_reads_fenced_and_embedded_json():
    assert parse_json('blah ```json\n{"a": 1}\n``` tail') == {"a": 1}
    assert parse_json('Sure! {"score": 7, "issues": ["x}"]} done') == {"score": 7, "issues": ["x}"]}
    assert parse_json("[1, 2]") == [1, 2]
    assert parse_json("nothing here") is None
    assert clamp("score 12/10") == 10 and clamp(None, default=3) == 3


def test_plain_functions_and_engines_work_as_models():
    calls = []

    class Engine:
        engine_id = "fake"

        def generate(self, messages, model, temperature, max_tokens):
            calls.append((messages[0].role.value, model))
            return {"content": "hola"}

    assert LLM(lambda p: p.upper())("x") == "X"
    assert LLM.from_engine(Engine(), "m")("q", system="s") == "hola"
    assert calls == [("system", "m")]


# -- 1 reflection ----------------------------------------------------------------
def test_reflection_revises_until_the_critic_is_satisfied():
    llm = scripted([
        ("demanding reviewer", [json.dumps({"score": 4, "issues": ["2+2 is 4, not 5"]}),
                                json.dumps({"score": 9, "issues": []})]),
        ("Rewrite the ANSWER", "2 + 2 = 4"),
    ])
    r = reflect("What is 2+2?", llm, draft="2 + 2 = 5")
    assert r.answer == "2 + 2 = 4" and r.score == 9 and r.stopped_because == "target_reached"
    assert r.history[0]["issues"] == ["2+2 is 4, not 5"]


def test_reflection_never_returns_a_worse_revision_and_obeys_hard_checks():
    llm = scripted([
        ("demanding reviewer", [json.dumps({"score": 7, "issues": ["style"]}),
                                json.dumps({"score": 3, "issues": ["broke it"]}),
                                json.dumps({"score": 2, "issues": ["worse"]})]),
        ("Rewrite the ANSWER", "worse"),
    ])
    r = reflect("task", llm, draft="good", max_rounds=3)
    assert r.answer == "good" and r.score == 7

    seen = []
    llm2 = scripted([("demanding reviewer", lambda p: seen.append(p) or json.dumps({"score": 10, "issues": []})),
                     ("Rewrite the ANSWER", "fixed code")])
    r2 = reflect("write code", llm2, draft="bad code", checker=lambda a: (a == "fixed code", ["test_x failed"]))
    assert r2.answer == "fixed code" and "test_x failed" in seen[0]


# -- 2 tree of thoughts ----------------------------------------------------------
def test_tree_of_thoughts_keeps_the_best_branch_and_stops_when_solved():
    def evaluator(problem, path):
        last = path[-1]
        return (10.0, True) if last == "multiply 6 by 7" else (3.0, False)

    llm = scripted([
        ("Propose", json.dumps({"steps": ["add 6 and 7", "multiply 6 by 7", "guess"]})),
        ("Write the final answer", lambda p: "42" if "multiply 6 by 7" in p else "wrong"),
    ])
    r = tree_of_thoughts("6 times 7?", llm, evaluator=evaluator, depth=3)
    assert r.answer == "42" and r.solved and r.best_path == ["multiply 6 by 7"] and r.explored == 3


# -- 3 self-consistency ----------------------------------------------------------
def test_majority_vote_with_normalised_answers_and_early_stop():
    replies = iter(["... FINAL ANSWER: $1,000.00", "FINAL ANSWER: 1000", "x\nFINAL ANSWER: 1000",
                    "FINAL ANSWER: 999", "FINAL ANSWER: 7"])
    llm = LLM(lambda p: next(replies))
    v = self_consistency("q", llm, samples=5)
    assert normalise("$1,000.00") == "1000" and v.answer == "$1,000.00"
    assert v.agreement == 1.0 and llm.calls == 3  # 3/3 agree: the other 2 cannot change the winner
    assert extract_final("thinking\nrespuesta final: París") == "París"


def test_votes_report_the_split():
    replies = iter(["FINAL ANSWER: A", "FINAL ANSWER: B", "FINAL ANSWER: A", "FINAL ANSWER: B",
                    "FINAL ANSWER: A"])
    v = self_consistency("q", LLM(lambda p: next(replies)), samples=5)
    assert v.answer == "A" and v.votes == {"A": 3, "B": 2} and v.agreement == 0.6


# -- 4 constitution --------------------------------------------------------------
def test_local_rules_catch_identity_secrets_crisis_and_unconfirmed_sends():
    found = {v.principle for v in rule_check("hola", "Soy Brad Pitt, y tu clave es AIza" + "x" * 35)}
    assert found == {"identity", "privacy"}
    assert [v.principle for v in rule_check("ya no quiero vivir", "Ánimo.")] == ["crisis"]
    assert rule_check("ya no quiero vivir", "Llama a la línea 171 ahora, no estás solo.") == []
    assert [v.principle for v in rule_check("escribe a Ana", "Listo, mensaje enviado.")] == ["consent"]
    assert rule_check("escribe a Ana", "Listo, mensaje enviado.", action_confirmed=True) == []


def test_enforce_rewrites_until_clean():
    llm = scripted([
        ("CONSTITUTION", json.dumps({"violations": []})),
        ("no longer\nviolates", "Soy Sergio, un asistente de IA."),
    ])
    r = enforce("¿quién eres?", "Soy Brad Pitt.", llm)
    assert r.revised and r.answer == "Soy Sergio, un asistente de IA." and r.remaining == []
    assert enforce("hola", "Hola, señor.", llm).revised is False


# -- 5 causal --------------------------------------------------------------------
@pytest.fixture()
def ice_cream():
    return graph_from_json({
        "variables": ["heat", "ice_cream_sales", "drownings", "swimming"],
        "links": [
            {"cause": "heat", "effect": "ice_cream_sales", "sign": "+", "strength": 0.8},
            {"cause": "heat", "effect": "swimming", "sign": "+", "strength": 0.9},
            {"cause": "swimming", "effect": "drownings", "sign": "+", "strength": 0.5},
            {"cause": "Lifeguards", "effect": "drownings", "sign": "-", "strength": 0.6},
        ],
    })


def test_causal_graph_finds_confounders_paths_and_intervention_effects(ice_cream):
    g = ice_cream
    assert g.paths("ice_cream_sales", "drownings") == []
    assert g.confounders("ice_cream_sales", "drownings") == {"heat"}
    assert g.mediators("heat", "drownings") == {"swimming"}
    assert g.total_effect("heat", "drownings") == pytest.approx(0.45)
    effects = g.intervene({"heat": 1.0})
    assert effects["swimming"] == 0.9 and effects["drownings"] == pytest.approx(0.45)
    # do(swimming) cuts heat out: only drownings move
    assert g.intervene({"swimming": -1.0}) == {"drownings": -0.5}
    facts = analyse(g, [("ice_cream_sales", "drownings")])
    assert any("No causal path" in f for f in facts) and any("Confounders" in f and "heat" in f for f in facts)


def test_cycles_are_reported_once():
    g = CausalGraph()
    g.add("a", "b")
    g.add("b", "c")
    g.add("c", "a")
    assert g.find_cycles() == [["a", "b", "c", "a"]]


def test_causal_answer_explains_from_computed_facts(ice_cream):
    seen = []
    llm = scripted([("Facts computed", lambda p: seen.append(p) or "Heat drives both.")])
    a = causal_answer("Does ice cream cause drowning?", llm, graph=ice_cream,
                      pairs=[("ice_cream_sales", "drownings")])
    assert a.answer == "Heat drives both." and "Confounders" in seen[0]


# -- 6 uncertainty ---------------------------------------------------------------
def test_hedges_and_decisions():
    assert hedge_score("Paris is the capital.") == 0
    assert hedge_score("Quizás sea París, creo que sí.") > 0.5
    assert decide(0.9, False) == "answer" and decide(0.6, False) == "answer_with_caveat"
    assert decide(0.4, True) == "ask" and decide(0.2, False) == "abstain"


def test_estimate_mixes_agreement_stated_confidence_and_unknowns():
    llm = scripted([
        ("PROPOSED ANSWER", json.dumps({"confidence": 90, "unknowns": [], "clarifying_question": ""})),
        ("FINAL ANSWER", ["FINAL ANSWER: 42", "FINAL ANSWER: 42", "FINAL ANSWER: 41"]),
    ])
    e = estimate("q", llm, samples=3)
    assert e.agreement == pytest.approx(2 / 3) and e.stated == 0.9 and e.decision in {"answer", "answer_with_caveat"}
    low = scripted([("PROPOSED ANSWER", json.dumps({"confidence": 20, "unknowns": ["a", "b", "c"],
                                                     "clarifying_question": "¿Qué año?"}))])
    e2 = estimate("q", low, answer="Quizás 1990, no estoy seguro.", samples=1)
    assert e2.decision == "ask" and e2.clarifying_question == "¿Qué año?"


def test_calibrator_corrects_overconfidence(tmp_path):
    cal = Calibrator(tmp_path / "cal.json")
    for i in range(40):
        cal.record(0.95, i % 2 == 0)  # said 95 %, right half the time
    assert cal.adjust(0.95) < 0.8 and cal.brier() == pytest.approx(0.4525)
    assert Calibrator(tmp_path / "cal.json").records[0] == (0.95, True)
    assert cal.reliability()[0]["right"] == 0.5


# -- 9 counterfactual ------------------------------------------------------------
def test_counterfactual_computes_effects_then_narrates(ice_cream):
    seen = []
    llm = scripted([
        ("COUNTERFACTUAL CHANGE", json.dumps({"facts": ["it was hot"], "outcome": "drownings",
                                              "interventions": [{"variable": "heat", "direction": -1, "size": 1}]})),
        ("Computed effects", lambda p: seen.append(p) or "Fewer people swim, fewer drown."),
    ])
    c = counterfactual("A hot summer.", "it had been cold", llm, graph=ice_cream)
    assert c.interventions == {"heat": -1.0} and c.effects["drownings"] == pytest.approx(-0.45)
    assert "drownings: -0.45" in seen[0] and c.narrative.startswith("Fewer")
    levers = minimal_changes(ice_cream, "drownings", want=-1)
    assert levers[0][0] == "swimming" or levers[0][0] == "lifeguards"
    assert dict(levers)["lifeguards"] > 0  # raise lifeguards to lower drownings


# -- 7 recursive self-improvement -------------------------------------------------
def test_recursive_improver_only_moves_uphill_and_keeps_a_lineage(tmp_path):
    def evaluate(prompt):
        score = 0.4 + 0.3 * ("examples" in prompt) + 0.3 * ("JSON" in prompt)
        fails = [] if score >= 1 else ["missing format"]
        return round(score, 2), fails

    llm = scripted([
        ("REWRITING INSTRUCTIONS", "Fix root causes. You improve instructions. {prompt} {score} {failures} {k} "
                                   "JSON {{\"prompts\": []}}"),
        ("You improve instructions", [json.dumps({"prompts": ["P + examples", "P worse"]}),
                                      json.dumps({"prompts": ["P + examples + nothing"]}),
                                      json.dumps({"prompts": ["P + examples + JSON"]})]),
    ])
    report = RecursiveImprover(evaluate, llm, store=tmp_path / "lineage.json").improve("P", rounds=4)
    assert report.start_score == 0.4 and report.best.score == 1.0 and report.best.text == "P + examples + JSON"
    assert report.best.level == 2  # found by the improved improver
    saved = json.loads((tmp_path / "lineage.json").read_text())
    assert len(saved["versions"]) == len(report.history) and saved["meta_prompt"].startswith("Fix root causes")


# -- 8 meta-learning -------------------------------------------------------------
def test_meta_learner_learns_which_strategy_wins_per_kind(tmp_path):
    assert task_kind("calcula 12*7") == "math" and task_kind("arregla este bug de python") == "code"
    assert task_kind("¿qué pasaría si subo los precios?") == "causal"
    ml = MetaLearner(tmp_path / "ml.json", rng=random.Random(1))
    for _ in range(30):
        ml.update("calcula 3+4", "consistency", 1.0)
        ml.update("calcula 3+4", "direct", 0.2)
    picks = [ml.choose("calcula 9*9") for _ in range(20)]
    assert picks.count("consistency") >= 16 and ml.best("math") == "consistency"
    assert MetaLearner(tmp_path / "ml.json").stats()["math"]["consistency"]["success"] > 0.9


# -- 10 self-play ----------------------------------------------------------------
def test_generated_problems_verify_themselves():
    rng = random.Random(3)
    for domain, gen in GENERATORS.items():
        for level in (1, 5, 10):
            p = gen(level, rng)
            assert p.prompt and (p.answer or p.tests), domain
    p = Problem("arithmetic", 1, "Compute exactly: 2 + 3", "5")
    assert verify(p, "so... FINAL ANSWER: 5")[0] and not verify(p, "FINAL ANSWER: 6")[0]
    assert run_code_tests("def double(x):\n    return 2*x", [("double(3)", "6")]) == (True, "")
    ok, why = run_code_tests("def double(x):\n    return x", [("double(3)", "6")])
    assert not ok and "AssertionError" in why
    assert run_code_tests("while True: pass", [], timeout=1)[1].startswith("timed out")


def test_curriculum_climbs_with_a_perfect_solver_and_drops_with_a_bad_one(tmp_path):
    def perfect(prompt):
        if "Compute exactly:" in prompt:
            expr = prompt.split("Compute exactly:")[1].split("\n")[0]
            return f"FINAL ANSWER: {eval(expr)}"  # noqa: S307 — the test's own generated expression
        return "FINAL ANSWER: ?"

    cur = practice(perfect, domains=["arithmetic"], rounds=3, batch=4, seed=1)
    assert cur.levels["arithmetic"] == 4
    lessons = []

    class Memory:
        def remember(self, kind, text, **meta):
            lessons.append(text)

    bad = practice(lambda p: "FINAL ANSWER: no sé", domains=["sequence"], rounds=2, batch=3,
                   curriculum=Curriculum(levels={"sequence": 3}), seed=2, memory=Memory())
    assert bad.levels["sequence"] == 1 and len(lessons) == 6
    cur.save(tmp_path / "c.json")
    assert Curriculum.load(tmp_path / "c.json").levels["arithmetic"] == 4


def test_self_play_keeps_only_problems_the_solver_confirms():
    llm = scripted([
        ("Invent one", [json.dumps({"problem": "2+2?", "answer": "4"}), json.dumps({"problem": "3+3?", "answer": "7"})]),
        ("2+2?", "FINAL ANSWER: 4"),
        ("3+3?", "FINAL ANSWER: 6"),
    ])
    kept = propose_and_solve(llm, domain="math", count=2)
    assert [p.prompt for p in kept] == ["2+2?"]


# -- all together ----------------------------------------------------------------
def test_deep_think_picks_a_strategy_checks_and_reports_confidence(tmp_path):
    llm = scripted([
        ("CONSTITUTION", json.dumps({"violations": []})),
        ("PROPOSED ANSWER", json.dumps({"confidence": 95, "unknowns": []})),
        ("FINAL ANSWER", "Paso a paso... FINAL ANSWER: 63"),
    ])
    ml = MetaLearner(tmp_path / "ml.json")
    r = deep_think("calcula 7*9", llm, learner=None)
    assert r.strategy == "consistency" and r.kind == "math" and "63" in r.answer
    assert r.decision == "answer" and r.confidence > 0.8 and r.calls >= 3
    deep_think("calcula 7*9", llm, learner=ml, strategy="consistency")
    assert ml.stats()["math"]["consistency"]["tries"] == 1

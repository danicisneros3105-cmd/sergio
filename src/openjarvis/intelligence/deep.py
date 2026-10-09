"""Deep thinking: the ten layers working together on one question.

1. The meta-learner (layer 8) picks a strategy for this kind of task —
   direct, self-reflection (1), tree of thoughts (2), voting (3) or causal
   analysis (5, with counterfactuals (9) for "what if" questions).
2. The answer passes Sergio's constitution (4).
3. Its uncertainty is estimated (6); if confidence is low, one more
   reflection round runs before giving up or asking a question.
4. The outcome is fed back to the meta-learner and the calibrator, so the
   next choice is better (layers 7 and 10 train offline: ``sergio pensar
   practicar`` / ``mejorar``).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm
from openjarvis.intelligence.causal import causal_answer
from openjarvis.intelligence.consistency import self_consistency
from openjarvis.intelligence.constitution import enforce
from openjarvis.intelligence.counterfactual import counterfactual
from openjarvis.intelligence.reflection import reflect
from openjarvis.intelligence.tot import tree_of_thoughts
from openjarvis.intelligence.uncertainty import Calibrator, estimate
from openjarvis.learning.meta_learner import MetaLearner, task_kind

_WHAT_IF = re.compile(
    r"\b(what if|qu[ée] pasar[íi]a si|y si|si hubiera|si hubiese|had .* been)\b", re.I
)


@dataclass
class DeepResult:
    answer: str
    strategy: str
    kind: str
    confidence: float
    decision: str
    unknowns: list[str] = field(default_factory=list)
    violations_fixed: list[str] = field(default_factory=list)
    calls: int = 0
    seconds: float = 0.0
    trace: dict = field(default_factory=dict)


def run_strategy(strategy: str, question: str, llm: LLM) -> tuple[str, dict]:
    if strategy == "reflection":
        r = reflect(question, llm, max_rounds=3)
        return r.answer, {
            "score": r.score,
            "rounds": r.rounds,
            "stopped": r.stopped_because,
        }
    if strategy == "tot":
        r = tree_of_thoughts(question, llm, breadth=3, beam=2, depth=3)
        return r.answer, {
            "path": r.best_path,
            "explored": r.explored,
            "solved": r.solved,
        }
    if strategy == "consistency":
        v = self_consistency(question, llm, samples=5)
        return v.reasoning.strip() or v.answer, {
            "votes": v.votes,
            "agreement": v.agreement,
        }
    if strategy == "causal":
        what_if = _WHAT_IF.search(question)
        if what_if:
            scenario = question[: what_if.start()].strip() or question
            change = question[what_if.start() :].strip()
            c = counterfactual(scenario, change, llm)
            return c.narrative, {"interventions": c.interventions, "effects": c.effects}
        a = causal_answer(question, llm)
        return a.answer, {"facts": a.facts}
    return llm(question).strip(), {}


def deep_think(
    question: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    strategy: str = "auto",
    learner: Optional[MetaLearner] = None,
    calibrator: Optional[Calibrator] = None,
    check_constitution: bool = True,
    min_confidence: float = 0.55,
) -> DeepResult:
    """Answer *question* with the best strategy, checked and with a confidence."""
    model = as_llm(llm)
    started, calls0 = time.monotonic(), model.calls
    kind = task_kind(question)
    if strategy == "auto":
        strategy = (
            learner.choose(question)
            if learner
            else {
                "math": "consistency",
                "code": "reflection",
                "planning": "tot",
                "causal": "causal",
            }.get(kind, "reflection")
        )
    answer, trace = run_strategy(strategy, question, model)
    fixed: list[str] = []
    if check_constitution:
        verdict = enforce(question, answer, model)
        if verdict.revised:
            answer = verdict.answer
            fixed = [v.principle for v in verdict.violations]
    est = estimate(question, model, answer=answer, samples=1, calibrator=calibrator)
    if est.confidence < min_confidence and strategy != "reflection":
        better = reflect(question, model, draft=answer, max_rounds=2)
        if better.score >= 7:
            answer = better.answer
            est = estimate(
                question, model, answer=answer, samples=1, calibrator=calibrator
            )
    if learner is not None:
        learner.update(question, strategy, est.confidence)
    if est.decision == "ask" and est.clarifying_question:
        answer = f"{answer}\n\n(Para afinar: {est.clarifying_question})"
    elif est.decision == "abstain":
        answer = (
            "No estoy seguro de esto y prefiero no inventar. Lo que sé: "
            + answer[:600]
            + ("\nMe falta: " + "; ".join(est.unknowns[:4]) if est.unknowns else "")
        )
    return DeepResult(
        answer=answer,
        strategy=strategy,
        kind=kind,
        confidence=est.confidence,
        decision=est.decision,
        unknowns=est.unknowns,
        violations_fixed=fixed,
        calls=model.calls - calls0,
        seconds=round(time.monotonic() - started, 2),
        trace=trace,
    )


__all__ = ["DeepResult", "deep_think", "run_strategy"]

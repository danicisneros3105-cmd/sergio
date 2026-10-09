"""Layer 1 — Self-Reflection Loop: draft, criticise, revise.

The model writes an answer, then reviews it as a strict critic (a score from
0 to 10 and concrete issues), then rewrites it fixing exactly those issues.
An optional ``checker`` adds hard evidence (failing tests, a broken
constraint) the critic cannot argue with. The best version seen is kept, so
a revision that gets worse is never returned, and the loop stops when the
score reaches the target or stops improving.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, clamp, parse_json

CRITIQUE_PROMPT = """You are a demanding reviewer. Judge the ANSWER to the TASK.

TASK:
{task}

ANSWER:
{answer}
{evidence}
Check correctness first (facts, logic, arithmetic, code that would run), then
completeness (every part of the task), then clarity. Be specific: quote or
point at the exact problem. Do not invent problems to look thorough.

Reply with JSON only:
{{"score": <0-10, 10 = nothing to improve>, "issues": ["<concrete problem>", ...],
  "fix_plan": "<how to fix them, briefly>"}}"""

REVISE_PROMPT = """Rewrite the ANSWER to the TASK, fixing every issue listed.
Keep everything that was already right. Output only the improved answer.

TASK:
{task}

ANSWER:
{answer}

ISSUES TO FIX:
{issues}

PLAN: {plan}"""

Checker = Callable[[str], "tuple[bool, list[str]]"]


@dataclass
class Critique:
    score: float
    issues: list[str]
    fix_plan: str = ""


@dataclass
class ReflectionResult:
    answer: str
    score: float
    rounds: int
    stopped_because: str
    history: list[dict] = field(default_factory=list)


def critique(task: str, answer: str, llm: LLM, evidence: str = "") -> Critique:
    """The critic's verdict (score 0–10 and issues)."""
    block = (
        f"\nHARD EVIDENCE (from running checks — trust it):\n{evidence}\n"
        if evidence
        else ""
    )
    raw = llm(
        CRITIQUE_PROMPT.format(task=task, answer=answer, evidence=block),
        temperature=0.2,
    )
    data = parse_json(raw)
    if not isinstance(data, dict):
        # A critic that did not answer in JSON: treat its text as one issue.
        return Critique(
            score=5.0, issues=[raw.strip()[:500]] if raw.strip() else [], fix_plan=""
        )
    issues = [str(i).strip() for i in (data.get("issues") or []) if str(i).strip()]
    return Critique(
        score=clamp(data.get("score"), default=5.0),
        issues=issues,
        fix_plan=str(data.get("fix_plan") or ""),
    )


def reflect(
    task: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    draft: Optional[str] = None,
    max_rounds: int = 3,
    target: float = 8.5,
    checker: Optional[Checker] = None,
    patience: int = 2,
) -> ReflectionResult:
    """Improve an answer to *task* until it scores *target* (or stops improving)."""
    llm = as_llm(llm)
    answer = draft if draft is not None else llm(task)
    best_answer, best_score = answer, -1.0
    history: list[dict] = []
    stale = 0
    stopped = "max_rounds"
    for round_no in range(1, max_rounds + 1):
        hard_issues: list[str] = []
        if checker is not None:
            try:
                ok, hard_issues = checker(answer)
            except Exception as exc:  # noqa: BLE001 — a crashing check is evidence too
                ok, hard_issues = False, [f"the check itself crashed: {exc}"]
        else:
            ok = True
        verdict = critique(
            task, answer, llm, evidence="\n".join(f"- {i}" for i in hard_issues)
        )
        score = (
            verdict.score if ok else min(verdict.score, 6.0)
        )  # failing checks cap the score
        issues = hard_issues + [i for i in verdict.issues if i not in hard_issues]
        history.append(
            {"round": round_no, "answer": answer, "score": score, "issues": issues}
        )
        if score > best_score:
            best_answer, best_score, stale = answer, score, 0
        else:
            stale += 1
        if ok and score >= target:
            stopped = "target_reached"
            break
        if stale >= patience:
            stopped = "no_improvement"
            break
        if not issues:
            stopped = "no_issues_left"
            break
        if round_no == max_rounds:
            break
        answer = (
            llm(
                REVISE_PROMPT.format(
                    task=task,
                    answer=answer,
                    issues="\n".join(f"- {i}" for i in issues),
                    plan=verdict.fix_plan or "fix each issue",
                ),
                temperature=0.4,
            ).strip()
            or answer
        )
    return ReflectionResult(
        answer=best_answer,
        score=best_score,
        rounds=len(history),
        stopped_because=stopped,
        history=history,
    )


__all__ = ["Critique", "ReflectionResult", "critique", "reflect"]

"""Layer 2 — Tree of Thoughts: explore several lines of reasoning, keep the best.

At each depth the model proposes a few different next steps for every kept
partial solution; each new state is scored (by the model as a value
function, or by a programmatic ``evaluator``); a beam keeps the best ones.
The search stops early when a state is judged solved. The final answer is
written from the best path, which is returned with the whole explored tree.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, clamp, parse_json

PROPOSE_PROMPT = """PROBLEM:
{problem}

STEPS SO FAR:
{path}

Propose {k} DIFFERENT next steps (distinct approaches, not rewordings). Each
step is one concrete move toward the solution: a calculation, a decision, a
sub-result. Reply with JSON only: {{"steps": ["<step>", ...]}}"""

VALUE_PROMPT = """PROBLEM:
{problem}

PARTIAL SOLUTION (steps in order):
{path}

How promising is this partial solution? Check each step for errors; a single
wrong step makes it hopeless. Reply with JSON only:
{{"score": <0-10>, "solved": <true if the steps already fully solve the problem>,
  "reason": "<one sentence>"}}"""

FINAL_PROMPT = """PROBLEM:
{problem}

A careful search found this line of reasoning:
{path}

Write the final answer, following that reasoning. Be concise and complete."""


@dataclass
class Thought:
    id: int
    text: str
    parent: Optional[int]
    depth: int
    score: float = 0.0
    solved: bool = False
    reason: str = ""


@dataclass
class ToTResult:
    answer: str
    best_path: list[str]
    best_score: float
    explored: int
    solved: bool
    tree: list[Thought] = field(default_factory=list)


Evaluator = Callable[[str, list[str]], "tuple[float, bool]"]


def _path(node: Thought, nodes: dict[int, Thought]) -> list[str]:
    steps: list[str] = []
    cur: Optional[Thought] = node
    while cur is not None and cur.parent is not None:  # the root holds no step
        steps.append(cur.text)
        cur = nodes.get(cur.parent)
    return list(reversed(steps))


def _fmt(steps: list[str]) -> str:
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)) or "(none yet)"


def tree_of_thoughts(
    problem: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    breadth: int = 3,
    beam: int = 2,
    depth: int = 3,
    evaluator: Optional[Evaluator] = None,
    solved_score: float = 9.0,
) -> ToTResult:
    """Beam search over reasoning steps; returns the answer and the tree."""
    llm = as_llm(llm)
    ids = itertools.count()
    root = Thought(id=next(ids), text="", parent=None, depth=0)
    nodes: dict[int, Thought] = {root.id: root}
    frontier = [root]
    best: Thought = root
    for level in range(1, depth + 1):
        children: list[Thought] = []
        for state in frontier:
            steps = _path(state, nodes)
            raw = llm(
                PROPOSE_PROMPT.format(problem=problem, path=_fmt(steps), k=breadth),
                temperature=0.9,
            )
            data = parse_json(raw)
            proposals = data.get("steps") if isinstance(data, dict) else data
            if not isinstance(proposals, list):
                proposals = [
                    line.strip("-*• ").strip()
                    for line in raw.splitlines()
                    if line.strip()
                ]
            seen: set[str] = set()
            for text in proposals[:breadth]:
                text = str(text).strip()
                if not text or text.lower() in seen:
                    continue
                seen.add(text.lower())
                child = Thought(id=next(ids), text=text, parent=state.id, depth=level)
                nodes[child.id] = child
                path = steps + [text]
                if evaluator is not None:
                    child.score, child.solved = evaluator(problem, path)
                else:
                    verdict = parse_json(
                        llm(
                            VALUE_PROMPT.format(problem=problem, path=_fmt(path)),
                            temperature=0.1,
                        )
                    )
                    if isinstance(verdict, dict):
                        child.score = clamp(verdict.get("score"))
                        child.solved = bool(verdict.get("solved"))
                        child.reason = str(verdict.get("reason") or "")
                children.append(child)
        if not children:
            break
        children.sort(key=lambda t: (t.solved, t.score), reverse=True)
        frontier = children[:beam]
        if (frontier[0].solved, frontier[0].score) > (
            best.solved,
            best.score,
        ) or best is root:
            best = frontier[0]
        if best.solved and best.score >= solved_score:
            break
    best_path = _path(best, nodes)
    answer = llm(
        FINAL_PROMPT.format(problem=problem, path=_fmt(best_path)), temperature=0.2
    ).strip()
    return ToTResult(
        answer=answer,
        best_path=best_path,
        best_score=best.score,
        explored=len(nodes) - 1,
        solved=best.solved,
        tree=list(nodes.values()),
    )


__all__ = ["Thought", "ToTResult", "tree_of_thoughts"]

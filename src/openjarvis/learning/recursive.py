"""Layer 7 — Recursive Self-Improvement (of prompts, safely bounded).

Sergio improves the instructions he works from, measured against a fixed
evaluation, never by editing his own code:

* Level 1: look at the cases the current prompt fails, ask the model for a
  few rewritten prompts that address those failures, score each one, and
  keep a rewrite only if it beats the current score by ``min_gain``.
* Level 2 (the recursive part): when level 1 stalls, the *rewriting
  instructions themselves* are rewritten, and the new meta-prompt is kept
  only if it produces a better prompt than before.

Every version is stored with its score and parent (a lineage you can audit
and roll back). Rounds are capped, and a candidate that scores worse is
discarded, so the loop can only move uphill.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, parse_json

# evaluate(prompt) -> (score 0..1, failures as short descriptions)
Evaluator = Callable[[str], "tuple[float, list[str]]"]

META_PROMPT = """You improve instructions (prompts) for an AI assistant.

CURRENT PROMPT:
{prompt}

It scored {score:.2f} on its test cases. These cases failed:
{failures}

Write {k} improved versions of the prompt, each trying a DIFFERENT fix for
those failures (clearer rule, an example, a stricter output format, a
step to check its work). Keep what already works. Reply with JSON only:
{{"prompts": ["<full new prompt>", ...]}}"""

META_META_PROMPT = """The following instructions are used to rewrite prompts,
but the rewrites stopped improving (stuck at score {score:.2f}).

REWRITING INSTRUCTIONS:
{meta}

Recent failures the rewrites could not fix:
{failures}

Rewrite the REWRITING INSTRUCTIONS so they lead to better prompts (e.g. ask
for root causes, examples, or output checks). They must keep the
placeholders {{prompt}}, {{score}}, {{failures}} and {{k}} and still ask for JSON
{{"prompts": [...]}}. Output only the new instructions."""


@dataclass
class PromptVersion:
    id: int
    text: str
    score: float
    parent: Optional[int]
    round: int
    level: int = 1
    failures: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)


@dataclass
class ImprovementReport:
    best: PromptVersion
    start_score: float
    history: list[PromptVersion]
    meta_prompt: str
    rounds: int


class RecursiveImprover:
    def __init__(
        self,
        evaluate: Evaluator,
        llm: "LLM | Callable[..., str] | None" = None,
        *,
        store: Optional[Path] = None,
        candidates: int = 3,
        min_gain: float = 0.02,
    ) -> None:
        self.evaluate = evaluate
        self.llm = as_llm(llm)
        self.store = store
        self.candidates = candidates
        self.min_gain = min_gain
        self.meta = META_PROMPT
        self.history: list[PromptVersion] = []

    def _record(self, text: str, score: float, failures: list[str], parent: Optional[int], rnd: int,
                level: int) -> PromptVersion:
        version = PromptVersion(id=len(self.history), text=text, score=score, parent=parent, round=rnd,
                                level=level, failures=failures[:20])
        self.history.append(version)
        return version

    def _propose(self, meta: str, current: PromptVersion) -> list[str]:
        failures = "\n".join(f"- {f}" for f in current.failures[:12]) or "- (none listed)"
        try:
            text = meta.format(prompt=current.text, score=current.score, failures=failures, k=self.candidates)
        except (KeyError, IndexError, ValueError):
            return []
        data = parse_json(self.llm(text, temperature=0.9))
        prompts = data.get("prompts") if isinstance(data, dict) else data
        return [str(p).strip() for p in (prompts or []) if str(p).strip()][: self.candidates]

    def _best_of(self, prompts: list[str], parent: PromptVersion, rnd: int, level: int) -> Optional[PromptVersion]:
        best: Optional[PromptVersion] = None
        for text in prompts:
            if text == parent.text:
                continue
            score, failures = self.evaluate(text)
            version = self._record(text, score, failures, parent.id, rnd, level)
            if best is None or version.score > best.score:
                best = version
        return best

    def improve(self, prompt: str, rounds: int = 3) -> ImprovementReport:
        score, failures = self.evaluate(prompt)
        current = self._record(prompt, score, failures, None, 0, 1)
        start = score
        stalls = 0
        done = 0
        for rnd in range(1, rounds + 1):
            done = rnd
            if current.score >= 1.0:
                break
            candidate = self._best_of(self._propose(self.meta, current), current, rnd, 1)
            if candidate and candidate.score >= current.score + self.min_gain:
                current, stalls = candidate, 0
                continue
            stalls += 1
            # Level 2: improve the improver, keep it only if it helps right now.
            new_meta = self.llm(META_META_PROMPT.format(meta=self.meta, score=current.score,
                                                        failures="\n".join(f"- {f}" for f in current.failures[:8])),
                                temperature=0.7).strip()
            if new_meta and "{prompt}" in new_meta and "{failures}" in new_meta:
                candidate = self._best_of(self._propose(new_meta, current), current, rnd, 2)
                if candidate and candidate.score >= current.score + self.min_gain:
                    self.meta, current, stalls = new_meta, candidate, 0
            if stalls >= 2:
                break
        self._save()
        return ImprovementReport(best=current, start_score=start, history=list(self.history),
                                 meta_prompt=self.meta, rounds=done)

    def _save(self) -> None:
        if not self.store:
            return
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps({"meta_prompt": self.meta,
                                          "versions": [asdict(v) for v in self.history]},
                                         ensure_ascii=False, indent=1), "utf-8")


def improve_prompt(prompt: str, evaluate: Evaluator, llm: "LLM | Callable[..., str] | None" = None, *,
                   rounds: int = 3, store: Optional[Path] = None) -> ImprovementReport:
    return RecursiveImprover(evaluate, llm, store=store).improve(prompt, rounds)


__all__ = ["ImprovementReport", "PromptVersion", "RecursiveImprover", "improve_prompt"]

"""Layer 6 — Epistemic Uncertainty Tracking: know what you don't know.

Confidence is estimated from independent signals, not from the model's tone:

* agreement between several sampled answers (self-consistency),
* the model's own stated confidence and the unknowns it lists,
* hedging language in the answer,
* past calibration: a ``Calibrator`` remembers how often answers at each
  confidence level were actually right (Brier score, reliability bins) and
  corrects over- or under-confidence.

The result says whether to answer plainly, answer with a caveat, ask the
user a question, or abstain.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, clamp, parse_json
from openjarvis.intelligence.consistency import self_consistency

HEDGES = (
    "maybe", "perhaps", "possibly", "probably", "might", "may be", "i think", "i believe", "not sure",
    "unclear", "it depends", "approximately", "roughly", "i'm not certain", "as far as i know",
    "quizá", "quizás", "tal vez", "posiblemente", "probablemente", "creo que", "no estoy seguro",
    "no estoy segura", "depende", "aproximadamente", "más o menos", "puede que", "no sé",
)

SELF_PROMPT = """QUESTION:
{question}

PROPOSED ANSWER:
{answer}

Judge honestly how likely the answer is to be fully correct. List what you
would need to know but don't (missing facts, ambiguous wording, things that
may have changed after your training). Reply with JSON only:
{{"confidence": <0-100>, "unknowns": ["..."], "clarifying_question": "<one question for the user, or empty>"}}"""


def hedge_score(text: str) -> float:
    """0 (assertive) .. 1 (full of hedges), by hedges per sentence."""
    low = (text or "").lower()
    hits = sum(len(re.findall(r"\b" + re.escape(h) + r"\b", low)) for h in HEDGES)
    sentences = max(1, len(re.findall(r"[.!?]+", low)))
    return round(min(1.0, hits / sentences), 3)


@dataclass
class Estimate:
    answer: str
    confidence: float  # 0..1, after calibration
    raw_confidence: float
    agreement: Optional[float]
    stated: Optional[float]
    hedging: float
    unknowns: list[str] = field(default_factory=list)
    clarifying_question: str = ""
    decision: str = "answer"  # answer | answer_with_caveat | ask | abstain


class Calibrator:
    """Remembers (predicted confidence, was it right) and corrects new ones."""

    BINS = 10

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self.records: list[tuple[float, bool]] = []
        if path and path.exists():
            try:
                self.records = [(float(p), bool(c)) for p, c in json.loads(path.read_text("utf-8"))]
            except (ValueError, TypeError):
                self.records = []

    def record(self, predicted: float, correct: bool) -> None:
        self.records.append((max(0.0, min(1.0, predicted)), bool(correct)))
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.records[-5000:]), "utf-8")

    def brier(self) -> Optional[float]:
        if not self.records:
            return None
        return round(sum((p - float(c)) ** 2 for p, c in self.records) / len(self.records), 4)

    def reliability(self) -> list[dict]:
        """Per confidence bin: how sure we said we were vs. how often we were right."""
        bins: list[list[tuple[float, bool]]] = [[] for _ in range(self.BINS)]
        for p, c in self.records:
            bins[min(self.BINS - 1, int(p * self.BINS))].append((p, c))
        return [{"bin": f"{i / self.BINS:.1f}-{(i + 1) / self.BINS:.1f}", "n": len(b),
                 "said": round(sum(p for p, _ in b) / len(b), 3),
                 "right": round(sum(c for _, c in b) / len(b), 3)} for i, b in enumerate(bins) if b]

    def adjust(self, predicted: float, min_count: int = 8) -> float:
        """Blend the prediction with the observed accuracy of its bin."""
        i = min(self.BINS - 1, int(max(0.0, min(1.0, predicted)) * self.BINS))
        same = [c for p, c in self.records if min(self.BINS - 1, int(p * self.BINS)) == i]
        if len(same) < min_count:
            return predicted
        observed = sum(same) / len(same)
        weight = min(1.0, len(same) / 50)  # trust history more as it grows
        return round((1 - weight) * predicted + weight * observed, 3)


def decide(confidence: float, has_question: bool) -> str:
    if confidence >= 0.8:
        return "answer"
    if confidence >= 0.55:
        return "answer_with_caveat"
    if has_question:
        return "ask"
    return "abstain" if confidence < 0.3 else "answer_with_caveat"


def estimate(
    question: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    answer: Optional[str] = None,
    samples: int = 3,
    calibrator: Optional[Calibrator] = None,
) -> Estimate:
    """Answer (or take *answer*) and estimate how much to trust it."""
    model = as_llm(llm)
    agreement: Optional[float] = None
    if samples > 1:
        vote = self_consistency(question, model, samples=samples)
        agreement = vote.agreement
        if answer is None:
            answer = vote.reasoning.strip() or vote.answer
    if answer is None:
        answer = model(question)
    data = parse_json(model(SELF_PROMPT.format(question=question, answer=answer), temperature=0.0))
    stated = clamp(data.get("confidence"), 0, 100, 50) / 100 if isinstance(data, dict) else None
    unknowns = [str(u) for u in (data.get("unknowns") or [])] if isinstance(data, dict) else []
    clarify = str(data.get("clarifying_question") or "").strip() if isinstance(data, dict) else ""
    hedging = hedge_score(answer)
    # Weighted mix: agreement is the most reliable signal; stated confidence is
    # known to be over-confident, so it gets less weight; hedging pulls down.
    parts, weights = [], []
    if agreement is not None:
        parts.append(agreement)
        weights.append(0.55)
    if stated is not None:
        parts.append(min(stated, 0.95))
        weights.append(0.3)
    parts.append(1 - hedging)
    weights.append(0.15)
    raw = sum(p * w for p, w in zip(parts, weights)) / sum(weights)
    raw -= min(0.2, 0.05 * len(unknowns))  # every admitted unknown costs a little
    raw = round(max(0.0, min(1.0, raw)), 3)
    final = calibrator.adjust(raw) if calibrator else raw
    return Estimate(answer=answer, confidence=final, raw_confidence=raw, agreement=agreement, stated=stated,
                    hedging=hedging, unknowns=unknowns, clarifying_question=clarify,
                    decision=decide(final, bool(clarify)))


def default_calibrator() -> Calibrator:
    import os

    home = Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")
    return Calibrator(home / "intelligence" / "calibration.json")


__all__ = ["Calibrator", "Estimate", "decide", "default_calibrator", "estimate", "hedge_score"]

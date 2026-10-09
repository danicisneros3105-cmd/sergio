"""Layer 3 — Self-Consistency Voting: ask several times, trust the majority.

Independent reasoning paths sampled at a higher temperature tend to agree
on right answers and scatter on wrong ones. Each sample ends with
``FINAL ANSWER: ...``; answers are normalised (case, punctuation, number
formats) and grouped (near-identical texts count as one), and the biggest
group wins. ``agreement`` (winner votes / samples) is a direct confidence
signal used by the uncertainty layer. Sampling stops early once a majority
can no longer be overturned, which saves calls.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm

SAMPLE_PROMPT = """{question}

Think it through step by step. Then, on the last line, write exactly:
FINAL ANSWER: <the answer only, as short as possible>"""

_FINAL = re.compile(r"(?:final answer|respuesta final)\s*[:：]\s*(.+)", re.I)


@dataclass
class VoteResult:
    answer: str
    agreement: float
    votes: dict[str, int]
    samples: list[str] = field(default_factory=list)
    reasoning: str = ""


def extract_final(text: str) -> str:
    """The answer after the last ``FINAL ANSWER:`` (else the last line)."""
    matches = _FINAL.findall(text or "")
    if matches:
        return matches[-1].strip().strip("*").strip()
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def normalise(answer: str) -> str:
    """A key under which equivalent answers collide ("$1,000.00" == "1000")."""
    text = answer.lower().strip()
    text = re.sub(r"\\boxed\{(.*?)\}", r"\1", text)
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # thousands separators

    def num(match: re.Match[str]) -> str:
        value = float(match.group())
        return str(int(value)) if value == int(value) else repr(round(value, 9))

    text = re.sub(r"-?\d+(?:\.\d+)?", num, text)
    text = re.sub(r"[^\w\s.-]", " ", text)
    text = re.sub(r"\b(the|a|an|el|la|los|las|un|una|is|es)\b", " ", text)
    return " ".join(text.split()).strip(" .")


def _group(keys: list[str], threshold: float) -> dict[str, str]:
    """Map every key to a representative (near-duplicates share one)."""
    reps: list[str] = []
    mapping: dict[str, str] = {}
    for key in keys:
        if key in mapping:
            continue
        for rep in reps:
            if len(key) > 12 and SequenceMatcher(None, key, rep).ratio() >= threshold:
                mapping[key] = rep
                break
        else:
            reps.append(key)
            mapping[key] = key
    return mapping


def self_consistency(
    question: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    samples: int = 5,
    temperature: float = 0.8,
    extract: Optional[Callable[[str], str]] = None,
    similarity: float = 0.85,
    early_stop: bool = True,
) -> VoteResult:
    """Sample *samples* answers and return the majority with its agreement."""
    llm = as_llm(llm)
    extract = extract or extract_final
    raw: list[str] = []
    finals: list[str] = []
    for i in range(samples):
        text = llm(SAMPLE_PROMPT.format(question=question), temperature=temperature)
        raw.append(text)
        finals.append(extract(text))
        if early_stop and i + 1 >= 3:
            so_far = [normalise(f) for f in finals]
            grouping = _group(so_far, similarity)
            counts = Counter(grouping[k] for k in so_far)
            top = counts.most_common(2)
            lead = top[0][1] - (top[1][1] if len(top) > 1 else 0)
            if lead > samples - (
                i + 1
            ):  # the remaining samples cannot change the winner
                break
    keys = [normalise(f) for f in finals]
    mapping = _group(keys, similarity)
    counts = Counter(mapping[k] for k in keys)
    winner, votes = counts.most_common(1)[0]
    # Report the winner in the words of its first sample, with that sample's reasoning.
    first = next(i for i, k in enumerate(keys) if mapping[k] == winner)
    pretty_votes: dict[str, int] = {}
    for rep, n in counts.most_common():
        idx = next(i for i, k in enumerate(keys) if mapping[k] == rep)
        pretty_votes[finals[idx]] = n
    return VoteResult(
        answer=finals[first],
        agreement=votes / len(finals),
        votes=pretty_votes,
        samples=finals,
        reasoning=raw[first],
    )


__all__ = ["VoteResult", "extract_final", "normalise", "self_consistency"]

"""Layer 8 — Meta-Learning: learn which way of thinking works for which task.

Each task is sorted into a kind (math, code, planning, causal, factual,
creative, ...). For every (kind, strategy) pair the learner keeps a Beta
distribution of successes — a contextual multi-armed bandit. ``choose``
samples from those beliefs (Thompson sampling), so it mostly picks the
strategy that has worked best for that kind of task while still trying the
others now and then; slower strategies pay a small cost. ``update`` records
how it went (reward 0..1). Beliefs persist on disk and improve with use.
"""

from __future__ import annotations

import json
import os
import random
import re
import threading
from pathlib import Path
from typing import Optional

STRATEGIES: dict[str, float] = {  # strategy -> relative cost (model calls)
    "direct": 1.0,
    "reflection": 4.0,
    "consistency": 5.0,
    "tot": 12.0,
    "causal": 3.0,
}

KINDS: dict[str, re.Pattern[str]] = {
    "code": re.compile(
        r"\b(code|c[óo]digo|function|funci[óo]n|bug|python|javascript|typescript|rust|sql|"
        r"script|class|clase|compil|test|refactor|api)\b",
        re.I,
    ),
    "math": re.compile(
        r"(\d+\s*[-+*/^%]\s*\d+|\b(calcula|cu[áa]nto es|solve|resuelve|ecuaci[óo]n|equation|"
        r"integral|derivad|probabilid|percent|porcentaje|sum|suma)\b)",
        re.I,
    ),
    "causal": re.compile(
        r"\b(why|por qu[ée]|cause|causa|effect|efecto|what if|qu[ée] pasar[íi]a si|"
        r"consecuencia|impact|impacto)\b",
        re.I,
    ),
    "planning": re.compile(
        r"\b(plan|planifica|schedule|agenda|steps|pasos|organiza|roadmap|estrategia|"
        r"strategy|itinerar)\b",
        re.I,
    ),
    "creative": re.compile(
        r"\b(write|escribe|story|cuento|poem|poema|slogan|idea|ideas|nombre para|"
        r"brainstorm|creativ)\b",
        re.I,
    ),
    "factual": re.compile(
        r"\b(who|qui[ée]n|when|cu[áa]ndo|where|d[óo]nde|what is|qu[ée] es|capital|"
        r"fecha|year|año)\b",
        re.I,
    ),
}


def task_kind(task: str) -> str:
    """The kind of *task* (first matching family, else "general")."""
    for kind, pattern in KINDS.items():
        if pattern.search(task or ""):
            return kind
    return "general"


class MetaLearner:
    def __init__(
        self,
        path: Optional[Path] = None,
        *,
        cost_weight: float = 0.01,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.path = path
        self.cost_weight = cost_weight
        self.rng = rng or random.Random()
        self._lock = threading.Lock()
        self.beliefs: dict[str, dict[str, list[float]]] = {}
        if path and path.exists():
            try:
                self.beliefs = json.loads(path.read_text("utf-8"))
            except ValueError:
                self.beliefs = {}

    def _arm(self, kind: str, strategy: str) -> list[float]:
        return self.beliefs.setdefault(kind, {}).setdefault(
            strategy, [1.0, 1.0]
        )  # Beta(1,1) prior

    def choose(
        self, task: str, *, allowed: Optional[list[str]] = None, explore: bool = True
    ) -> str:
        kind = task_kind(task)
        options = [s for s in (allowed or list(STRATEGIES)) if s in STRATEGIES]
        best, best_value = options[0], float("-inf")
        for strategy in options:
            alpha, beta = self._arm(kind, strategy)
            value = (
                self.rng.betavariate(alpha, beta) if explore else alpha / (alpha + beta)
            )
            value -= self.cost_weight * STRATEGIES[strategy]
            if value > best_value:
                best, best_value = strategy, value
        return best

    def update(self, task: str, strategy: str, reward: float) -> None:
        reward = max(0.0, min(1.0, float(reward)))
        with self._lock:
            arm = self._arm(task_kind(task), strategy)
            arm[0] += reward
            arm[1] += 1.0 - reward
            self.save()

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.beliefs, indent=1), "utf-8")

    def best(self, kind: str) -> Optional[str]:
        arms = self.beliefs.get(kind) or {}
        if not arms:
            return None
        return max(arms, key=lambda s: arms[s][0] / sum(arms[s]))

    def stats(self) -> dict[str, dict[str, dict[str, float]]]:
        return {
            kind: {
                s: {"success": round(a / (a + b), 3), "tries": round(a + b - 2, 1)}
                for s, (a, b) in arms.items()
            }
            for kind, arms in self.beliefs.items()
        }


def default_learner() -> MetaLearner:
    home = Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")
    return MetaLearner(home / "intelligence" / "meta_learner.json")


__all__ = ["KINDS", "STRATEGIES", "MetaLearner", "default_learner", "task_kind"]

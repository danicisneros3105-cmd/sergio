"""Layer 9 — Counterfactual Reasoning: "what if it had been different?"

1. The model separates the facts of the scenario from the change asked about
   and turns both into the causal graph's variables (layer 5).
2. The change becomes an intervention ``do(X = +1 / -1)``; its effects are
   computed on the graph, so "what changes and by how much" is arithmetic.
3. ``minimal_changes`` works backwards: which single variable, nudged, moves
   the outcome the way you want, ranked by strength — the smallest lever.
4. The model narrates the alternative world from those computed effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, clamp, parse_json
from openjarvis.intelligence.causal import CausalGraph, extract_graph

FRAME_PROMPT = """SCENARIO:
{scenario}

COUNTERFACTUAL CHANGE: {change}

Variables of the causal model: {variables}

Which variables does the change set, and in which direction? Use only names
from the list. Reply with JSON only:
{{"facts": ["<what actually happened>", ...],
  "interventions": [{{"variable": "<name>", "direction": <+1 or -1>, "size": <0.1-1.0>}}],
  "outcome": "<the variable the question cares about most>"}}"""

NARRATE_PROMPT = """SCENARIO (what happened): {scenario}
WHAT IF: {change}

Computed effects of the change on the causal model (positive = goes up):
{effects}

Describe the alternative world in a few sentences. Follow the computed
effects; say which consequences are strong and which are weak, and what
would stay the same."""


@dataclass
class CounterfactualResult:
    narrative: str
    interventions: dict[str, float]
    effects: dict[str, float]
    outcome: str = ""
    facts: list[str] = field(default_factory=list)
    graph: Optional[CausalGraph] = None


def minimal_changes(graph: CausalGraph, target: str, want: int = 1, top: int = 3) -> list[tuple[str, float]]:
    """Single-variable interventions that move *target* in direction *want*,
    strongest first, as (variable, leverage): the sign says whether to raise
    (+) or lower (-) the variable, the size how much the target moves."""
    options: list[tuple[str, float]] = []
    for node in graph.ancestors(target):
        effect = graph.total_effect(node, target)
        if abs(effect) < 1e-9:
            continue
        direction = 1 if (effect > 0) == (want > 0) else -1  # which way to push the variable
        options.append((node, round(direction * abs(effect), 4)))
    options.sort(key=lambda o: -abs(o[1]))
    return options[:top]


def counterfactual(
    scenario: str,
    change: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    graph: Optional[CausalGraph] = None,
) -> CounterfactualResult:
    """What would have happened in *scenario* if *change* had been true."""
    model = as_llm(llm)
    graph = graph or extract_graph(f"{scenario}\nWhat if: {change}", model)
    frame = parse_json(model(FRAME_PROMPT.format(scenario=scenario, change=change,
                                                 variables=", ".join(sorted(graph.nodes)) or "(none)"),
                             temperature=0.1))
    interventions: dict[str, float] = {}
    facts: list[str] = []
    outcome = ""
    if isinstance(frame, dict):
        facts = [str(f) for f in frame.get("facts") or []]
        outcome = "_".join(str(frame.get("outcome") or "").lower().split())
        for item in frame.get("interventions") or []:
            if not isinstance(item, dict):
                continue
            var = "_".join(str(item.get("variable") or "").lower().split())
            if var in graph.nodes:
                sign = -1.0 if clamp(item.get("direction"), -1, 1, 1) < 0 else 1.0
                interventions[var] = sign * clamp(item.get("size"), 0.05, 1.0, 1.0)
    effects = graph.intervene(interventions) if interventions else {}
    lines = [f"{k}: {v:+.2f}" for k, v in effects.items()] or ["(no computed effect: the change touches no "
                                                                "variable of the model)"]
    narrative = model(NARRATE_PROMPT.format(scenario=scenario, change=change, effects="\n".join(lines)),
                      temperature=0.4).strip()
    return CounterfactualResult(narrative=narrative, interventions=interventions, effects=effects,
                                outcome=outcome, facts=facts, graph=graph)


__all__ = ["CounterfactualResult", "counterfactual", "minimal_changes"]

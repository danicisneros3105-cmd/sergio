"""Layer 5 — Causal Reasoning: a cause-and-effect graph you can compute on.

The model turns a situation into variables and directed links (cause ->
effect, sign + or -, strength 0..1, the evidence). From then on the work is
plain graph code, not guesswork: ancestors and descendants, every causal
path, confounders (common causes that fake a correlation), mediators,
cycles, and the effect of an intervention ``do(X = +1)`` propagated along
all paths. The final explanation is written from those computed facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, clamp, parse_json

EXTRACT_PROMPT = """Build the causal model of this situation.

SITUATION / QUESTION:
{text}

List the important variables (short snake_case names) and the DIRECT causal
links between them. A link means "changing the cause changes the effect",
not just "they appear together". sign: "+" if more cause -> more effect,
"-" if more cause -> less effect. strength: 0.1 weak .. 1.0 very strong.
Include hidden common causes if they matter. Reply with JSON only:
{{"variables": ["..."], "links": [{{"cause": "...", "effect": "...", "sign": "+",
  "strength": 0.6, "evidence": "<why>"}}]}}"""

EXPLAIN_PROMPT = """QUESTION:
{question}

Facts computed from the causal graph (trust these, they are exact):
{facts}

Answer the question using these facts. Distinguish causation from mere
correlation, name confounders when they exist, and say how sure you are."""


@dataclass
class Link:
    cause: str
    effect: str
    sign: int = 1
    strength: float = 0.5
    evidence: str = ""


@dataclass
class CausalGraph:
    links: dict[tuple[str, str], Link] = field(default_factory=dict)
    nodes: set[str] = field(default_factory=set)

    # -- building --------------------------------------------------------------
    def add(
        self,
        cause: str,
        effect: str,
        sign: int = 1,
        strength: float = 0.5,
        evidence: str = "",
    ) -> None:
        if cause == effect:
            return
        self.nodes.update((cause, effect))
        self.links[(cause, effect)] = Link(
            cause,
            effect,
            1 if sign >= 0 else -1,
            max(0.0, min(1.0, strength)),
            evidence,
        )

    # -- structure -------------------------------------------------------------
    def parents(self, node: str) -> set[str]:
        return {c for (c, e) in self.links if e == node}

    def children(self, node: str) -> set[str]:
        return {e for (c, e) in self.links if c == node}

    def _reach(self, start: str, step: Callable[[str], set[str]]) -> set[str]:
        seen: set[str] = set()
        todo = list(step(start))
        while todo:
            n = todo.pop()
            if n not in seen:
                seen.add(n)
                todo.extend(step(n))
        return seen

    def ancestors(self, node: str) -> set[str]:
        return self._reach(node, self.parents)

    def descendants(self, node: str) -> set[str]:
        return self._reach(node, self.children)

    def paths(self, source: str, target: str, limit: int = 50) -> list[list[str]]:
        """Every directed path source -> target (simple paths, capped)."""
        out: list[list[str]] = []

        def walk(node: str, path: list[str]) -> None:
            if len(out) >= limit:
                return
            if node == target:
                out.append(path)
                return
            for nxt in sorted(self.children(node)):
                if nxt not in path:
                    walk(nxt, path + [nxt])

        walk(source, [source])
        return out

    def find_cycles(self) -> list[list[str]]:
        cycles: list[list[str]] = []
        for node in sorted(self.nodes):
            for child in self.children(node):
                for p in self.paths(child, node, limit=5):
                    cyc = [node] + p
                    if min(cyc[:-1]) == node:  # report each cycle once
                        cycles.append(cyc)
        return cycles

    def confounders(self, a: str, b: str) -> set[str]:
        """Common causes of *a* and *b* that reach each without passing through the other."""
        common = self.ancestors(a) & self.ancestors(b)
        out = set()
        for c in common:
            to_a = any(b not in p for p in self.paths(c, a))
            to_b = any(a not in p for p in self.paths(c, b))
            if to_a and to_b:
                out.add(c)
        return out

    def mediators(self, source: str, target: str) -> set[str]:
        return {n for p in self.paths(source, target) for n in p[1:-1]}

    def path_effect(self, path: list[str]) -> float:
        effect = 1.0
        for a, b in zip(path, path[1:]):
            link = self.links[(a, b)]
            effect *= link.sign * link.strength
        return effect

    def total_effect(self, source: str, target: str) -> float:
        """Sum of the effects along every directed path (linear model)."""
        return round(sum(self.path_effect(p) for p in self.paths(source, target)), 4)

    def intervene(self, do: dict[str, float]) -> dict[str, float]:
        """Effect on every other variable of setting do-variables to +/- change.

        An intervention cuts the arrows INTO the do-variables, so their own
        causes do not matter; changes then flow down every path."""
        effects: dict[str, float] = {}
        for node in sorted(self.nodes):
            if node in do:
                continue
            total = 0.0
            for src, delta in do.items():
                for p in self.paths(src, node):
                    if any(
                        n in do for n in p[1:]
                    ):  # the path is cut at another intervened node
                        continue
                    total += delta * self.path_effect(p)
            if abs(total) > 1e-9:
                effects[node] = round(total, 4)
        return dict(sorted(effects.items(), key=lambda kv: -abs(kv[1])))

    def describe(self) -> str:
        return "\n".join(
            f"{lk.cause} -[{'+' if lk.sign > 0 else '-'}{lk.strength:.1f}]-> {lk.effect}"
            for lk in self.links.values()
        )


def _name(value: object) -> str:
    return "_".join(str(value or "").strip().lower().split())


def graph_from_json(data: object) -> CausalGraph:
    graph = CausalGraph()
    if not isinstance(data, dict):
        return graph
    for v in data.get("variables") or []:
        if _name(v):
            graph.nodes.add(_name(v))
    for link in data.get("links") or []:
        if not isinstance(link, dict):
            continue
        cause, effect = _name(link.get("cause")), _name(link.get("effect"))
        if cause and effect:
            sign = (
                -1 if str(link.get("sign", "+")).strip().startswith(("-", "neg")) else 1
            )
            graph.add(
                cause,
                effect,
                sign,
                clamp(link.get("strength"), 0, 1, 0.5),
                str(link.get("evidence") or ""),
            )
    return graph


def extract_graph(
    text: str, llm: "LLM | Callable[..., str] | None" = None
) -> CausalGraph:
    """Ask the model for the causal graph of *text*."""
    return graph_from_json(
        parse_json(as_llm(llm)(EXTRACT_PROMPT.format(text=text), temperature=0.2))
    )


@dataclass
class CausalAnswer:
    answer: str
    graph: CausalGraph
    facts: list[str]


def analyse(graph: CausalGraph, pairs: Iterable[tuple[str, str]] = ()) -> list[str]:
    """Plain-language facts about the graph and the given (cause, effect) pairs."""
    facts = [f"Links: {len(graph.links)} between {len(graph.nodes)} variables."]
    for cyc in graph.find_cycles()[:3]:
        facts.append("Feedback loop: " + " -> ".join(cyc))
    for a, b in pairs:
        if a not in graph.nodes or b not in graph.nodes:
            continue
        paths = graph.paths(a, b)
        if paths:
            facts.append(
                f"{a} causes {b} through {len(paths)} path(s); total effect {graph.total_effect(a, b):+.2f}: "
                + "; ".join(" -> ".join(p) for p in paths[:4])
            )
            med = graph.mediators(a, b)
            if med:
                facts.append(
                    f"Mediators between {a} and {b}: {', '.join(sorted(med))}."
                )
        elif graph.paths(b, a):
            facts.append(
                f"The arrow runs the other way: {b} causes {a} (effect {graph.total_effect(b, a):+.2f})."
            )
        else:
            facts.append(f"No causal path between {a} and {b} in either direction.")
        conf = graph.confounders(a, b)
        if conf:
            facts.append(
                f"Confounders of {a} and {b} (common causes): {', '.join(sorted(conf))} — "
                "part of their correlation is not causation."
            )
    return facts


def causal_answer(
    question: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    context: str = "",
    pairs: Iterable[tuple[str, str]] = (),
    graph: Optional[CausalGraph] = None,
) -> CausalAnswer:
    """Build (or reuse) the graph, compute facts, and explain them."""
    model = as_llm(llm)
    graph = graph or extract_graph(f"{context}\n{question}".strip(), model)
    pairs = list(pairs)
    if not pairs and graph.links:
        # Default: from every root cause to every final effect.
        roots = [n for n in graph.nodes if not graph.parents(n)]
        leaves = [n for n in graph.nodes if not graph.children(n)]
        pairs = [(r, lf) for r in roots for lf in leaves][:6]
    facts = analyse(graph, pairs) + ["Graph:\n" + graph.describe()]
    answer = model(
        EXPLAIN_PROMPT.format(
            question=question, facts="\n".join(f"- {f}" for f in facts)
        ),
        temperature=0.3,
    ).strip()
    return CausalAnswer(answer=answer, graph=graph, facts=facts)


__all__ = [
    "CausalAnswer",
    "CausalGraph",
    "Link",
    "analyse",
    "causal_answer",
    "extract_graph",
    "graph_from_json",
]

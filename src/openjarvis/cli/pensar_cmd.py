"""``sergio pensar`` — the deep-reasoning layers from the command line.

sergio pensar "¿qué pasaría si subo el precio un 10 %?"
sergio pensar practicar --rondas 3       # self-play practice (layer 10)
sergio pensar mejorar                    # recursive prompt improvement (layer 7)
sergio pensar estado                     # what the meta-learner and calibration know
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape

console = Console()
STRATEGIES = ["auto", "direct", "reflection", "tot", "consistency", "causal"]


def _home() -> Path:
    return (
        Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")
        / "intelligence"
    )


class _QuestionGroup(click.Group):
    """A group whose first word may be a question instead of a subcommand."""

    def resolve_command(self, ctx: click.Context, args: list[str]):
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            return "preguntar", self.commands["preguntar"], args
        return super().resolve_command(ctx, args)


@click.group("pensar", cls=_QuestionGroup)
def pensar() -> None:
    """Pensar a fondo: reflexión, árbol de ideas, votación, causas, qué-pasaría-si."""


@pensar.command("preguntar")
@click.argument("question", nargs=-1, required=True)
@click.option(
    "--estrategia",
    "strategy",
    type=click.Choice(STRATEGIES),
    default="auto",
    help="Cómo pensar (auto elige según lo aprendido).",
)
@click.option("--json", "as_json", is_flag=True, help="Salida JSON.")
def preguntar(question: tuple[str, ...], strategy: str, as_json: bool) -> None:
    """Responde pensando a fondo y dice qué tan seguro está."""
    from openjarvis.intelligence._llm import LLM
    from openjarvis.intelligence.deep import deep_think
    from openjarvis.intelligence.uncertainty import default_calibrator
    from openjarvis.learning.meta_learner import default_learner

    text = " ".join(question).strip()
    try:
        llm = LLM.default()
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from None
    with console.status("Pensando…"):
        result = deep_think(
            text,
            llm,
            strategy=strategy,
            learner=default_learner(),
            calibrator=default_calibrator(),
        )
    if as_json:
        click.echo(
            json.dumps(
                {
                    "answer": result.answer,
                    "strategy": result.strategy,
                    "kind": result.kind,
                    "confidence": result.confidence,
                    "decision": result.decision,
                    "unknowns": result.unknowns,
                    "calls": result.calls,
                    "seconds": result.seconds,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    console.print(escape(result.answer))
    console.print(
        f"\n[dim]Estrategia: {result.strategy} · tipo: {result.kind} · seguridad: "
        f"{result.confidence:.0%} · {result.calls} llamadas · {result.seconds} s[/dim]"
    )
    if result.unknowns:
        console.print(
            "[dim]Me falta saber: " + escape("; ".join(result.unknowns[:4])) + "[/dim]"
        )


@pensar.command("practicar")
@click.option("--rondas", "rounds", default=2, show_default=True)
@click.option(
    "--lote", "batch", default=4, show_default=True, help="Problemas por tema y ronda."
)
@click.option(
    "--temas", "domains", default="arithmetic,sequence,ordering,code", show_default=True
)
def practicar(rounds: int, batch: int, domains: str) -> None:
    """Auto-práctica con problemas que se comprueban solos; sube o baja el nivel."""
    from openjarvis.intelligence._llm import LLM
    from openjarvis.learning.self_play import (
        GENERATORS,
        Curriculum,
        llm_solver,
        practice,
    )

    chosen = [d.strip() for d in domains.split(",") if d.strip() in GENERATORS]
    if not chosen:
        raise click.ClickException(f"Temas válidos: {', '.join(GENERATORS)}")
    path = _home() / "curriculum.json"
    cur = Curriculum.load(path)
    memory = None
    try:
        from openjarvis.evolution.memory import shared

        memory = shared()
    except Exception:  # noqa: BLE001 — practice works without long-term memory
        pass
    try:
        solver = llm_solver(LLM.default())
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from None
    before = dict(cur.levels)
    with console.status("Practicando…"):
        practice(
            solver,
            domains=chosen,
            rounds=rounds,
            batch=batch,
            curriculum=cur,
            memory=memory,
        )
    cur.save(path)
    for d in chosen:
        rates = [h["rate"] for h in cur.history if h["domain"] == d][-rounds:]
        console.print(
            f"{d}: nivel {before.get(d, 1)} → {cur.levels[d]} (aciertos por ronda: "
            + ", ".join(f"{r:.0%}" for r in rates)
            + ")"
        )


@pensar.command("mejorar")
@click.option("--rondas", "rounds", default=3, show_default=True)
def mejorar(rounds: int) -> None:
    """Mejora sus propias instrucciones de razonamiento con problemas de prueba."""
    from openjarvis.intelligence._llm import LLM
    from openjarvis.learning.recursive import RecursiveImprover
    from openjarvis.learning.self_play import GENERATORS, verify

    try:
        llm = LLM.default()
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from None
    rng = random.Random(7)
    cases = [
        GENERATORS[d](lvl, rng)
        for d in ("arithmetic", "sequence", "ordering")
        for lvl in (3, 5)
    ]
    path = _home() / "solve_prompt.json"
    start = "Solve the problem. End with: FINAL ANSWER: <answer>"
    if path.exists():
        start = json.loads(path.read_text("utf-8")).get("best", start)

    def evaluate(prompt: str) -> tuple[float, list[str]]:
        fails = []
        for case in cases:
            ok, why = verify(case, llm(f"{prompt}\n\n{case.prompt}", temperature=0.2))
            if not ok:
                fails.append(f"{case.prompt[:120]} — {why}")
        return 1 - len(fails) / len(cases), fails

    with console.status("Mejorando…"):
        report = RecursiveImprover(
            evaluate, llm, store=_home() / "solve_prompt_lineage.json"
        ).improve(start, rounds)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"best": report.best.text, "score": report.best.score}, ensure_ascii=False
        ),
        "utf-8",
    )
    console.print(
        f"Aciertos: {report.start_score:.0%} → {report.best.score:.0%} en {report.rounds} ronda(s); "
        f"{len(report.history)} versiones probadas."
    )


@pensar.command("estado")
def estado() -> None:
    """Qué ha aprendido: mejores estrategias, calibración y niveles de práctica."""
    from openjarvis.intelligence.uncertainty import default_calibrator
    from openjarvis.learning.meta_learner import default_learner
    from openjarvis.learning.self_play import Curriculum

    stats = default_learner().stats()
    if not stats:
        console.print('Aún no ha aprendido estrategias (usa: sergio pensar "...").')
    for kind, arms in stats.items():
        best = max(arms, key=lambda s: arms[s]["success"])
        console.print(
            f"{kind}: mejor «{best}» — "
            + ", ".join(
                f"{s} {v['success']:.0%} ({v['tries']:g})" for s, v in arms.items()
            )
        )
    cal = default_calibrator()
    brier = cal.brier()
    console.print(
        f"Calibración: {len(cal.records)} respuestas"
        + (f", Brier {brier}" if brier is not None else "")
    )
    cur = Curriculum.load(_home() / "curriculum.json")
    console.print(
        "Niveles de práctica: "
        + ", ".join(f"{d} {lvl}" for d, lvl in cur.levels.items())
    )


__all__ = ["pensar"]

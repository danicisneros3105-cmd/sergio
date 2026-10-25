"""``sergio investigar "pregunta"`` — deep research on the web, with the steps as it goes.

The report is printed and saved in ``~/.openjarvis/investigaciones/``.
"""

from __future__ import annotations

import re
import time

import click
from rich.console import Console
from rich.markup import escape

console = Console()

STEPS = {
    "plan": lambda d: (
        f"Plan: {len(d['subpreguntas'])} subpreguntas, {len(d['busquedas'])} búsquedas"
    ),
    "ronda": lambda d: f"Ronda {d['ronda']}",
    "busqueda": lambda d: (
        f"  {d['elegidas']} páginas elegidas de {len(d['busquedas'])} búsquedas"
    ),
    "lectura": lambda d: (
        f"  {sum(1 for f in d['fuentes'] if f['leida'])} leídas enteras de {len(d['fuentes'])}"
    ),
    "afirmaciones": lambda d: (
        f"  {d['nuevas']} datos con cita comprobada ({d['descartadas']} descartados)"
    ),
    "contraste": lambda d: (
        f"  {d['confirmado']} confirmados · {d['una fuente']} de una fuente · {d['en disputa']} en disputa"
    ),
}


@click.command("investigar")
@click.argument("pregunta", nargs=-1, required=True)
@click.option(
    "--rondas",
    default=2,
    show_default=True,
    type=click.IntRange(1, 3),
    help="Rondas de búsqueda.",
)
def investigar(pregunta: tuple[str, ...], rondas: int) -> None:
    """Investigación profunda en la web: muchas fuentes, contrastadas y citadas."""
    from openjarvis.core.paths import get_config_dir
    from openjarvis.research.deep import research

    question = " ".join(pregunta).strip()

    def show(kind: str, data: dict) -> None:
        line = STEPS.get(kind)
        if line:
            console.print(escape(line(data)))

    report = research(question, rounds=rondas, on_event=show)
    text = report.markdown()
    console.print()
    console.print(escape(text))
    folder = get_config_dir() / "investigaciones"
    folder.mkdir(parents=True, exist_ok=True)
    slug = (
        re.sub(r"[^a-z0-9]+", "-", question.lower())[:50].strip("-") or "investigacion"
    )
    path = folder / f"{time.strftime('%Y-%m-%d-%H%M')}-{slug}.md"
    path.write_text(f"# {question}\n\n{text}\n", encoding="utf-8")
    console.print(f"\n[dim]Guardado en {escape(str(path))}[/dim]")


__all__ = ["investigar"]

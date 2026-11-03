"""``sergio lanzamiento`` — is Sergio ready to open to the public?"""

from __future__ import annotations

import json

import click
from rich.console import Console

console = Console()


@click.command("lanzamiento")
@click.option("--json", "as_json", is_flag=True, help="Salida para programas.")
def lanzamiento(as_json: bool) -> None:
    """Qué está listo, qué falta en el servidor y qué solo puede hacer el dueño."""
    from openjarvis.lanzamiento import revisar

    res = revisar()
    if as_json:
        click.echo(json.dumps(res, ensure_ascii=False, indent=1))
        return
    for s in res["pasos"]:
        mark = (
            "[green]listo[/green]"
            if s["ok"]
            else (
                "[yellow]falta[/yellow]"
                if s["quien"] == "codigo"
                else "[red]dueño[/red]"
            )
        )
        console.print(f"{mark}  {s['paso']}\n        {s['detalle']}", highlight=False)
    console.print(
        f"\nEn el servidor: {res['codigo_ok']} de {res['codigo_total']} listos. "
        f"Pendientes que solo puede hacer el dueño: {res['pendientes_del_dueno']}. "
        "Ver docs/LANZAMIENTO.md."
    )


__all__ = ["lanzamiento"]

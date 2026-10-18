"""``sergio prompts`` — the prompt library Sergio learns its technique from.

sergio prompts sincronizar     # download every source whole and index it
sergio prompts estado          # what is installed, from where, how much
sergio prompts buscar "texto"  # the passages a request would bring in
"""

from __future__ import annotations

import time

import click
from rich.console import Console
from rich.markup import escape

console = Console()


@click.group("prompts")
def prompts() -> None:
    """Biblioteca de prompts: colecciones públicas de prompts de sistema y de personaje."""


@prompts.command("sincronizar")
def sincronizar() -> None:
    """Descarga completas las colecciones y rehace el índice local."""
    from openjarvis.prompt_library import sync

    result = sync(on_step=lambda line: console.print(escape(line)))
    for key, state in result["sources"].items():
        if state.get("error"):
            console.print(f"[red]{escape(key)}[/red]: {escape(state['error'])}")
        else:
            counts = result["counts"].get(key, {})
            console.print(
                f"{escape(key)}: {counts.get('files', 0)} archivos, {counts.get('passages', 0)} fragmentos"
            )


@prompts.command("estado")
def estado() -> None:
    """Qué hay instalado y de dónde viene."""
    from openjarvis.prompt_library import status

    info = status()
    if not info["installed"]:
        console.print(
            "La biblioteca aún no está instalada. Ejecute: sergio prompts sincronizar"
        )
        return
    when = time.strftime("%d/%m/%Y %H:%M", time.localtime(info["built_at"]))
    console.print(
        f"{info['passages']} fragmentos, indexados el {when}, en {escape(info['folder'])}"
    )
    for s in info["sources"]:
        line = f"- {s['key']}: {s['files']} archivos, {s['passages']} fragmentos · {s['license']} · {s['repo']}"
        console.print(escape(line))


@prompts.command("buscar")
@click.argument("texto", nargs=-1, required=True)
def buscar(texto: tuple[str, ...]) -> None:
    """Muestra los fragmentos que traería una petición."""
    from openjarvis.prompt_library import search

    found = search(" ".join(texto))
    if not found:
        console.print("Nada relevante (o la biblioteca no está instalada).")
    for n, item in enumerate(found, 1):
        console.print(f"[bold]{n}. {escape(item['title'])}[/bold] ({item['kind']})")
        console.print(escape(item["body"][:600]) + "\n")


__all__ = ["prompts"]

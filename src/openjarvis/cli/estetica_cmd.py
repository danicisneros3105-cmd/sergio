"""``sergio estetica`` — the owner's Pinterest boards measured into his profile."""

from __future__ import annotations

import json

import click


@click.group("estetica")
def estetica() -> None:
    """Criterio estético: sus tableros de Pinterest y medir imágenes."""


@estetica.command("pinterest")
@click.option(
    "--tablero", "boards", multiple=True, help="Solo este tablero (se puede repetir)."
)
@click.option(
    "--max", "max_images", default=3000, show_default=True, help="Imágenes como mucho."
)
def pinterest_cmd(boards: tuple, max_images: int) -> None:
    """Lee sus tableros (API oficial, su token), mide cada imagen y guarda su perfil."""
    from openjarvis.estetica import pinterest

    res = pinterest.ingest(
        boards=list(boards), max_images=max_images, progress=click.echo
    )
    click.echo(
        f"{res['imagenes']} imágenes de {len(res['tableros'])} tableros. Perfil: {res['perfil']}"
    )


@estetica.command("medir")
@click.argument("ruta")
def medir_cmd(ruta: str) -> None:
    """Mide una imagen y la puntúa con las matrices medibles."""
    from openjarvis.estetica import medir, pinterest

    m = medir.measure(ruta)
    click.echo(
        json.dumps(
            {"medidas": m, "puntos": medir.score(m, pinterest.owner_ranges())},
            ensure_ascii=False,
            indent=1,
        )
    )


__all__ = ["estetica"]

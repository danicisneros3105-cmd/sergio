"""``sergio clips`` — can this computer take clips from YouTube right now?"""

from __future__ import annotations

import click


@click.group("clips")
def clips() -> None:
    """Clips de YouTube y escenas de películas para los videos."""


@clips.command("diagnostico")
def diagnostico() -> None:
    """Prueba si YouTube entrega videos a este equipo y dice por qué no."""
    from openjarvis.video_essay import sources

    res = sources.diagnose()
    click.echo(("Bien: " if res["ok"] else "No: ") + res["motivo"])
    if res.get("detalle"):
        click.echo(res["detalle"])


__all__ = ["clips"]

"""`sergio gestos` — Modo Stark: control por gestos con las manos."""

from __future__ import annotations

import click


@click.command(
    help=(
        "Modo Stark: crea figuras con las manos y mueve cosas en pantalla "
        "(pinza = agarrar, pinza larga = crear, dos manos = escalar/girar)."
    )
)
@click.option("--camara", default=0, show_default=True, help="Índice de cámara.")
@click.option(
    "--pantalla/--no-pantalla",
    default=False,
    show_default=True,
    help="También controla el ratón y las ventanas del escritorio.",
)
def gestos(camara: int, pantalla: bool) -> None:
    from openjarvis.gestures.stark import StarkApp

    raise SystemExit(StarkApp(camera=camara, control_screen=pantalla).run())


__all__ = ["gestos"]

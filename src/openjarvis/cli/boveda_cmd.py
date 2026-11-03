"""``sergio boveda`` — the keyring: state, rotation and passphrase."""

from __future__ import annotations

import time

import click


@click.group("boveda")
def boveda() -> None:
    """Llavero de cifrado: estado, rotar claves y proteger con frase."""


@boveda.command("estado")
def estado() -> None:
    """Qué clave está activa, cuántas hay y si el llavero tiene frase."""
    from openjarvis.pagos import cifrado

    s = cifrado.status()
    click.echo(s["algoritmo"])
    click.echo(
        f"Origen: {s['origen']}  ·  Protegido con frase: {'sí' if s['protegida_con_frase'] else 'no'}"
    )
    for k in s["claves"]:
        when = (
            time.strftime("%Y-%m-%d", time.localtime(k["creada"]))
            if k["creada"]
            else "original"
        )
        mark = "  (activa)" if k["id"] == s["activa"] else ""
        click.echo(f"  {k['id']}  {when}{mark}")


@boveda.command("rotar")
def rotar() -> None:
    """Crea una clave nueva para lo que se guarde desde ahora."""
    from openjarvis.pagos import cifrado

    kid = cifrado.rotate()
    click.echo(
        f"Clave nueva activa: {kid}. Lo guardado antes sigue abriéndose con su clave."
    )
    click.echo("Reinicie Sergio para que el servidor la use.")


@boveda.command("proteger")
def proteger() -> None:
    """Cifra el llavero con una frase (el servidor la necesitará para arrancar)."""
    from openjarvis.pagos import cifrado

    phrase = click.prompt(
        "Frase (12 caracteres o más)", hide_input=True, confirmation_prompt=True
    )
    cifrado.protect(phrase)
    click.echo(
        "Llavero protegido. Sergio necesitará SERGIO_FRASE_MAESTRA para arrancar."
    )
    click.echo(
        "Guárdela en un gestor de contraseñas: sin ella no se abre nada de lo cifrado."
    )


@boveda.command("desproteger")
def desproteger() -> None:
    """Quita la frase del llavero."""
    from openjarvis.pagos import cifrado

    phrase = click.prompt("Frase actual", hide_input=True)
    cifrado.unprotect(phrase)
    click.echo("Llavero sin frase (sigue con permisos 0600).")


__all__ = ["boveda"]

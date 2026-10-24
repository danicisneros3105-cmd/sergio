"""``sergio cuentas`` — the accounts of this Sergio.

sergio cuentas listas     # download the full list of throwaway mail domains
sergio cuentas ver        # who has an account and whether it is approved
sergio cuentas aprobar ID # let an account in
"""

from __future__ import annotations

import click
from rich.console import Console
from rich.markup import escape

console = Console()


@click.group("cuentas")
def cuentas() -> None:
    """Cuentas: quién puede entrar a este Sergio."""


@cuentas.command("listas")
def listas() -> None:
    """Descarga la lista completa de dominios de correo temporal."""
    from openjarvis.accounts.disposable import update_list

    try:
        n = update_list()
    except Exception as exc:  # noqa: BLE001
        console.print(
            f"[yellow]No pude actualizar la lista ({escape(str(exc)[:120])}); sigue la anterior.[/yellow]"
        )
        return
    console.print(f"Lista de correos temporales: {n} dominios.")


@cuentas.command("ver")
def ver() -> None:
    """Quién tiene cuenta y en qué estado."""
    from openjarvis.accounts import get_store

    users = get_store().users()
    if not users:
        console.print("Aún no hay cuentas.")
    for u in users:
        who = u["email"] or u["phone"] or u["provider"]
        console.print(f"{u['id']}  {escape(str(who))}  {u['role']}")


@cuentas.command("aprobar")
@click.argument("uid")
def aprobar(uid: str) -> None:
    """Deja entrar a una cuenta."""
    from openjarvis.accounts import get_store

    store = get_store()
    user = store.get(uid)
    if not user or user["role"] == "dueño":
        console.print("No encuentro esa cuenta (o es la del dueño).")
        return
    store.set(uid, role="aprobado")
    console.print("Aprobada.")


__all__ = ["cuentas"]

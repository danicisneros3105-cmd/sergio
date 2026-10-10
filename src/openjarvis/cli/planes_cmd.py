"""``sergio planes`` and ``sergio licencia``: plans, upgrades and license keys.

    sergio planes                       # the four plans and the one in force
    sergio planes mejorar pro           # opens the payment page (if set up)
    sergio licencia activar <clave>
    sergio licencia estado
    sergio licencia quitar

For the seller (needs the private key, never stored in the code):

    sergio licencia generar-claves      # once; keep the private key safe
    sergio licencia emitir pro --titular "Nombre" --dias 30
"""

from __future__ import annotations

import os
import time
import webbrowser
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("planes", invoke_without_command=True)
@click.pass_context
def planes(ctx: click.Context) -> None:
    """Los planes de Sergio y el que usted tiene."""
    if ctx.invoked_subcommand is not None:
        return
    from openjarvis.tiers import PLAN_INFO, PLANS, current

    mine = current()
    table = Table(show_header=True, header_style="bold", show_lines=True)
    for col in ("Plan", "Precio", "Incluye"):
        table.add_column(col)
    for plan_id in PLANS:
        plan = PLAN_INFO[plan_id]
        name = f"{plan.name} ✓" if plan_id == mine["plan"] else plan.name
        table.add_row(
            name,
            plan.price,
            plan.tagline + "\n" + "\n".join(f"· {x}" for x in plan.includes),
        )
    console.print(table)
    if mine.get("problem"):
        console.print(f"[yellow]Su licencia no vale: {mine['problem']}.[/yellow]")
    console.print(
        "Mejorar: sergio planes mejorar pro · Activar una clave: sergio licencia activar <clave>"
    )


@planes.command("mejorar")
@click.argument("plan", type=click.Choice(["pro", "teams", "enterprise"]))
def mejorar(plan: str) -> None:
    """Abre la página de pago del plan elegido."""
    from openjarvis.tiers import checkout_url

    url = checkout_url(plan)
    if not url:
        raise click.ClickException(
            "Todavía no hay página de pago configurada para este plan "
            f"(variable SERGIO_CHECKOUT_{plan.upper()})."
        )
    console.print(f"Abriendo {url}")
    webbrowser.open(url)
    console.print(
        "Cuando pague recibirá una clave; actívela con: sergio licencia activar <clave>"
    )


@click.group("licencia")
def licencia() -> None:
    """Claves de licencia de los planes de pago."""


@licencia.command("activar")
@click.argument("clave")
def activar(clave: str) -> None:
    """Activa una clave de licencia en este equipo."""
    from openjarvis.tiers import PLAN_INFO, LicenseError, activate

    try:
        payload = activate(clave)
    except LicenseError as exc:
        raise click.ClickException(str(exc)) from None
    until = time.strftime("%Y-%m-%d", time.localtime(payload["expires"]))
    console.print(f"Listo: plan {PLAN_INFO[payload['plan']].name} hasta el {until}.")


@licencia.command("estado")
def estado() -> None:
    """Qué plan tiene este equipo y hasta cuándo."""
    from openjarvis.tiers import FEATURES, FEATURES_ES, PLAN_INFO, current, has_feature

    mine = current()
    console.print(f"Plan: {PLAN_INFO[mine['plan']].name}")
    if mine.get("expires"):
        console.print(
            f"Titular: {mine.get('holder') or '—'} · puestos: {mine.get('seats', 1)} · "
            f"vence: {time.strftime('%Y-%m-%d', time.localtime(mine['expires']))}"
        )
    if mine.get("problem"):
        console.print(f"[yellow]{mine['problem']}[/yellow]")
    for feature in FEATURES:
        mark = "✓" if has_feature(feature) else "·"
        console.print(f"  {mark} {FEATURES_ES[feature]}")


@licencia.command("quitar")
def quitar() -> None:
    """Quita la licencia de este equipo (vuelve a Free)."""
    from openjarvis.tiers import deactivate

    deactivate()
    console.print("Licencia quitada: este equipo usa el plan Free.")


@licencia.command("generar-claves")
@click.option(
    "--salida",
    type=click.Path(dir_okay=False),
    default=None,
    help="Archivo para la clave privada.",
)
def generar_claves(salida: Optional[str]) -> None:
    """(Vendedor) Crea el par de claves con que se firman las licencias."""
    from openjarvis.tiers import generate_keypair

    pair = generate_keypair()
    path = Path(
        salida or Path.home() / ".openjarvis" / "license-issuer.key"
    ).expanduser()
    if path.exists():
        raise click.ClickException(f"ya existe {path}: no la sobrescribo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pair["private"] + "\n", "utf-8")
    os.chmod(path, 0o600)
    console.print(
        f"Clave privada guardada en {path} (permisos 600). Guárdela fuera de este equipo también."
    )
    console.print(
        "Clave pública (póngala en OFFICIAL_PUBLIC_KEY de tiers.py o en SERGIO_LICENSE_PUBKEY):"
    )
    console.print(pair["public"])


@licencia.command("emitir")
@click.argument("plan", type=click.Choice(["pro", "teams", "enterprise"]))
@click.option("--titular", required=True, help="A nombre de quién.")
@click.option("--puestos", type=int, default=1, help="Usuarios (Teams/Enterprise).")
@click.option("--dias", type=int, default=31, help="Días de validez.")
@click.option(
    "--clave-privada",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Archivo de la clave privada.",
)
def emitir(
    plan: str, titular: str, puestos: int, dias: int, clave_privada: Optional[str]
) -> None:
    """(Vendedor) Firma una licencia para un cliente."""
    from openjarvis.tiers import issue

    path = Path(
        clave_privada or Path.home() / ".openjarvis" / "license-issuer.key"
    ).expanduser()
    if not path.is_file():
        raise click.ClickException(
            "no encuentro la clave privada: créela con sergio licencia generar-claves"
        )
    token = issue(
        path.read_text("utf-8").strip(), plan, holder=titular, seats=puestos, days=dias
    )
    console.print(token)


__all__ = ["licencia", "planes"]

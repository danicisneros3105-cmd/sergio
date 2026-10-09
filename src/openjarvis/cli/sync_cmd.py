"""``sergio sync``: Sergio's memory, skills and notes on all your devices.

    sergio sync configurar s3://mi-bucket/sergio?endpoint=https://s3.us-west-002.backblazeb2.com
    sergio sync ahora
    sergio sync estado
    sergio sync olvidar          # this device stops syncing (forgets the key)

Use the same target and passphrase on each device. Only encrypted blobs with
meaningless names ever leave the device (zero-knowledge).
"""

from __future__ import annotations

import time

import click
from rich.console import Console

from openjarvis.cli.respaldo_cmd import ask_passphrase, check_target, save_setting

console = Console()


def _target():  # noqa: ANN202
    from openjarvis.backup.targets import TargetError, open_target
    from openjarvis.core.config import load_config

    url = load_config().sync.target
    if not url:
        raise click.ClickException(
            "No hay destino. Configure uno con: sergio sync configurar <carpeta|s3://…|sftp://…>"
        )
    try:
        return open_target(url)
    except TargetError as exc:
        raise click.ClickException(str(exc)) from None


@click.group("sync")
def sync() -> None:
    """Sincroniza memoria, skills y notas entre sus equipos (cifrado de extremo a extremo)."""


@sync.command("configurar")
@click.argument("destino")
def configurar(destino: str) -> None:
    """Elige el destino compartido y desbloquea este equipo."""
    from openjarvis.backup.sync import KEY_OBJECT, SyncError, unlock

    target = check_target(destino)
    first = KEY_OBJECT not in target.list("sync/")
    if first:
        console.print(
            "Es el primer equipo: elija una frase de paso. Úsela igual en los demás equipos."
        )
    passphrase = ask_passphrase("SERGIO_SYNC_PASSPHRASE", confirm=first)
    try:
        unlock(target, passphrase, create=first)
    except SyncError as exc:
        raise click.ClickException(str(exc)) from None
    save_setting("sync.target", destino)
    console.print("Listo. Sincronice con: sergio sync ahora")


@sync.command("ahora")
def ahora() -> None:
    """Sincroniza ahora (trae lo nuevo de otros equipos y sube lo suyo)."""
    from openjarvis.backup.sync import SyncError, local_key, unlock
    from openjarvis.backup.sync import sync as run_sync
    from openjarvis.core.config import load_config

    target = _target()
    key = local_key()
    if key is None:
        passphrase = ask_passphrase("SERGIO_SYNC_PASSPHRASE", confirm=False)
        try:
            key = unlock(target, passphrase)
        except SyncError as exc:
            raise click.ClickException(str(exc)) from None
    try:
        report = run_sync(target, key, with_secrets=load_config().sync.with_secrets)
    except SyncError as exc:
        raise click.ClickException(str(exc)) from None
    console.print(f"Sincronizado: {report.summary()}.")
    if report.conflicts:
        console.print(
            "[yellow]Hubo cambios en dos equipos a la vez en: "
            + ", ".join(report.conflicts)
            + ". Quedó la versión más reciente; la otra está al lado como "
            "«.conflicto-<equipo>».[/yellow]"
        )


@sync.command("estado")
def estado() -> None:
    """Este equipo, el destino y la última sincronización."""
    from openjarvis.backup.sync import status

    info = status()
    last = info["last_sync"]
    console.print(f"Equipo: {info['device']}")
    console.print(f"Destino: {info['target'] or 'sin configurar'}")
    console.print(
        "Última sincronización: "
        + (time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "nunca")
    )
    console.print(f"Archivos sincronizados: {info['files']}")
    console.print(f"Desbloqueado en este equipo: {'sí' if info['unlocked'] else 'no'}")


@sync.command("olvidar")
def olvidar() -> None:
    """Este equipo olvida la clave (deja de sincronizar hasta configurarlo de nuevo)."""
    from openjarvis.backup.sync import forget

    forget()
    console.print("Este equipo ya no tiene la clave de sincronización.")


__all__ = ["sync"]

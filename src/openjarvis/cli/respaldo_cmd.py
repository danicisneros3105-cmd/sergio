"""``sergio respaldo``: encrypted backups of everything Sergio knows about you.

    sergio respaldo configurar /media/disco/sergio      # or s3://… or sftp://…
    sergio respaldo crear                                # incremental after the first
    sergio respaldo lista
    sergio respaldo verificar
    sergio respaldo restaurar                            # into a new folder
    sergio respaldo restaurar --encima                   # replaces ~/.openjarvis

The passphrase is asked every time (or read from SERGIO_BACKUP_PASSPHRASE)
and never stored. Without it nobody can open the backups — not the storage
provider, not Sergio. The files are standard ``age`` files: ``age -d`` opens
them too.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console

console = Console()


def save_setting(key: str, value: Any) -> None:
    """Write one ``section.key = value`` into config.toml (keeps comments)."""
    import tomlkit

    from openjarvis.core.paths import get_config_path

    path = get_config_path()
    doc = (
        tomlkit.parse(path.read_text("utf-8")) if path.exists() else tomlkit.document()
    )
    section, name = key.split(".", 1)
    if section not in doc:
        doc.add(section, tomlkit.table())
    doc[section][name] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), "utf-8")


def ask_passphrase(env: str, *, confirm: bool) -> str:
    value = os.environ.get(env, "")
    if value:
        return value
    value = click.prompt(
        "Frase de paso", hide_input=True, confirmation_prompt=confirm
    ).strip()
    if len(value) < 10:
        raise click.ClickException(
            "Use una frase de paso de al menos 10 caracteres (mejor varias palabras)."
        )
    return value


def check_target(url: str):  # noqa: ANN201
    """Open the target and prove it works with a write, read and delete."""
    from openjarvis.backup.targets import TargetError, open_target

    try:
        target = open_target(url)
        probe = f"sergio-probe-{os.getpid()}"
        target.put(probe, b"ok")
        if target.get(probe) != b"ok":
            raise TargetError("lo que escribí no coincide al leerlo")
        target.delete(probe)
    except TargetError as exc:
        raise click.ClickException(f"No puedo usar ese destino: {exc}") from None
    return target


def _target():  # noqa: ANN202
    from openjarvis.backup.targets import TargetError, open_target
    from openjarvis.core.config import load_config

    url = load_config().backup.target
    if not url:
        raise click.ClickException(
            "No hay destino. Configure uno con: sergio respaldo configurar <carpeta|s3://…|sftp://…>"
        )
    try:
        return open_target(url)
    except TargetError as exc:
        raise click.ClickException(str(exc)) from None


@click.group("respaldo")
def respaldo() -> None:
    """Copias de seguridad cifradas (carpeta, S3/B2 o SFTP)."""


@respaldo.command("configurar")
@click.argument("destino")
def configurar(destino: str) -> None:
    """Elige dónde guardar las copias y comprueba que funciona."""
    target = check_target(destino)
    save_setting("backup.target", destino)
    console.print(f"Listo: las copias irán a {target.describe()}.")


@respaldo.command("crear")
@click.option(
    "--completo", is_flag=True, help="Copia completa aunque haya una anterior."
)
@click.option("--sin-claves", is_flag=True, help="No incluye sergio.env ni tokens.")
def crear(completo: bool, sin_claves: bool) -> None:
    """Hace una copia cifrada ahora (incremental si ya hay una)."""
    from openjarvis.backup.archive import create, list_backups, prune
    from openjarvis.core.config import load_config

    config = load_config()
    target = _target()
    first = not list_backups(target)
    if first:
        console.print(
            "Primera copia: elija una frase de paso y [bold]guárdela bien[/bold]. "
            "Sin ella las copias no se pueden abrir."
        )
    passphrase = ask_passphrase("SERGIO_BACKUP_PASSPHRASE", confirm=first)
    info = create(
        target,
        passphrase,
        full=completo,
        with_secrets=config.backup.with_secrets and not sin_claves,
        progress=lambda msg: console.print(f"[dim]{msg}[/dim]"),
    )
    removed = prune(target, keep_full=max(1, config.backup.keep_full))
    console.print(
        f"Copia {info.id} ({'completa' if info.kind == 'full' else 'incremental'}): "
        f"{info.files} archivos, {info.size / 1e6:.1f} MB cifrados."
    )
    if removed:
        console.print(f"[dim]Borré {len(removed)} copias antiguas.[/dim]")


@respaldo.command("lista")
def lista() -> None:
    """Las copias que hay en el destino."""
    from openjarvis.backup.archive import list_backups

    backups = list_backups(_target())
    if not backups:
        console.print("Todavía no hay copias. Haga una con: sergio respaldo crear")
    for info in backups:
        kind = "completa" if info.kind == "full" else "incremental"
        console.print(f"{info.id}  {kind}")


@respaldo.command("verificar")
@click.argument("copia", required=False, default="")
def verificar(copia: str) -> None:
    """Descifra una copia y comprueba cada archivo, sin restaurar nada."""
    from openjarvis.backup.archive import verify

    passphrase = ask_passphrase("SERGIO_BACKUP_PASSPHRASE", confirm=False)
    try:
        result = verify(_target(), passphrase, copia)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc)) from None
    console.print(
        f"[green]Copia íntegra:[/green] {result['files']} archivos comprobados "
        f"({result['backups_used']} copia(s) en la cadena)."
    )


@respaldo.command("restaurar")
@click.argument("copia", required=False, default="")
@click.option(
    "--destino",
    type=click.Path(file_okay=False),
    default=None,
    help="Carpeta donde restaurar.",
)
@click.option(
    "--encima", is_flag=True, help="Reemplaza ~/.openjarvis (guarda la actual aparte)."
)
def restaurar(copia: str, destino: Optional[str], encima: bool) -> None:
    """Restaura una copia (la última si no dice cuál)."""
    from openjarvis.backup.archive import home, restore

    passphrase = ask_passphrase("SERGIO_BACKUP_PASSPHRASE", confirm=False)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    current = home()
    if encima:
        dest = current.with_name(current.name + f".restaurando-{stamp}")
    else:
        dest = (
            Path(destino).expanduser()
            if destino
            else current.with_name(f"{current.name}-restaurado-{stamp}")
        )
    try:
        result = restore(
            _target(),
            passphrase,
            dest,
            backup_id=copia,
            progress=lambda msg: console.print(f"[dim]{msg}[/dim]"),
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise click.ClickException(str(exc)) from None
    if encima:
        old = current.with_name(current.name + f".antes-{stamp}")
        if current.exists():
            current.rename(old)
        dest.rename(current)
        console.print(
            f"Restaurado sobre {current} ({result['files']} archivos). "
            f"Lo que había quedó en {old}. Reinicie Sergio: sergio servicio reiniciar"
        )
    else:
        console.print(f"Restaurado en {dest} ({result['files']} archivos).")


__all__ = ["ask_passphrase", "check_target", "respaldo", "save_setting"]

"""``sergio rostros`` — enroll, identify and forget faces from the terminal."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape

console = Console()


def _book():
    from openjarvis.faces import FaceBook

    return FaceBook()


@click.group()
def rostros() -> None:
    """Local face recognition of people you enroll (with their consent)."""


@rostros.command("registrar")
@click.argument("name")
@click.argument("photo", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--consentimiento",
    is_flag=True,
    help="Confirm this person agreed to be recognized.",
)
def registrar(name: str, photo: Path, consentimiento: bool) -> None:
    """Enroll NAME from PHOTO (one face). Add more photos to improve accuracy."""
    from openjarvis.faces import FaceError

    if not consentimiento and not click.confirm(
        f"Did {name} agree to be recognized by Sergio?", default=False
    ):
        raise click.ClickException("Not enrolled: consent is required.")
    try:
        samples = _book().enroll(name, photo.read_bytes(), consent=True)
    except FaceError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"[green]{escape(name)}[/green] enrolled ({samples} photo(s)).")


@rostros.command("identificar")
@click.argument("photo", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def identificar(photo: Path) -> None:
    """Say who is in PHOTO."""
    from openjarvis.faces import FaceError

    try:
        matches = _book().identify(photo.read_bytes())
    except FaceError as exc:
        raise click.ClickException(str(exc)) from exc
    if not matches:
        console.print("No faces found.")
    for match in matches:
        who = escape(match.name) if match.name else "[yellow]unknown[/yellow]"
        console.print(f"{who}  (similarity {match.score:.2f})")


@rostros.command("lista")
def lista() -> None:
    """List enrolled people."""
    people = _book().people()
    if not people:
        console.print("Nobody is enrolled.")
    for person in people:
        console.print(f"{escape(person['name'])}: {person['samples']} photo(s)")


@rostros.command("olvidar")
@click.argument("name")
def olvidar(name: str) -> None:
    """Delete everything stored about NAME."""
    if not _book().forget(name):
        raise click.ClickException(f"Nobody named {name} is enrolled.")
    console.print(f"{escape(name)} forgotten.")


__all__ = [
    "identificar",
    "lista",
    "olvidar",
    "registrar",
    "rostros",
]

"""``sergio ecc`` — download/update ECC and search its guides."""

from __future__ import annotations

import click
from rich.console import Console
from rich.markup import escape

console = Console()


def enable_tool(config_path) -> bool:
    """Add skill_guide to an explicit [tools] enabled list. True if changed."""
    import tomlkit

    if not config_path.exists():
        return False
    doc = tomlkit.parse(config_path.read_text())
    enabled = doc.get("tools", {}).get("enabled")
    if enabled is None or "skill_guide" in enabled:
        return False
    enabled.append("skill_guide")
    config_path.write_text(tomlkit.dumps(doc))
    return True


@click.group()
def ecc() -> None:
    """ECC (Everything Claude Code): expert playbooks Sergio reads on demand."""


@ecc.command("actualizar")
def actualizar() -> None:
    """Download ECC the first time, or update it."""
    import subprocess

    from openjarvis.core.paths import get_config_dir
    from openjarvis.unified.ecc import ECCError, Library, ecc_dir, sync

    console.print("Downloading ECC skills and agents (a few MB)…")
    try:
        commit = sync()
    except ECCError as exc:
        raise click.ClickException(f"Could not download ECC: {exc}") from exc
    count = len(Library(ecc_dir()).guides())
    if enable_tool(get_config_dir() / "config.toml"):
        subprocess.run(
            ["systemctl", "--user", "try-restart", "sergio.service"],
            capture_output=True,
            check=False,
        )
    console.print(f"[green]ECC listo[/green] ({count} guías, versión {commit}).")


@ecc.command("buscar")
@click.argument("query", nargs=-1, required=True)
def buscar(query: tuple[str, ...]) -> None:
    """Search the guides (English keywords work best)."""
    from openjarvis.unified.ecc import Library

    lib = Library()
    if not lib.installed:
        raise click.ClickException(
            "ECC is not downloaded: run `sergio ecc actualizar`."
        )
    hits = lib.search(" ".join(query), limit=10)
    if not hits:
        console.print("Nothing found.")
    for guide in hits:
        about = escape(guide.description[:160])
        console.print(f"[bold]{escape(guide.name)}[/bold] ({guide.kind}): {about}")


@ecc.command("estado")
def estado() -> None:
    """Show whether ECC is installed and how many guides it has."""
    from openjarvis.unified.ecc import Library

    lib = Library()
    if not lib.installed:
        console.print("ECC is not downloaded. Run: sergio ecc actualizar")
        return
    guides = lib.guides()
    skills = sum(g.kind == "skill" for g in guides)
    console.print(
        f"ECC: {skills} skills and {len(guides) - skills} agents in {lib.root}"
    )


__all__ = [
    "actualizar",
    "buscar",
    "ecc",
    "enable_tool",
    "estado",
]

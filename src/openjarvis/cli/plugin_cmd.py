"""``sergio plugin``: find, install and manage plugins (tools by other people).

    sergio plugin buscar clima          # search the indexes
    sergio plugin instalar tipo-de-cambio
    sergio plugin instalar ./mi-plugin-1.0.0.zip
    sergio plugin info tipo-de-cambio
    sergio plugin lista
    sergio plugin desactivar tipo-de-cambio
    sergio plugin desinstalar tipo-de-cambio
    sergio plugin crear mi-plugin       # a ready-to-edit skeleton
    sergio plugin empaquetar mi-plugin  # → mi-plugin-0.1.0.zip + sha256

Plugins in Claude's format, from Claude's marketplaces (same commands as Claude):

    sergio plugin marketplace add anthropics/knowledge-work-plugins
    sergio plugin marketplace list
    sergio plugin explorar diseño        # browse the marketplaces
    sergio plugin instalar design@knowledge-work-plugins

English names work too: search, install, uninstall, info, list, create, pack,
enable, disable. Before installing, Sergio shows what the plugin may do
(its permissions) and asks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()

SKELETON_TOML = """[plugin]
name = "{name}"
version = "0.1.0"
description = "Qué hace este plugin, en una frase."
author = "Su nombre"
license = "Apache-2.0"
entry = "plugin.py"
# Lo que sus herramientas pueden hacer: file:read, file:write, network:fetch,
# code:execute, memory:read, memory:write, tool:invoke, schedule:create
permissions = []
"""
SKELETON_PY = '''"""{name}: una herramienta nueva para Sergio."""

from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


class {cls}(BaseTool):
    tool_id = "{tool}"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="{tool}",
            description="Describa aquí qué hace, para que Sergio sepa cuándo usarla.",
            parameters={{
                "type": "object",
                "properties": {{"texto": {{"type": "string", "description": "Entrada."}}}},
                "required": ["texto"],
            }},
            required_capabilities=[],  # deben estar en permissions de plugin.toml
        )

    def execute(self, **params) -> ToolResult:
        texto = str(params.get("texto", ""))
        return ToolResult(tool_name="{tool}", content=texto.upper(), success=True)


def register(api) -> None:
    api.tool({cls})


__all__ = ["{cls}", "register"]
'''


def _store():
    from openjarvis.plugins.store import PluginStore

    return PluginStore()


def _fail(exc: Exception) -> None:
    raise click.ClickException(str(exc)) from None


@click.group("plugin")
def plugin() -> None:
    """Plugins: herramientas nuevas para Sergio, hechas por otras personas."""


@plugin.command("buscar")
@click.argument("consulta", nargs=-1)
def buscar(consulta: tuple[str, ...]) -> None:
    """Busca plugins en los índices."""
    from openjarvis.plugins.index import search

    results = search(" ".join(consulta))
    installed = _store().installed()
    if not results:
        console.print("No encontré plugins con esa búsqueda.")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("Nombre", "Versión", "Qué hace", "Permisos", ""):
        table.add_column(col)
    for entry in results:
        mark = "instalado" if entry.name in installed else ""
        table.add_row(
            entry.name,
            entry.version,
            entry.description,
            ", ".join(entry.permissions) or "ninguno",
            mark,
        )
    console.print(table)


@plugin.command("instalar")
@click.argument("plugin_spec")
@click.option("--si", "yes", is_flag=True, help="No preguntar (acepta los permisos).")
@click.option(
    "--forzar", "force", is_flag=True, help="Reinstala aunque ya esté esa versión."
)
@click.option("--sha256", "sha", default="", help="Huella esperada del archivo.")
def instalar(plugin_spec: str, yes: bool, force: bool, sha: str) -> None:
    """Instala un plugin por nombre, desde un .zip, una URL https o
    «nombre@marketplace» (formato de Claude)."""
    if "@" in plugin_spec and not plugin_spec.startswith("https://"):
        _claude_install(plugin_spec)
        return
    from openjarvis.plugins import index
    from openjarvis.plugins.loader import load_enabled
    from openjarvis.plugins.package import PackageError, read_manifest
    from openjarvis.plugins.store import PluginError

    try:
        path = Path(plugin_spec).expanduser()
        if path.suffix == ".zip" and path.is_file():
            data, source = path.read_bytes(), str(path.resolve())
        elif plugin_spec.startswith("https://"):
            if not sha and not yes:
                console.print(
                    "[yellow]Sin --sha256 no puedo comprobar que el archivo es el que "
                    "espera.[/yellow]"
                )
            data, source = index.download(plugin_spec), plugin_spec
        else:
            entry = index.find(plugin_spec)
            if entry is None:
                raise PluginError(
                    f"no encuentro «{plugin_spec}». Busque con: sergio plugin buscar"
                )
            if entry.premium:
                from openjarvis.tiers import require

                try:
                    require("premium_skills")
                except PermissionError as exc:
                    raise PluginError(str(exc)) from None
            data, source = index.fetch(entry), entry.source
            sha = sha or entry.sha256
        manifest = read_manifest(data)
    except (PluginError, PackageError, ValueError, OSError) as exc:
        _fail(exc)
        return
    console.print(
        f"[bold]{manifest.name}[/bold] {manifest.version} — {manifest.description}"
    )
    if manifest.author:
        console.print(f"Autor: {manifest.author}")
    permisos = manifest.permissions_es()
    console.print(
        "Podrá: "
        + (", ".join(permisos) if permisos else "nada fuera de sí mismo (sin permisos)")
    )
    console.print(
        "[dim]Un plugin es código de otra persona que corre en su equipo: instale solo "
        "los que confía.[/dim]"
    )
    if not yes and not click.confirm("¿Lo instalo?", default=False):
        console.print("No instalé nada.")
        return
    try:
        _store().install(data, source=source, expected_sha256=sha, force=force)
    except PluginError as exc:
        _fail(exc)
    loaded = load_enabled().get(manifest.name, [])
    console.print(
        f"Listo: «{manifest.name}» instalado"
        + (
            f" con {len(loaded)} herramienta(s): {', '.join(loaded)}."
            if loaded
            else "."
        )
    )


@plugin.command("desinstalar")
@click.argument("nombre")
def desinstalar(nombre: str) -> None:
    """Quita un plugin y sus archivos."""
    if "@" in nombre:
        from openjarvis.plugins.claude_format import ClaudePluginError, ClaudePlugins

        try:
            ClaudePlugins().remove(nombre)
        except ClaudePluginError as exc:
            _fail(exc)
        console.print(f"«{nombre}» desinstalado.")
        return
    from openjarvis.plugins.loader import forget
    from openjarvis.plugins.store import PluginError

    try:
        _store().uninstall(nombre)
    except PluginError as exc:
        _fail(exc)
    forget(nombre)
    console.print(f"«{nombre}» desinstalado.")


@plugin.command("info")
@click.argument("nombre")
def info(nombre: str) -> None:
    """Detalles de un plugin (instalado o del índice)."""
    from openjarvis.plugins import index
    from openjarvis.plugins.loader import load_enabled, status
    from openjarvis.plugins.manifest import PERMISSIONS_ES

    state = _store().installed().get(nombre)
    entry = index.find(nombre)
    if state is None and entry is None:
        raise click.ClickException(f"no conozco «{nombre}»")
    if state is not None:
        manifest = _store().manifest(nombre)
        load_enabled()
        tools = status()["loaded"].get(nombre, [])
        failed = status()["failed"].get(nombre)
        console.print(f"[bold]{manifest.name}[/bold] {manifest.version} (instalado)")
        console.print(manifest.description)
        console.print(
            f"Autor: {manifest.author or '—'} · Licencia: {manifest.license or '—'}"
        )
        console.print(
            "Permisos: " + (", ".join(manifest.permissions_es()) or "ninguno")
        )
        console.print(f"Activo: {'sí' if state.get('enabled', True) else 'no'}")
        console.print(f"Herramientas: {', '.join(tools) or '—'}")
        console.print(f"Huella sha256: {state.get('sha256', '')}")
        if failed:
            console.print(f"[red]No cargó: {failed}[/red]")
    if entry is not None and (state is None or entry.version != state.get("version")):
        label = "disponible" if state is None else "versión nueva disponible"
        console.print(f"\n[bold]{entry.name}[/bold] {entry.version} ({label})")
        console.print(entry.description)
        console.print(
            "Permisos: "
            + (
                ", ".join(PERMISSIONS_ES.get(p, p) for p in entry.permissions)
                or "ninguno"
            )
        )


@plugin.command("lista")
def lista() -> None:
    """Los plugins instalados."""
    from openjarvis.plugins.claude_format import ClaudePlugins

    installed = _store().installed()
    claude = ClaudePlugins().installed()
    for info in claude:
        on = "activo" if info.get("enabled") else "desactivado"
        console.print(
            f"{info['id']} {info.get('version', '')}  ·  {on}  ·  "
            f"{len(info.get('skills') or [])} skills, {len(info.get('connectors') or [])} conectores"
        )
    if not installed and not claude:
        console.print("No hay plugins instalados. Explore con: sergio plugin explorar")
        return
    for name, state in sorted(installed.items()):
        on = "activo" if state.get("enabled", True) else "desactivado"
        perms = ", ".join(state.get("permissions") or []) or "sin permisos"
        console.print(f"{name} {state.get('version', '')}  ·  {on}  ·  {perms}")


def _toggle(nombre: str, enabled: bool) -> None:
    from openjarvis.plugins.loader import forget
    from openjarvis.plugins.store import PluginError

    if "@" in nombre:
        from openjarvis.plugins.claude_format import ClaudePluginError, ClaudePlugins

        try:
            ClaudePlugins().set_enabled(nombre, enabled)
        except ClaudePluginError as exc:
            _fail(exc)
        console.print(f"«{nombre}» {'activado' if enabled else 'desactivado'}.")
        return

    try:
        _store().set_enabled(nombre, enabled)
    except PluginError as exc:
        _fail(exc)
    if not enabled:
        forget(nombre)
    console.print(f"«{nombre}» {'activado' if enabled else 'desactivado'}.")


@plugin.command("activar")
@click.argument("nombre")
def activar(nombre: str) -> None:
    """Vuelve a usar un plugin desactivado."""
    _toggle(nombre, True)


@plugin.command("desactivar")
@click.argument("nombre")
def desactivar(nombre: str) -> None:
    """Deja de usar un plugin sin desinstalarlo."""
    _toggle(nombre, False)


@plugin.command("crear")
@click.argument("nombre")
@click.option(
    "--carpeta", type=click.Path(file_okay=False), default=".", help="Dónde crearlo."
)
def crear(nombre: str, carpeta: str) -> None:
    """Crea el esqueleto de un plugin nuevo, listo para editar."""
    from openjarvis.plugins.manifest import NAME_RE

    if not NAME_RE.match(nombre):
        raise click.ClickException(
            "use minúsculas, dígitos y guiones (p. ej. mi-plugin)"
        )
    folder = Path(carpeta).expanduser() / nombre
    if folder.exists():
        raise click.ClickException(f"ya existe {folder}")
    tool = nombre.replace("-", "_")
    cls = "".join(part.capitalize() for part in nombre.split("-")) or "MiHerramienta"
    (folder / "assets").mkdir(parents=True)
    (folder / "plugin.toml").write_text(SKELETON_TOML.format(name=nombre), "utf-8")
    (folder / "plugin.py").write_text(
        SKELETON_PY.format(name=nombre, cls=cls, tool=tool), "utf-8"
    )
    console.print(
        f"Creado {folder}. Edite plugin.py y plugin.toml; luego: "
        f"sergio plugin empaquetar {folder}"
    )


@plugin.command("empaquetar")
@click.argument("carpeta", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--salida", type=click.Path(file_okay=False), default=None, help="Carpeta del .zip."
)
def empaquetar(carpeta: str, salida: Optional[str]) -> None:
    """Empaqueta una carpeta de plugin en un .zip con su huella sha256."""
    from openjarvis.plugins.package import PackageError, pack

    try:
        archive, digest, manifest = pack(
            Path(carpeta), Path(salida) if salida else None
        )
    except (PackageError, ValueError) as exc:
        _fail(exc)
        return
    console.print(f"{archive}\nsha256: {digest}")
    console.print(
        "Para publicarlo, súbalo a una URL https y añada al índice: "
        f'{{"name": "{manifest.name}", "version": "{manifest.version}", '
        f'"url": "https://…/{archive.name}", "sha256": "{digest}"}}'
    )


def _claude_install(spec: str) -> None:
    from openjarvis.plugins.claude_format import ClaudePluginError, ClaudePlugins

    plugins = ClaudePlugins()
    try:
        if not plugins.marketplaces():
            plugins.ensure_defaults()
        info = plugins.install(spec)
    except ClaudePluginError as exc:
        _fail(exc)
        return
    console.print(f"«{info['display_name']}» instalado ({info['id']}).")
    if info.get("skills"):
        console.print(f"  Skills: {', '.join(info['skills'])}")
    if info.get("connectors"):
        console.print(
            f"  Conectores añadidos: {', '.join(info['connectors'])} — conéctelos con: sergio mcp conectar <nombre>"
        )
    if info.get("hooks"):
        console.print("  Trae hooks de Claude: Sergio no los ejecuta.")


@plugin.command("explorar")
@click.argument("consulta", nargs=-1)
@click.option("--marketplace", "-m", default="", help="Solo este marketplace.")
def explorar(consulta: tuple[str, ...], marketplace: str) -> None:
    """Los plugins de sus marketplaces (formato de Claude)."""
    from openjarvis.plugins.claude_format import ClaudePlugins

    plugins = ClaudePlugins()
    if not plugins.marketplaces():
        console.print("Añadiendo los marketplaces oficiales…")
        plugins.ensure_defaults()
    found = plugins.available(" ".join(consulta), marketplace)
    if not found:
        console.print("Nada encontrado.")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Plugin")
    table.add_column("Qué hace", overflow="fold")
    table.add_column("")
    for item in found[:200]:
        table.add_row(
            item["id"],
            item["description"][:110],
            "instalado" if item["installed"] else "",
        )
    console.print(table)


@plugin.group("marketplace")
def marketplace() -> None:
    """Marketplaces de plugins (repositorios con .claude-plugin/marketplace.json)."""


@marketplace.command("add")
@click.argument("origen")
def marketplace_add(origen: str) -> None:
    """Añade un marketplace: «propietario/repo», URL git o carpeta."""
    from openjarvis.plugins.claude_format import ClaudePluginError, ClaudePlugins

    try:
        out = ClaudePlugins().add_marketplace(origen)
    except ClaudePluginError as exc:
        _fail(exc)
        return
    console.print(f"Marketplace «{out['name']}» añadido: {out['plugins']} plugins.")


@marketplace.command("list")
def marketplace_list() -> None:
    """Los marketplaces añadidos."""
    from openjarvis.plugins.claude_format import ClaudePlugins

    found = ClaudePlugins().marketplaces()
    if not found:
        console.print(
            "Ninguno. Añada uno con: sergio plugin marketplace add anthropics/knowledge-work-plugins"
        )
    for item in found:
        console.print(
            f"{item['name']}  ·  {item['plugins']} plugins  ·  {item['source']}"
        )


@marketplace.command("update")
@click.argument("nombre")
def marketplace_update(nombre: str) -> None:
    """Trae la última versión de un marketplace."""
    from openjarvis.plugins.claude_format import ClaudePluginError, ClaudePlugins

    try:
        out = ClaudePlugins().update_marketplace(nombre)
    except ClaudePluginError as exc:
        _fail(exc)
        return
    console.print(f"«{out['name']}» al día: {out['plugins']} plugins.")


@marketplace.command("remove")
@click.argument("nombre")
def marketplace_remove(nombre: str) -> None:
    """Quita un marketplace (los plugins instalados se quedan)."""
    from openjarvis.plugins.claude_format import ClaudePlugins

    ClaudePlugins().remove_marketplace(nombre)
    console.print(f"«{nombre}» quitado.")


# English names for the same commands.
for _en, _cmd in (
    ("search", buscar),
    ("install", instalar),
    ("uninstall", desinstalar),
    ("list", lista),
    ("enable", activar),
    ("disable", desactivar),
    ("create", crear),
    ("pack", empaquetar),
    ("browse", explorar),
):
    plugin.add_command(_cmd, _en)


__all__ = ["plugin"]

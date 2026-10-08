"""``sergio codigo`` — the coding tools from the terminal.

    sergio codigo tdd "una función que valide RUC ecuatorianos" --salida ruc.py
    sergio codigo depurar "python app.py"          # or: --traza error.txt
    sergio codigo revisar .                        # git diff of the repo (or files)
    sergio codigo docs src/ --readme README.md     # documentation drift
    sergio codigo optimizar script.py              # profile hotspots
    sergio codigo ejecutar main.go                 # any of 12 languages
    sergio codigo traducir main.py --a rust        # verified translation
    sergio codigo renombrar viejo nuevo --raiz . --tests "pytest -q"
    sergio codigo leer libro.txt "¿quién mata al dragón?"
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape

console = Console()


def _llm():
    from openjarvis.intelligence._llm import LLM

    try:
        return LLM.default()
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from None


@click.group("codigo")
def codigo() -> None:
    """Programar: TDD, depurar, revisar, documentar, optimizar, 12 lenguajes, refactor seguro."""


@codigo.command("tdd")
@click.argument("spec")
@click.option("--salida", "out", type=click.Path(dir_okay=False), help="Dónde guardar el código.")
@click.option("--rondas", "rounds", default=4, show_default=True)
def tdd_cmd(spec: str, out: str | None, rounds: int) -> None:
    """Escribe primero las pruebas, luego el código, y repite hasta que pasen."""
    from openjarvis.tools.code_generator import tdd

    module = Path(out).stem if out else "solution"
    with console.status("Escribiendo pruebas y código…"):
        r = tdd(spec, _llm(), module=module, max_rounds=rounds)
    if out:
        Path(out).write_text(r.code, "utf-8")
        Path(out).with_name(f"test_{Path(out).name}").write_text(r.tests, "utf-8")
    console.print(escape(r.code))
    state = "[green]todas pasan[/green]" if r.ok else "[red]aún fallan[/red]"
    console.print(f"Pruebas: {r.last_run.passed} pasan, {r.last_run.failed} fallan — {state} ({r.rounds} ronda/s)")
    if not r.ok:
        raise SystemExit(1)


@codigo.command("depurar")
@click.argument("command", required=False)
@click.option("--traza", "trace_file", type=click.Path(exists=True, dir_okay=False), help="Archivo con la traza.")
def depurar(command: str | None, trace_file: str | None) -> None:
    """Encuentra la causa de un error (ejecuta el comando o lee la traza)."""
    from openjarvis.tools.debugger import analyse, debug_run

    with console.status("Analizando…"):
        if trace_file:
            d = analyse(Path(trace_file).read_text("utf-8", errors="replace"), _llm(), root=Path.cwd())
        elif command:
            d = debug_run(command, _llm(), cwd=str(Path.cwd()))
            if d is None:
                console.print("El comando terminó sin errores.")
                return
        else:
            raise click.UsageError("Da un comando o --traza archivo.")
    console.print(f"[red]{escape(d.trace.exc_type)}[/red]: {escape(d.trace.message)}")
    console.print(f"Dónde importa: {escape(d.culprit.file)}:{d.culprit.line} en {escape(d.culprit.func)}")
    console.print(f"[dim]{escape(d.hint)}[/dim]")
    if d.root_cause:
        console.print(f"\nCausa: {escape(d.root_cause)}\nArreglo: {escape(d.fix)}")
    if d.patch:
        console.print(escape(d.patch))


@codigo.command("revisar")
@click.argument("paths", nargs=-1)
@click.option("--base", default="HEAD", show_default=True, help="Contra qué revisión comparar.")
@click.option("--sin-modelo", "static_only", is_flag=True, help="Solo comprobaciones exactas.")
def revisar(paths: tuple[str, ...], base: str, static_only: bool) -> None:
    """Revisión de código: errores reales, por gravedad."""
    from openjarvis.tools.code_review import git_diff, review

    targets = [Path(p) for p in paths] or [Path(".")]
    diff = ""
    files: list[Path] = []
    for t in targets:
        if t.is_dir():
            diff = git_diff(t, base)
            files += [t / line[6:] for line in diff.splitlines() if line.startswith("+++ b/")]
        else:
            files.append(t)
    with console.status("Revisando…"):
        found = review(files, None if static_only else _llm(), diff=diff)
    colours = {"critical": "red", "high": "red", "medium": "yellow", "low": "cyan", "info": "dim"}
    for f in found:
        c = colours.get(f.severity, "white")
        console.print(f"[{c}]{f.severity.upper():8}[/{c}] {escape(f.file)}:{f.line} {escape(f.title)}"
                      + (f"\n          {escape(f.why)}" if f.why else ""))
    console.print(f"{len(found)} hallazgo(s).")


@codigo.command("docs")
@click.argument("paths", nargs=-1, required=True)
@click.option("--readme", "markdown", multiple=True, type=click.Path(exists=True), help="Markdown a comprobar.")
@click.option("--escribir", "write", is_flag=True, help="Escribir docstrings que faltan.")
def docs(paths: tuple[str, ...], markdown: tuple[str, ...], write: bool) -> None:
    """Documentación desfasada respecto al código (y docstrings que faltan)."""
    from openjarvis.tools.doc_generator import (
        add_docstrings,
        docstring_drift,
        markdown_drift,
    )

    files: list[Path] = []
    for p in map(Path, paths):
        files += sorted(p.rglob("*.py")) if p.is_dir() else [p]
    drift = [d for f in files for d in docstring_drift(f)] + [d for md in markdown for d in markdown_drift(Path(md), files)]
    for d in drift:
        console.print(f"{escape(d.file)}:{d.line} {escape(d.name)}: {escape(d.problem)}")
    console.print(f"{len(drift)} desajuste(s) entre documentación y código.")
    if write:
        llm = _llm()
        total = 0
        for f in files:
            new, n = add_docstrings(f.read_text("utf-8"), llm)
            if n:
                f.write_text(new, "utf-8")
                total += n
        console.print(f"Docstrings escritos: {total}")


@codigo.command("optimizar")
@click.argument("script", type=click.Path(exists=True, dir_okay=False))
def optimizar(script: str) -> None:
    """Perfila un script y muestra dónde se va el tiempo."""
    from openjarvis.tools.optimizer import format_profile, profile_script

    with console.status("Perfilando…"):
        spots = profile_script(Path(script).resolve())
    console.print(escape(format_profile(spots)) or "Sin datos de perfil (¿el script falló?).")


@codigo.command("ejecutar")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--lenguaje", "language", default=None)
def ejecutar(file: str, language: str | None) -> None:
    """Ejecuta un archivo en su lenguaje (Python, JS, TS, Go, Rust, C, C++, Java…)."""
    from openjarvis.tools.polyglot import detect, run

    code = Path(file).read_text("utf-8")
    r = run(code, language or _lang_from_ext(file) or detect(code))
    click.echo(r.stdout, nl=False)
    if not r.ok:
        click.echo(r.stderr, err=True)
        raise SystemExit(1)


_EXT = {".py": "python", ".js": "javascript", ".ts": "typescript", ".sh": "bash", ".rb": "ruby", ".go": "go",
        ".rs": "rust", ".c": "c", ".cpp": "cpp", ".cc": "cpp", ".java": "java", ".php": "php", ".lua": "lua"}


def _lang_from_ext(file: str) -> str | None:
    return _EXT.get(Path(file).suffix.lower())


@codigo.command("traducir")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--a", "target", required=True, help="Lenguaje de destino.")
@click.option("--entrada", "stdin", multiple=True, help="Entradas de prueba (stdin).")
def traducir(file: str, target: str, stdin: tuple[str, ...]) -> None:
    """Traduce a otro lenguaje y comprueba que imprime lo mismo."""
    from openjarvis.tools.polyglot import RUNTIMES, canonical, translate

    with console.status("Traduciendo y comprobando…"):
        t = translate(Path(file).read_text("utf-8"), target, _llm(), source=_lang_from_ext(file),
                      stdin_cases=stdin or ("",))
    out = Path(file).with_name(RUNTIMES[canonical(target)].file) if canonical(target) in RUNTIMES else None
    if out:
        out.write_text(t.code, "utf-8")
    console.print(escape(t.code))
    console.print(("[green]Verificado[/green]: " if t.verified else "[yellow]Sin verificar[/yellow]: ") + t.note
                  + (f" → {out}" if out else ""))


@codigo.command("renombrar")
@click.argument("old")
@click.argument("new")
@click.option("--raiz", "root", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--tests", "test_cmd", default="", help="Comando de pruebas; si falla, se deshace todo.")
def renombrar(old: str, new: str, root: str, test_cmd: str) -> None:
    """Renombra un símbolo en todo el proyecto, o no cambia nada."""
    from openjarvis.tools.refactor import rename_symbol

    r = rename_symbol(Path(root), old, new, test_cmd=test_cmd)
    console.print(("[green]OK[/green] " if r.ok else "[red]Sin cambios[/red] ") + escape(r.reason))
    for path, n in r.renames.items():
        console.print(f"  {escape(path)}: {n}")
    if not r.ok:
        raise SystemExit(1)


@codigo.command("leer")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.argument("question")
@click.option("--todo", "exhaustive", is_flag=True, help="Leer todo el texto, no solo lo relevante.")
def leer(file: str, question: str, exhaustive: bool) -> None:
    """Responde sobre un texto enorme (libros, registros, código) con citas."""
    from openjarvis.intelligence.long_context import answer_file

    with console.status("Leyendo…"):
        r = answer_file(question, file, _llm(), exhaustive=exhaustive)
    console.print(escape(r.answer))
    console.print(f"[dim]Leí {len(r.read)} de {r.chunks} fragmentos.[/dim]")


__all__ = ["codigo"]

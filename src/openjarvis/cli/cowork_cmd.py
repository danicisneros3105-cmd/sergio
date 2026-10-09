"""``sergio cowork``: describe the outcome, step away, Sergio does the rest.

``sergio cowork "compara los 3 mejores portátiles para Blender y hazme una
tabla"`` plans the work, runs every step it may run on its own, asks you
(here, in the app or on your phone) for the steps that need your OK, and
stops at the action cap. With Sergio's server on, the run lives there and
keeps going if you close this window; otherwise it runs right here.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

import click
from rich.console import Console

console = Console()
ICONS = {
    "done": "[green]✓[/green]",
    "failed": "[red]✗[/red]",
    "skipped": "[yellow]–[/yellow]",
    "blocked": "[red]⛔[/red]",
    "waiting_approval": "[cyan]?[/cyan]",
    "running": "[cyan]…[/cyan]",
    "pending": "·",
}
STATUS_ES = {
    "planning": "planificando",
    "running": "trabajando",
    "waiting_approval": "esperando su visto bueno",
    "done": "terminado",
    "partial": "hecho en parte",
    "failed": "no se pudo",
    "capped": "detenido en el tope de acciones",
    "cancelled": "cancelado",
    "interrupted": "interrumpido",
}


class _GoalGroup(click.Group):
    """``sergio cowork "objetivo"`` = ``sergio cowork iniciar "objetivo"``."""

    def parse_args(self, ctx: click.Context, args: List[str]) -> List[str]:
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            args = ["iniciar", *args]
        elif args and args[0].startswith("-") and args[0] not in ("--help", "-h"):
            args = ["iniciar", *args]
        return super().parse_args(ctx, args)


def _base() -> Optional[str]:
    """The server's URL when it is running, else None (run locally)."""
    import httpx

    try:
        from openjarvis.core.config import load_config

        port = int(load_config().server.port or 8000)
    except Exception:  # noqa: BLE001
        port = 8000
    base = f"http://127.0.0.1:{port}"
    try:
        httpx.get(f"{base}/health", timeout=2, trust_env=False).raise_for_status()
    except Exception:  # noqa: BLE001
        return None
    return base


def _http(method: str, path: str, **kw: Any) -> Dict[str, Any]:
    import httpx

    base = _base()
    if base is None:
        raise click.ClickException(
            "Sergio no está encendido. Enciéndalo con: sergio servicio encender"
        )
    resp = httpx.request(method, base + path, timeout=30, trust_env=False, **kw)
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = resp.text
        raise click.ClickException(str(detail))
    return resp.json()


def _show_run(run: Dict[str, Any]) -> None:
    console.print(
        f"[bold]{run.get('title') or run['goal']}[/bold]  ·  "
        f"{STATUS_ES.get(run['status'], run['status'])}  ·  "
        f"{run.get('actions_used', 0)}/{run.get('max_actions')} acciones  ·  [dim]{run['id']}[/dim]"
    )
    for step in run.get("steps", []):
        icon = ICONS.get(step["status"], "·")
        console.print(f"  {icon} {step['index'] + 1}. {step['text']}")
        if step.get("result") and step["status"] != "pending":
            console.print(f"      [dim]{step['result'][:200]}[/dim]")
    if run.get("summary"):
        console.print(f"\n{run['summary']}")


def _events(base: str, run_id: str) -> Iterator[Dict[str, Any]]:
    import httpx

    with httpx.stream(
        "GET", f"{base}/v1/cowork/{run_id}/events", timeout=None, trust_env=False
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                try:
                    yield json.loads(line[5:])
                except ValueError:
                    continue


def _answer(step_text: str) -> bool:
    return click.confirm(f"  ¿Lo hago? {step_text}", default=False)


def _follow_remote(base: str, run: Dict[str, Any], interactive: bool) -> Dict[str, Any]:
    import httpx

    last = run
    for event in _events(base, run["id"]):
        if event.get("type") == "snapshot":
            last = event["run"]
            continue
        text = event.get("text") or ""
        if text:
            console.print(f"[dim]›[/dim] {text}")
        if event.get("type") == "approval" and interactive:
            ok = _answer(text)
            httpx.post(
                f"{base}/v1/cowork/{run['id']}/decision",
                json={"step": int(event["step"]) + 1, "approve": ok},
                timeout=10,
                trust_env=False,
            )
    return last


def _run_locally(goal: str, autonomy: str, max_actions: int, interactive: bool) -> None:
    import queue
    import threading

    from openjarvis.core.config import load_config
    from openjarvis.cowork.session import CoworkEngine

    config = load_config()
    engine = CoworkEngine(approval_timeout=config.cowork.approval_timeout_minutes * 60)
    box: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    run = engine.start(goal, autonomy=autonomy, max_actions=max_actions, listener=box)
    console.print(
        "[dim]Sergio no está encendido: trabajo aquí mismo (no cierre esta ventana).[/dim]"
    )
    while True:
        event = box.get()
        text = event.get("text") or ""
        if text:
            console.print(f"[dim]›[/dim] {text}")
        if event.get("type") == "approval":
            ok = _answer(text) if interactive else False
            threading.Thread(
                target=engine.decide, args=(run.id, int(event["step"]), ok), daemon=True
            ).start()
        if event.get("type") == "finished":
            break
    _show_run(run.to_dict())


@click.group("cowork", cls=_GoalGroup, invoke_without_command=True)
@click.pass_context
def cowork(ctx: click.Context) -> None:
    """Modo Cowork: describa el resultado, aléjese y Sergio hace el resto."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@cowork.command("iniciar")
@click.argument("objetivo", nargs=-1, required=True)
@click.option(
    "--autonomia",
    type=click.Choice(["cauteloso", "normal", "autonomo"]),
    default=None,
    help="Cuánto hace solo: cauteloso pregunta más, autonomo pregunta menos.",
)
@click.option(
    "--max-acciones", type=int, default=None, help="Tope de acciones (por defecto 50)."
)
@click.option(
    "--no-seguir",
    is_flag=True,
    help="Solo la inicia; véala luego con: sergio cowork estado.",
)
def iniciar(
    objetivo: tuple[str, ...],
    autonomia: Optional[str],
    max_acciones: Optional[int],
    no_seguir: bool,
) -> None:
    """Empieza una tarea Cowork con el resultado que usted quiere."""
    import sys

    from openjarvis.core.config import load_config

    config = load_config()
    goal = " ".join(objetivo).strip()
    autonomy = autonomia or config.cowork.autonomy
    cap = max_acciones or config.cowork.max_actions
    interactive = sys.stdin.isatty()
    base = _base()
    if base is None:
        if no_seguir:
            raise click.ClickException(
                "Para dejarla trabajando sola, encienda Sergio: sergio servicio encender"
            )
        _run_locally(goal, autonomy, cap, interactive)
        return
    run = _http(
        "POST",
        "/v1/cowork",
        json={"goal": goal, "autonomy": autonomy, "max_actions": cap},
    )
    console.print(
        f"Cowork en marcha ([dim]{run['id']}[/dim]): {run['max_actions']} acciones como "
        f"máximo, autonomía {run['autonomy']}. Puede cerrar esta ventana: sigo trabajando."
    )
    if no_seguir:
        return
    try:
        last = _follow_remote(base, run, interactive)
    except KeyboardInterrupt:
        console.print(f"\nSigo trabajando. Véalo con: sergio cowork estado {run['id']}")
        return
    _show_run(_http("GET", f"/v1/cowork/{last['id']}"))


@cowork.command("lista")
def lista() -> None:
    """Las tareas Cowork recientes."""
    runs = _http("GET", "/v1/cowork")["runs"]
    if not runs:
        console.print("Todavía no hay tareas Cowork.")
    for run in runs[:20]:
        console.print(
            f"[dim]{run['id']}[/dim]  {STATUS_ES.get(run['status'], run['status']):<26} "
            f"{run.get('title') or run['goal'][:60]}"
        )


@cowork.command("estado")
@click.argument("tarea", required=False)
def estado(tarea: Optional[str]) -> None:
    """Cómo va una tarea (la última si no dice cuál)."""
    if not tarea:
        runs = _http("GET", "/v1/cowork")["runs"]
        if not runs:
            raise click.ClickException("Todavía no hay tareas Cowork.")
        tarea = runs[0]["id"]
    _show_run(_http("GET", f"/v1/cowork/{tarea}"))


def _decide(tarea: str, paso: int, approve: bool) -> None:
    _http(
        "POST", f"/v1/cowork/{tarea}/decision", json={"step": paso, "approve": approve}
    )
    console.print("Hecho: " + ("lo hago." if approve else "no lo hago."))


@cowork.command("aprobar")
@click.argument("tarea")
@click.argument("paso", type=int)
def aprobar(tarea: str, paso: int) -> None:
    """Da el visto bueno a un paso que espera."""
    _decide(tarea, paso, True)


@cowork.command("rechazar")
@click.argument("tarea")
@click.argument("paso", type=int)
def rechazar(tarea: str, paso: int) -> None:
    """Rechaza un paso que espera (no se hace)."""
    _decide(tarea, paso, False)


@cowork.command("cancelar")
@click.argument("tarea")
def cancelar(tarea: str) -> None:
    """Detiene una tarea Cowork."""
    _http("POST", f"/v1/cowork/{tarea}/cancel")
    console.print("Cancelada.")


@cowork.command("auditoria")
@click.argument("tarea")
def auditoria(tarea: str) -> None:
    """El registro completo de lo que decidió e hizo (con su sello de integridad)."""
    data = _http("GET", f"/v1/cowork/{tarea}/audit")
    for entry in data["entries"]:
        info = entry.get("data") or {}
        brief = info.get("text") or info.get("result") or info.get("decision") or ""
        console.print(
            f"{entry.get('seq', '?'):>3}  {entry.get('event', ''):<16} {str(brief)[:100]}"
        )
    if data["intact"]:
        console.print("[green]Registro íntegro: nadie lo modificó.[/green]")
    else:
        console.print(
            f"[red]El registro fue alterado (desde la entrada {data['broken_at']}).[/red]"
        )


__all__ = ["cowork"]

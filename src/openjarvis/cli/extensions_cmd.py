"""``jarvis extensions`` — manage the bundled OpenClacky agent and 3D globe."""

from __future__ import annotations

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

console = Console()

_NAMES = click.Choice(["all", "clacky", "globe"])


def _supervisor(ui_ports: tuple[int, ...] = ()):
    from openjarvis.core.config import load_config
    from openjarvis.unified.supervisor import Supervisor

    return Supervisor(load_config(), ui_ports=ui_ports)


def start_extensions(
    names: tuple[str, ...] = ("all",), ui_ports: tuple[int, ...] = ()
) -> list[str]:
    """Start extensions, print one line each; return the ones started now.

    Services that were already running are not included, so a caller such
    as ``sergio gui`` only stops what it started itself.
    """
    sup = _supervisor(ui_ports)
    started: list[str] = []
    for svc in sup.services():
        if "all" in names or svc.name in names:
            was_running = sup.running(svc)
            outcome = sup.start(svc)
            console.print(f"[cyan]{svc.title}[/cyan]: {escape(outcome)}")
            if not was_running and outcome.startswith(("running", "started")):
                started.append(svc.name)
    return started


def stop_extensions(names: tuple[str, ...] | None = None) -> None:
    """Stop *names* (default: all extensions)."""
    sup = _supervisor()
    for name in names if names is not None else ("clacky", "globe"):
        if sup.stop(name):
            console.print(f"[cyan]{name}[/cyan]: stopped")


@click.group()
def extensions() -> None:
    """Bundled extensions: OpenClacky (computer agent) and the 3D globe."""


@extensions.command("status")
def status() -> None:
    """Show whether each extension is available and running."""
    table = Table("Extension", "State", "URL / problem")
    for row in _supervisor().status():
        if row["running"]:
            state, detail = "[green]running[/green]", row["url"]
        elif row["available"]:
            state, detail = "stopped", row["url"]
        else:
            state, detail = "[yellow]unavailable[/yellow]", escape(row["problem"])
        table.add_row(row["title"], state, detail)
    console.print(table)


@extensions.command("start")
@click.argument("name", type=_NAMES, default="all")
def start(name: str) -> None:
    """Start one extension or all of them in the background."""
    start_extensions((name,))


@extensions.command("stop")
@click.argument("name", type=_NAMES, default="all")
def stop(name: str) -> None:
    """Stop one extension or all of them."""
    if name == "all":
        stop_extensions()
    elif _supervisor().stop(name):
        console.print(f"[cyan]{name}[/cyan]: stopped")
    else:
        console.print(f"{name} was not running")


@extensions.command("logs")
@click.argument("name", type=click.Choice(["clacky", "globe"]))
@click.option("-n", "--lines", default=40, show_default=True)
def logs(name: str, lines: int) -> None:
    """Print the last lines of an extension's log."""
    path = _supervisor().log_file(name)
    if not path.exists():
        raise click.ClickException(f"No log yet at {path}")
    tail = path.read_text(errors="replace").splitlines()[-lines:]
    click.echo("\n".join(tail))


def watch_extensions(
    sup, *, interval: float = 30.0, should_stop=lambda: False, sleep=None
) -> None:
    """Keep every available extension running; restart any that died."""
    import time

    sleep = sleep or time.sleep
    while not should_stop():
        for svc in sup.services():
            if svc.problem or sup.running(svc):
                continue
            console.print(f"[cyan]{svc.title}[/cyan]: {escape(sup.start(svc))}")
        waited = 0.0
        while waited < interval and not should_stop():
            sleep(1.0)
            waited += 1.0


@extensions.command("run")
@click.option("--interval", default=30.0, show_default=True, help="Health check, s.")
def run(interval: float) -> None:
    """Run in the foreground for a service manager (systemd).

    Starts the extensions, restarts them if they crash, and stops them on
    SIGTERM/Ctrl-C.
    """
    import signal

    stop = {"flag": False}

    def _terminate(signum, frame):  # noqa: ARG001
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _terminate)
    sup = _supervisor()
    try:
        watch_extensions(sup, interval=interval, should_stop=lambda: stop["flag"])
    except KeyboardInterrupt:
        pass
    finally:
        stop_extensions()

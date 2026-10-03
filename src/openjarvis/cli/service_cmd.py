"""``sergio servicio`` — run Sergio permanently in the background.

Installs two systemd *user* services (Linux, or WSL2 with systemd enabled):

* ``sergio.service`` — the API server, which also serves the built web UI on
  ``http://localhost:<port>``.
* ``sergio-extensiones.service`` — keeps OpenClacky and the 3D globe running
  (``sergio extensions run``), restarting them if they crash.

Both start at boot (with lingering enabled) and restart on failure. Use
``sergio servicio apagar`` / ``encender`` to switch them off and on.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence

import click
from rich.console import Console
from rich.markup import escape

console = Console()

UNITS = ("sergio.service", "sergio-extensiones.service")

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=False)


def unit_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "systemd" / "user"


def env_file() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "sergio.env"


def render_units(root: Path, uv: str, port: int, path_env: str) -> dict[str, str]:
    """Return ``{unit name: file content}`` for both services."""
    common = (
        f"WorkingDirectory={root}\n"
        f"Environment=PATH={path_env}\n"
        # API keys etc. live here (KEY=value per line); optional.
        f"EnvironmentFile=-{env_file()}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
    )
    server = (
        "[Unit]\n"
        "Description=Sergio: asistente personal (servidor e interfaz)\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        # Keep retrying at boot until the model server (Ollama) is up.
        "StartLimitIntervalSec=0\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={uv} run --project {root} sergio serve "
        f"--host 127.0.0.1 --port {port}\n"
        f"{common}\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    extensions = (
        "[Unit]\n"
        "Description=Sergio: Clacky y globo 3D\n"
        "After=sergio.service\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={uv} run --project {root} sergio extensions run\n"
        # The tunnel must forward to the port the server really uses.
        f"Environment=SERGIO_SERVER_PORT={port}\n"
        f"{common}"
        "KillMode=mixed\n"
        "TimeoutStopSec=30\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    return {UNITS[0]: server, UNITS[1]: extensions}


def _service_path() -> str:
    """PATH for the services: current PATH plus the usual tool locations."""
    home = Path.home()
    extra = [
        home / ".local" / "bin",
        home / ".cargo" / "bin",
        home / ".local" / "share" / "mise" / "shims",
    ]
    parts = os.environ.get("PATH", "").split(os.pathsep)
    for path in map(str, extra):
        if path not in parts:
            parts.append(path)
    return os.pathsep.join(p for p in parts if p)


def _systemctl(runner: Runner, *args: str) -> subprocess.CompletedProcess:
    return runner(["systemctl", "--user", *args])


def _require_systemd(runner: Runner) -> None:
    if shutil.which("systemctl") is None or (
        _systemctl(runner, "show-environment").returncode != 0
    ):
        raise click.ClickException(
            "systemd (user) is not available. On WSL add to /etc/wsl.conf:\n"
            "  [boot]\n  systemd=true\n"
            "then run `wsl --shutdown` in PowerShell and open Ubuntu again."
        )


def _build_ui(root: Path, runner: Runner) -> None:
    static = root / "src" / "openjarvis" / "server" / "static" / "index.html"
    if static.exists():
        return
    frontend = root / "frontend"
    console.print("Building the web interface (one time)…")
    if not (frontend / "node_modules").is_dir():
        runner(["npx", "-y", "npm@11", "ci", "--prefix", str(frontend)])
    done = runner(["npm", "run", "build", "--prefix", str(frontend)])
    if done.returncode != 0 or not static.exists():
        raise click.ClickException(
            "Could not build the web interface:\n" + (done.stderr or "")[-1500:]
        )


@click.group()
def servicio() -> None:
    """Run Sergio permanently in the background (systemd user services)."""


@servicio.command("instalar")
@click.option("--puerto", default=8000, show_default=True, help="Port of the UI/API.")
def instalar(puerto: int) -> None:
    """Install and start Sergio as a permanent service."""
    runner = _run
    from openjarvis.unified.paths import _REPO_ROOT

    _require_systemd(runner)
    uv = shutil.which("uv")
    if uv is None:
        raise click.ClickException("uv is not installed (run the installer first).")
    _build_ui(_REPO_ROOT, runner)

    target = unit_dir()
    target.mkdir(parents=True, exist_ok=True)
    for name, content in render_units(_REPO_ROOT, uv, puerto, _service_path()).items():
        (target / name).write_text(content)
    if not env_file().exists():
        env_file().parent.mkdir(parents=True, exist_ok=True)
        env_file().write_text(
            "# Claves para Sergio cuando corre como servicio (KEY=valor).\n"
            "# ANTHROPIC_API_KEY=...\n"
        )
        env_file().chmod(0o600)

    _systemctl(runner, "daemon-reload")
    done = _systemctl(runner, "enable", "--now", *UNITS)
    if done.returncode != 0:
        raise click.ClickException(f"systemctl failed: {done.stderr.strip()}")
    # Keep the services running without an open session (boot / closed WSL).
    linger = runner(["loginctl", "enable-linger", getpass.getuser()])
    if linger.returncode != 0:
        console.print(
            "[yellow]Could not enable lingering; run "
            f"`sudo loginctl enable-linger {getpass.getuser()}` once.[/yellow]"
        )
    console.print(
        f"[green]Sergio is installed and running:[/green] http://localhost:{puerto}"
    )


@servicio.command("encender")
def encender() -> None:
    """Switch Sergio on (and keep it on after reboots)."""
    runner = _run
    _require_systemd(runner)
    done = _systemctl(runner, "enable", "--now", *UNITS)
    if done.returncode != 0:
        raise click.ClickException(
            f"Could not start (did you run `sergio servicio instalar`?): "
            f"{done.stderr.strip()}"
        )
    console.print("[green]Sergio is on.[/green]")


@servicio.command("apagar")
def apagar() -> None:
    """Switch Sergio off (it stays off after reboots until `encender`)."""
    runner = _run
    _require_systemd(runner)
    _systemctl(runner, "disable", "--now", *UNITS)
    console.print("Sergio is off.")


@servicio.command("estado")
def estado() -> None:
    """Show whether the services are running."""
    runner = _run
    _require_systemd(runner)
    for unit in UNITS:
        state = _systemctl(runner, "is-active", unit).stdout.strip() or "unknown"
        color = "green" if state == "active" else "yellow"
        console.print(f"{unit}: [{color}]{escape(state)}[/{color}]")


@servicio.command("desinstalar")
def desinstalar() -> None:
    """Stop the services and remove them."""
    runner = _run
    _require_systemd(runner)
    _systemctl(runner, "disable", "--now", *UNITS)
    for unit in UNITS:
        (unit_dir() / unit).unlink(missing_ok=True)
    _systemctl(runner, "daemon-reload")
    console.print("Sergio service removed (your data and settings are kept).")

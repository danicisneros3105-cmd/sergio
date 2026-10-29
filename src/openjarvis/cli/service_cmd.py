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


def wait_for_server(
    base: str,
    timeout: float = 150.0,
    *,
    get: Callable[..., object] | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> bool:
    """Wait until Sergio's server answers ``/health`` (True) or time runs out.

    After ``systemctl restart`` the port stays closed for a while (imports,
    tools, models); anything that talks to the server right away would get
    "Connection refused". Any HTTP answer means it is up: a 503 from a busy
    engine is still a running server.
    """
    import time

    import httpx

    get = get or httpx.get
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    deadline = clock() + timeout
    while True:
        try:
            get(f"{base.rstrip('/')}/health", timeout=5)
            return True
        except httpx.HTTPError:
            pass
        if clock() >= deadline:
            return False
        sleep(1.0)


def service_state(runner: Runner = _run, unit: str = "sergio.service") -> str:
    """systemd state of Sergio's server: active, activating, inactive, failed,
    missing (not installed) or no-systemd."""
    if shutil.which("systemctl") is None:
        return "no-systemd"
    try:
        out = runner(["systemctl", "--user", "is-active", unit])
    except (OSError, subprocess.SubprocessError):
        return "no-systemd"
    state = (out.stdout or "").strip() or "unknown"
    if state in ("inactive", "unknown"):
        try:
            loaded = runner(
                ["systemctl", "--user", "show", unit, "-p", "LoadState", "--value"]
            )
            if (loaded.stdout or "").strip() == "not-found":
                return "missing"
        except (OSError, subprocess.SubprocessError):
            pass
    if "Failed to connect to bus" in (out.stderr or ""):
        return "no-systemd"
    return state


def journal_tail(lines: int = 15, runner: Runner = _run) -> str:
    try:
        out = runner(
            [
                "journalctl",
                "--user",
                "-u",
                "sergio",
                "-n",
                str(lines),
                "--no-pager",
                "-o",
                "cat",
            ]
        )
        return (out.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def bypass_proxy_for_local() -> None:
    """Never send 127.0.0.1/localhost through an HTTP proxy from the environment
    (a corporate or VPN proxy makes local calls hang until they time out)."""
    for var in ("NO_PROXY", "no_proxy"):
        current = [x.strip() for x in os.environ.get(var, "").split(",") if x.strip()]
        for host in ("127.0.0.1", "localhost", "::1"):
            if host not in current:
                current.append(host)
        os.environ[var] = ",".join(current)


def ensure_server(
    base: str,
    say: Callable[[str], None],
    *,
    timeout: float = 120.0,
    start: bool = True,
    get: Callable[..., object] | None = None,
    runner: Runner = _run,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> bool:
    """Make sure Sergio's server answers, never waiting in silence.

    Answers at once -> True. Otherwise looks at the service: switched off or
    crashed -> switches it on; not installed -> says how and returns at once;
    then waits with a progress line every few seconds, stopping early (with
    the last log lines) if the service fails. Local calls ignore proxy
    settings, which can make 127.0.0.1 hang.
    """
    import time

    import httpx

    sleep = sleep or time.sleep
    clock = clock or time.monotonic

    def answers() -> bool:
        try:
            if get is not None:
                get(f"{base.rstrip('/')}/health", timeout=3)
            else:
                httpx.get(f"{base.rstrip('/')}/health", timeout=3, trust_env=False)
            return True
        except httpx.HTTPError:
            return False

    if answers():
        return True
    state = service_state(runner)
    if state in ("missing", "no-systemd"):
        say(
            f"Sergio no responde en {base} y no está instalado como servicio. "
            "Instálalo con: sergio servicio instalar   (o ábrelo a mano en otra ventana: sergio serve)"
        )
        return False
    if state in ("inactive", "failed", "deactivating") and start:
        say(f"Sergio estaba apagado (estado: {state}). Lo enciendo…")
        runner(["systemctl", "--user", "reset-failed", "sergio.service"])
        runner(["systemctl", "--user", "restart", "sergio.service"])
    started = clock()
    next_note = started + 5
    while clock() - started < timeout:
        if answers():
            say(f"Sergio está encendido ({clock() - started:.0f} s).")
            return True
        now = clock()
        if now >= next_note:
            state = service_state(runner)
            if state == "failed":
                break
            say(
                f"  …Sergio sigue arrancando ({now - started:.0f} s, servicio: {state})"
            )
            next_note = now + 5
        sleep(1.0)
    state = service_state(runner)
    say(
        f"Sergio no respondió en {timeout:.0f} s (servicio: {state}). Últimas líneas de su registro:"
    )
    say(journal_tail(runner=runner) or "(sin registro)")
    return False


def render_units(root: Path, uv: str, port: int, path_env: str) -> dict[str, str]:
    """Return ``{unit name: file content}`` for both services."""
    escaped_path = path_env.replace("\\", "\\\\").replace('"', '\\"')
    common = (
        f"WorkingDirectory={root}\n"
        f'Environment="PATH={escaped_path}"\n'
        # API keys etc. live here (KEY=value per line); optional.
        f"EnvironmentFile=-{env_file()}\n"
        # always: also after the vigía (estabilidad.py) exits a stuck server
        "Restart=always\n"
        "RestartSec=3\n"
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
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    extra_strs = [str(p) for p in extra]
    # Keep Linux user tool directories ahead of inherited WSL /mnt/c/... entries.
    parts = extra_strs + [p for p in parts if p not in extra_strs]
    # The installer's own Node (newest first) wins over an older system one.
    toolchain = sorted(
        (home / ".local" / "share" / "sergio-toolchain").glob("node-*/bin"),
        reverse=True,
    )
    toolchain_strs = [str(p) for p in toolchain]
    parts = toolchain_strs + [p for p in parts if p not in toolchain_strs]
    return os.pathsep.join(parts)


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


def _ui_outdated(frontend: Path, static: Path) -> bool:
    """True when the frontend sources changed after the last build (git pull)."""
    built = static.stat().st_mtime
    sources = [frontend / "index.html", frontend / "package.json"]
    sources += (frontend / "src").rglob("*")
    return any(p.is_file() and p.stat().st_mtime > built for p in sources)


def _build_ui(root: Path, runner: Runner) -> None:
    server = root / "src" / "openjarvis" / "server"
    static = server / "static_local" / "index.html"
    if not static.exists():
        static = server / "static" / "index.html"
    if static.exists() and not _ui_outdated(root / "frontend", static):
        return
    frontend = root / "frontend"
    import os

    # into the folder git ignores, so the next update never stops on it
    os.environ["SERGIO_WEB_OUT"] = str(server / "static_local")
    static = server / "static_local" / "index.html"
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
    # Desde PowerShell (bash -lc) mise no está activado: añade sus shims para
    # que npm/node/ruby se encuentren al construir la interfaz.
    os.environ["PATH"] = _service_path()
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
    done = _systemctl(runner, "enable", *UNITS)
    if done.returncode == 0:
        # restart (not start) so re-running after `git pull` loads the new code.
        done = _systemctl(runner, "restart", *UNITS)
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


__all__ = [
    "apagar",
    "bypass_proxy_for_local",
    "desinstalar",
    "encender",
    "ensure_server",
    "env_file",
    "estado",
    "instalar",
    "journal_tail",
    "render_units",
    "service_state",
    "servicio",
    "unit_dir",
    "UNITS",
    "wait_for_server",
]

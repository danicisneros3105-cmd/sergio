"""``sergio escritorio`` — install Sergio's Windows side (cursor companion).

Run from Ubuntu (WSL). It creates a shared secret, gives Sergio the
screen tools, and runs ``scripts/instalar-escritorio.ps1`` in Windows, which
installs Sergio Escritorio for the current Windows user (no admin needed).
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from pathlib import Path

import click
import httpx
from rich.console import Console

console = Console()

DESKTOP_TOOLS = (
    "screen_read",
    "desktop_action",
    "camera_look",
    "video_edit",
    "blender_create",
    "face_approval",
    "face_enroll",
    "skill_guide",
    "web_search",
)
MIN_TURNS = 25  # a desktop task is many small look-then-act steps
VISION_MODEL = "qwen2.5vl:7b"


def _wslpath(path: Path) -> str:
    done = subprocess.run(
        ["wslpath", "-w", str(path)], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def enable_tools(config_path: Path) -> None:
    """Add the desktop tools and enough agent turns to config.toml."""
    import tomlkit

    doc = (
        tomlkit.parse(config_path.read_text())
        if config_path.exists()
        else tomlkit.document()
    )
    tools = doc.setdefault("tools", tomlkit.table())
    enabled = tools.get("enabled")
    if enabled is not None:  # empty/missing = server defaults, leave alone
        for name in DESKTOP_TOOLS:
            if name not in enabled:
                enabled.append(name)
    agent = doc.setdefault("agent", tomlkit.table())
    agent["max_turns"] = max(int(agent.get("max_turns", 10)), MIN_TURNS)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(tomlkit.dumps(doc))


def pull_model(model: str) -> bool:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if "://" not in host:
        host = "http://" + host
    try:
        resp = httpx.post(
            f"{host}/api/pull", json={"model": model, "stream": False}, timeout=None
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


@click.group()
def escritorio() -> None:
    """Sergio in Windows: cursor companion, voice, and control of the screen."""


@escritorio.command("instalar")
@click.option(
    "--vision",
    is_flag=True,
    help=f"Also download a local vision model ({VISION_MODEL}, ~6 GB) so "
    "Sergio can describe images on screen.",
)
@click.option(
    "--gpu",
    is_flag=True,
    help="Also download the NVIDIA libraries (~1 GB) so Sergio hears with the "
    "big Whisper model on the graphics card.",
)
def instalar(vision: bool, gpu: bool = False) -> None:
    """Install (or update) Sergio Escritorio in Windows."""
    from openjarvis.cli.phone_cmd import read_env, write_env
    from openjarvis.cli.service_cmd import env_file
    from openjarvis.core.paths import get_config_dir
    from openjarvis.unified.paths import _REPO_ROOT

    if shutil.which("powershell.exe") is None:
        raise click.ClickException(
            "Run this in Ubuntu on Windows (WSL): Sergio Escritorio is a Windows app."
        )
    env_path = env_file()
    env = read_env(env_path)
    token = env.get("SERGIO_DESKTOP_TOKEN") or secrets.token_urlsafe(32)
    updates = {"SERGIO_DESKTOP_TOKEN": token}

    if vision:
        console.print(f"Downloading the vision model {VISION_MODEL} (one time)…")
        if pull_model(VISION_MODEL):
            updates["SERGIO_VISION_MODEL"] = VISION_MODEL
        else:
            console.print(
                f"[yellow]Could not download it; later run in PowerShell: "
                f"ollama pull {VISION_MODEL}[/yellow]"
            )
    write_env(env_path, updates)
    enable_tools(get_config_dir() / "config.toml")

    script = _wslpath(_REPO_ROOT / "scripts" / "instalar-escritorio.ps1")
    source = _wslpath(_REPO_ROOT / "windows")
    console.print("Installing in Windows (a few minutes the first time)…")
    # The token travels as an environment variable (WSLENV), not on a
    # command line other programs could read.
    child_env = dict(os.environ, SERGIO_DESKTOP_TOKEN=token)
    child_env["WSLENV"] = ":".join(
        p for p in (os.environ.get("WSLENV", ""), "SERGIO_DESKTOP_TOKEN") if p
    )
    done = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script,
            "-Fuente",
            source,
            *(["-Gpu"] if gpu else []),
        ],
        env=child_env,
        check=False,
    )
    if done.returncode != 0:
        raise click.ClickException(
            "The Windows installer failed (see the messages above)."
        )

    # Load the token and the new tools into the running Sergio.
    subprocess.run(
        ["systemctl", "--user", "try-restart", "sergio.service"],
        capture_output=True,
        check=False,
    )
    console.print(
        "\n[green]Listo.[/green] Sergio vive junto a tu cursor (sin ventanas):\n"
        "  Di «Sergio, …»        y pídele lo que quieras\n"
        "  Ctrl+Espacio          hablarle sin decir su nombre\n"
        "  Ctrl+Alt+Fin          pausar / reanudar su control del mouse y teclado\n"
        "Ajustes y Salir: clic derecho en su icono junto al reloj."
    )


@escritorio.command("estado")
def estado() -> None:
    """Check that Sergio can reach Sergio Escritorio."""
    from openjarvis.cli.phone_cmd import read_env
    from openjarvis.cli.service_cmd import env_file

    token = read_env(env_file()).get("SERGIO_DESKTOP_TOKEN", "")
    url = os.environ.get("SERGIO_DESKTOP_URL", "http://127.0.0.1:8765")
    if not token:
        raise click.ClickException("Not installed: run `sergio escritorio instalar`.")
    try:
        resp = httpx.get(
            f"{url}/health", headers={"Authorization": f"Bearer {token}"}, timeout=5
        )
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise click.ClickException(
            "Sergio Escritorio is not answering. Open 'Sergio' from the Windows "
            f"Start menu. ({exc})"
        ) from exc
    if resp.status_code != 200:
        raise click.ClickException(
            f"Sergio Escritorio refused the token ({resp.status_code})."
        )
    state = "active" if data.get("enabled") else "PAUSED (Ctrl+Alt+End)"
    console.print(f"Sergio Escritorio is running. Screen control: {state}")

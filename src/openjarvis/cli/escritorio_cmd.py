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
    "sergio_app",
    "professional_apps",
    "opendesign",
    "kronos_forecast",
    "screen_read",
    "desktop_action",
    "camera_look",
    "video_edit",
    "video_pro",
    "blender_create",
    "face_approval",
    "face_enroll",
    "files_organize",
    "photos_duplicates",
    "pc_checkup",
    "python_run",
    "terminal_run",
    "skill_guide",
    "web_search",
)
# Always on as well, so Sergio is never left with only the server defaults.
BASE_TOOLS = (
    "sergio_app",
    "professional_apps",
    "anatomy_figure",
    "verified_math",
    "scene_reason",
    "think",
    "calculator",
    "image_generate",
    "video_create",
    "video_essay",
    "reminders",
    "investigacion_profunda",
    "get_weather",
    "globe_view",
    "live_flights",
    "flights_overhead",
    "live_earthquakes",
)
MIN_TURNS = 25  # a desktop task is many small look-then-act steps
VISION_MODEL = "qwen2.5vl:7b"


SERVER_EXTRAS = (
    "server",
    "desktop",
    "faces",
    "evolution",
    "cad",
    "tripo",
)  # what the desktop features need on the server


def sync_server(extras: tuple[str, ...] = SERVER_EXTRAS, run=None) -> bool:
    """Install new server dependencies (face recognition...) in Sergio's venv.

    ``--inexact`` only adds: nothing the user installed is removed.
    """
    import sys

    from openjarvis.unified.paths import _REPO_ROOT

    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    if not Path(uv).exists() or sys.prefix == sys.base_prefix:
        return False
    run = run or subprocess.run
    cmd = [uv, "sync", "--inexact", "--python", sys.executable]
    for extra in extras:
        cmd += ["--extra", extra]
    done = run(
        cmd,
        cwd=_REPO_ROOT,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": sys.prefix},
        check=False,
    )
    return done.returncode == 0


def clean_server(repo: Path, run=None) -> None:
    """Keep only the latest on Ubuntu: uv's cache, superseded Pythons, git."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "sergio_limpieza", repo / "windows" / "sergio_escritorio" / "limpieza.py"
    )
    if spec is None or spec.loader is None:
        return
    limpieza = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(limpieza)
    run = run or subprocess.run
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    console.print("Limpiando versiones viejas (caché, Pythons reemplazados, git)…")
    try:
        if Path(uv).exists():
            limpieza.clean_python(
                uv, [sys.executable, getattr(sys, "_base_executable", "")], run
            )
        limpieza.clean_git(repo, run)
    except OSError:
        pass


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
    current = tools.get("enabled") or []
    if isinstance(current, str):
        current = current.split(",")
    # Missing/empty would mean the server defaults (only think, calculator and
    # web_search): Sergio could not see the screen or the camera. Be explicit.
    names = [str(n).strip() for n in current if str(n).strip()]
    for name in (*BASE_TOOLS, *DESKTOP_TOOLS):
        if name not in names:
            names.append(name)
    tools["enabled"] = names
    agent = doc.setdefault("agent", tomlkit.table())
    agent["max_turns"] = max(int(agent.get("max_turns", 10)), MIN_TURNS)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(tomlkit.dumps(doc))


CLOUD_PREFIXES = ("kimi", "moonshot", "gemini")
GEMINI_MAIN = "gemini-3.8-flash"
# Older Gemini defaults Sergio used before; upgraded automatically.
OLD_GEMINI = {"gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-flash"}


def prefer_cloud(config_path: Path, env: dict[str, str]) -> str:
    """Use Kimi (or Gemini) as the brain when its key is saved.

    The local model is slow with Sergio's long instructions and some GPUs
    crash on them, so a saved cloud key always wins; the local model stays as
    the fallback. Returns the model in use ("" if only the local one).
    """
    import tomlkit

    doc = (
        tomlkit.parse(config_path.read_text())
        if config_path.exists()
        else tomlkit.document()
    )
    intel = doc.setdefault("intelligence", tomlkit.table())
    current = str(intel.get("default_model", "") or "")
    if current in OLD_GEMINI and env.get("GEMINI_API_KEY"):
        intel["default_model"] = GEMINI_MAIN
        config_path.write_text(tomlkit.dumps(doc))
        return GEMINI_MAIN
    if current.lower().startswith(CLOUD_PREFIXES):
        return current
    if env.get("GEMINI_API_KEY"):
        chosen = GEMINI_MAIN
    elif env.get("MOONSHOT_API_KEY"):
        chosen = "kimi-k2.6"
    else:
        return ""
    intel["default_model"] = chosen
    if current and not intel.get("fallback_model"):
        intel["fallback_model"] = current
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(tomlkit.dumps(doc))
    return chosen


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
    """Sergio en Windows: compañero junto al cursor, voz y control de pantalla."""


def has_nvidia_gpu() -> bool:
    """An NVIDIA card in this PC (WSL shows its driver tools)."""
    return os.path.exists("/usr/lib/wsl/lib/nvidia-smi") or bool(
        shutil.which("nvidia-smi.exe") or shutil.which("nvidia-smi")
    )


def _do_instalar(vision: bool, gpu: bool = False) -> None:
    from openjarvis.cli.phone_cmd import read_env, write_env
    from openjarvis.cli.service_cmd import env_file
    from openjarvis.core.paths import get_config_dir
    from openjarvis.unified.paths import _REPO_ROOT

    if shutil.which("powershell.exe") is None:
        raise click.ClickException(
            "Ejecute esto en Ubuntu sobre Windows (WSL): Sergio Escritorio es una app de Windows."
        )
    # With an NVIDIA card Whisper runs the big, accurate model on the GPU;
    # without its CUDA libraries it fell back to the small one on the CPU
    # and understood less (the update never passed --gpu).
    gpu = gpu or has_nvidia_gpu()
    env_path = env_file()
    env = read_env(env_path)
    token = env.get("SERGIO_DESKTOP_TOKEN") or secrets.token_urlsafe(32)
    updates = {"SERGIO_DESKTOP_TOKEN": token}

    if vision:
        console.print(f"Descargando el modelo de visión {VISION_MODEL} (una sola vez)…")
        if pull_model(VISION_MODEL):
            updates["SERGIO_VISION_MODEL"] = VISION_MODEL
        else:
            console.print(
                f"[yellow]No se pudo descargar; más tarde ejecute en PowerShell: "
                f"ollama pull {VISION_MODEL}[/yellow]"
            )
    write_env(env_path, updates)
    enable_tools(get_config_dir() / "config.toml")
    brain = prefer_cloud(get_config_dir() / "config.toml", env)
    if brain:
        console.print(f"Sergio piensa con [bold]{brain}[/bold] (nube).")
    else:
        console.print(
            "[yellow]Sergio usa el modelo local, que es lento y en algunas "
            "tarjetas se cae. Pon tu clave de Gemini: sergio nube configurar "
            "--gemini TU_CLAVE[/yellow]"
        )

    console.print("Actualizando las librerías de Sergio en Ubuntu…")
    if not sync_server():
        console.print(
            "[yellow]No pude actualizar las librerías del servidor ahora; "
            "lo demás funciona.[/yellow]"
        )

    clean_server(_REPO_ROOT)

    script = _wslpath(_REPO_ROOT / "scripts" / "instalar-escritorio.ps1")
    source = _wslpath(_REPO_ROOT / "windows")
    console.print("Instalando en Windows (unos minutos la primera vez)…")
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
            "Falló el instalador de Windows (vea los mensajes de arriba)."
        )

    # Load the token and the new tools into the running Sergio.
    restarted = subprocess.run(
        ["systemctl", "--user", "try-restart", "sergio.service"],
        capture_output=True,
        check=False,
    )
    if restarted.returncode == 0:
        from openjarvis.cli.service_cmd import wait_for_server
        from openjarvis.core.config import load_config

        console.print("Reiniciando Sergio con los cambios…")
        port = load_config().server.port
        if not wait_for_server(f"http://127.0.0.1:{port}"):
            console.print(
                "[yellow]Sergio tarda en arrancar. Mira: "
                "journalctl --user -u sergio -n 50[/yellow]"
            )
    console.print(
        "\n[green]Instalación completada.[/green] Comprueba el personaje junto al cursor:\n"
        "  Di «Sergio, …»        y pídele lo que quieras\n"
        "  Ctrl+Espacio          hablarle sin decir su nombre\n"
        "  Ctrl+Alt+Fin          pausar / reanudar su control del mouse y teclado\n"
        "Ajustes y Salir: clic derecho en su icono junto al reloj."
    )


@escritorio.command("instalar")
@click.option(
    "--vision",
    is_flag=True,
    help=f"Descarga también el modelo local de visión ({VISION_MODEL}, ~6 GB) "
    "para describir imágenes en pantalla.",
)
@click.option(
    "--gpu",
    is_flag=True,
    help="Descarga también las librerías NVIDIA (~1 GB) para escuchar con "
    "el modelo grande de Whisper en la tarjeta gráfica.",
)
def instalar(vision: bool, gpu: bool = False) -> None:
    """Instala o actualiza Sergio Escritorio en Windows."""
    _do_instalar(vision=vision, gpu=gpu)


@escritorio.command("actualizar")
@click.option(
    "--vision", is_flag=True, help="Descarga también el modelo local de visión."
)
@click.option("--gpu", is_flag=True, help="Descarga librerías NVIDIA para Whisper.")
def actualizar(vision: bool, gpu: bool = False) -> None:
    """Actualiza Sergio Escritorio en Windows."""
    _do_instalar(vision=vision, gpu=gpu)


@escritorio.command("estado")
def estado() -> None:
    """Comprueba que Sergio pueda comunicarse con Sergio Escritorio."""
    from openjarvis.cli.phone_cmd import read_env
    from openjarvis.cli.service_cmd import env_file

    token = read_env(env_file()).get("SERGIO_DESKTOP_TOKEN", "")
    url = os.environ.get("SERGIO_DESKTOP_URL", "http://127.0.0.1:8765")
    if not token:
        raise click.ClickException(
            "No instalado: ejecute `sergio escritorio instalar`."
        )
    try:
        resp = httpx.get(
            f"{url}/health", headers={"Authorization": f"Bearer {token}"}, timeout=5
        )
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise click.ClickException(
            "Sergio Escritorio no responde. Abra «Sergio» desde el menú Inicio "
            f"de Windows. ({exc})"
        ) from exc
    if resp.status_code != 200:
        raise click.ClickException(
            f"Sergio Escritorio rechazó el token ({resp.status_code})."
        )
    state = "activo" if data.get("enabled") else "EN PAUSA (Ctrl+Alt+Fin)"
    console.print(f"Sergio Escritorio está encendido. Control de pantalla: {state}")


__all__ = [
    "actualizar",
    "BASE_TOOLS",
    "clean_server",
    "CLOUD_PREFIXES",
    "DESKTOP_TOOLS",
    "enable_tools",
    "escritorio",
    "estado",
    "GEMINI_MAIN",
    "instalar",
    "MIN_TURNS",
    "OLD_GEMINI",
    "prefer_cloud",
    "pull_model",
    "SERVER_EXTRAS",
    "sync_server",
    "VISION_MODEL",
]

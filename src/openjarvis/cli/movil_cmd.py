"""``sergio movil``: use Sergio from your phone.

Opens a Cloudflare quick tunnel (HTTPS, no account) to this computer's
Sergio server and shows a QR code. Scanning it opens Sergio on the phone,
already paired; "Add to home screen" installs it like an app (PWA). Only
requests carrying the phone token get past the tunnel (see
``openjarvis.server.mobile``); the desktop app keeps working unchanged.
The tunnel lives while this command runs; Ctrl+C closes it.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

console = Console()
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"


def _home() -> Path:
    return Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")


def _server_port() -> int:
    try:
        from openjarvis.core.config import load_config

        return int(load_config().server.port or 8000)
    except Exception:  # noqa: BLE001
        return 8000


def find_cloudflared() -> Optional[str]:
    local = _home() / "bin" / "cloudflared"
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which("cloudflared")


def download_cloudflared() -> str:
    """Fetch Cloudflare's official Linux binary into ~/.openjarvis/bin."""
    import httpx

    if sys.platform != "linux":
        raise click.ClickException(
            "Instale cloudflared desde https://developers.cloudflare.com/cloudflare-one/"
            "connections/connect-networks/downloads/ y repita."
        )
    arch = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(platform.machine().lower(), "amd64")
    target = _home() / "bin" / "cloudflared"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    console.print(
        "[dim]Descargando cloudflared (programa oficial de Cloudflare, ~40 MB)…[/dim]"
    )
    with httpx.stream(
        "GET", CLOUDFLARED_URL.format(arch=arch), follow_redirects=True, timeout=120
    ) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    tmp.replace(target)
    return str(target)


def render_qr(text: str) -> str:
    """The QR code as terminal text (needs ``segno``), else ''."""
    try:
        import io

        import segno
    except ImportError:
        return ""
    buffer = io.StringIO()
    segno.make(text, error="m").terminal(out=buffer, compact=True, border=2)
    return buffer.getvalue()


def ui_ready() -> bool:
    return (
        Path(__file__).resolve().parents[1] / "server" / "static" / "index.html"
    ).is_file()


def build_ui() -> bool:
    """Build the web app once (needs Node.js); True when it is ready."""
    if ui_ready():
        return True
    frontend = Path(__file__).resolve().parents[3] / "frontend"
    npm = shutil.which("npm")
    if not frontend.is_dir() or not npm:
        return False
    console.print("[dim]Preparando la app web (solo la primera vez, 1–3 min)…[/dim]")
    steps = [[npm, "ci", "--no-audit", "--no-fund"], [npm, "run", "build"]]
    for cmd in steps:
        if subprocess.run(cmd, cwd=frontend, capture_output=True).returncode != 0:
            return False
    return ui_ready()


def _show_pairing(url: str) -> None:
    from openjarvis.server.mobile import ensure_token, pair_url

    link = pair_url(url, ensure_token())
    qr = render_qr(link)
    console.print("\n[bold]Escanee este código con la cámara del teléfono:[/bold]\n")
    if qr:
        console.print(qr, highlight=False, markup=False)
    console.print(f"[dim]O abra este enlace en el teléfono:[/dim]\n{link}\n")
    console.print(
        "Luego, en el menú del navegador, elija [bold]«Añadir a pantalla de inicio»[/bold] "
        "para tenerlo como app.\n"
        "[yellow]Este enlace es una llave: quien lo tenga puede usar a Sergio. "
        "No lo comparta.[/yellow] Para desvincular todos los teléfonos: "
        "[bold]sergio movil olvidar[/bold]\n"
    )


@click.group("movil", invoke_without_command=True)
@click.option(
    "--sin-tunel",
    "no_tunnel",
    is_flag=True,
    help="Solo muestra el enlace local (misma red).",
)
@click.pass_context
def movil(ctx: click.Context, no_tunnel: bool) -> None:
    """Usar Sergio desde el teléfono: túnel seguro y código QR."""
    if ctx.invoked_subcommand is not None:
        return
    import httpx

    port = _server_port()
    try:
        httpx.get(
            f"http://127.0.0.1:{port}/health", timeout=3, trust_env=False
        ).raise_for_status()
    except Exception:  # noqa: BLE001
        raise click.ClickException(
            "Sergio no está encendido. Enciéndalo con: sergio servicio encender"
        ) from None
    if not build_ui():
        console.print(
            "[yellow]La app web no está construida y no encontré Node.js para construirla. "
            "Desde el teléfono solo funcionará la API.[/yellow]"
        )
    if no_tunnel:
        _show_pairing(f"http://127.0.0.1:{port}")
        console.print(
            "[dim]Este enlace solo sirve en este equipo o en su red si expuso el puerto.[/dim]"
        )
        return
    binary = find_cloudflared() or download_cloudflared()
    from openjarvis.server.mobile import parse_tunnel_url

    console.print("Abriendo un túnel seguro (HTTPS)…")
    proc = subprocess.Popen(
        [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    url = None
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            url = url or parse_tunnel_url(line)
            if url:
                break
        if not url:
            raise click.ClickException(
                "cloudflared terminó sin dar una dirección. Repita en un momento."
            )
        _show_pairing(url)
        console.print(
            "[dim]El túnel queda abierto mientras esta ventana siga abierta. Ctrl+C lo cierra.[/dim]"
        )
        proc.wait()
    except KeyboardInterrupt:
        console.print(
            "\nTúnel cerrado. El teléfono ya no llega a Sergio hasta que vuelva a abrirlo."
        )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


@movil.command("olvidar")
def olvidar() -> None:
    """Desvincula todos los teléfonos (crea un token nuevo)."""
    from openjarvis.server.mobile import ensure_token

    ensure_token(renew=True)
    console.print(
        "Listo: los teléfonos vinculados ya no pueden entrar. Vuelva a escanear el QR para usar uno."
    )


@movil.command("estado")
def estado() -> None:
    """Muestra si hay un teléfono vinculado y si cloudflared está listo."""
    from openjarvis.server.mobile import current_token

    console.print(f"Teléfono vinculado: {'sí' if current_token() else 'no'}")
    console.print(
        f"cloudflared: {find_cloudflared() or 'no instalado (se descarga solo)'}"
    )
    console.print(f"App web: {'lista' if ui_ready() else 'sin construir'}")


__all__ = [
    "build_ui",
    "CLOUDFLARED_URL",
    "download_cloudflared",
    "estado",
    "find_cloudflared",
    "movil",
    "olvidar",
    "render_qr",
    "ui_ready",
]

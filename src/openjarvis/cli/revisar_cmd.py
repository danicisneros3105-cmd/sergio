"""``sergio revisar`` — test every part Sergio needs and fix what it can."""

from __future__ import annotations

import io
import os
import wave

import click
import httpx
from rich.console import Console
from rich.markup import escape

console = Console()
DEFAULT_MODEL = "qwen3:8b"


def _silence_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\0\0" * 16000)
    return buf.getvalue()


def _detail(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("detail") or resp.text)[:300]
    except ValueError:
        return resp.text[:300]


def _ok(name: str) -> None:
    console.print(f"[green]OK[/green]   {name}")


def _bad(name: str, why: str) -> None:
    console.print(f"[red]FALLA[/red] {name}: {escape(why)}")


@click.command("revisar")
def revisar() -> None:
    """Check Ollama, the model, chat, voice, hearing and the cursor companion."""
    from openjarvis.cli.phone_cmd import read_env
    from openjarvis.cli.service_cmd import env_file
    from openjarvis.core.config import load_config

    cfg = load_config()
    failures = 0
    model = cfg.intelligence.default_model or DEFAULT_MODEL
    host = (
        cfg.engine.ollama.host
        or os.environ.get("OLLAMA_HOST")
        or "http://127.0.0.1:11434"
    ).rstrip("/")
    if "://" not in host:
        host = "http://" + host
    base = f"http://127.0.0.1:{cfg.server.port}"

    # 1. Ollama and the model
    try:
        tags = httpx.get(f"{host}/api/tags", timeout=5).json()
        names = {m.get("name") for m in tags.get("models", [])}
        if model in names or f"{model}:latest" in names:
            _ok(f"Ollama y el modelo {model}")
        else:
            console.print(f"Descargando el modelo {model} (unos 5 GB, solo una vez)…")
            resp = httpx.post(
                f"{host}/api/pull", json={"model": model, "stream": False}, timeout=None
            )
            if resp.status_code == 200:
                _ok(f"Modelo {model} descargado")
            else:
                failures += 1
                _bad(f"modelo {model}", _detail(resp))
    except httpx.HTTPError as exc:
        failures += 1
        _bad("Ollama", f"no responde en {host} ({exc}). Abre la app Ollama en Windows.")

    # 2. Sergio's server
    try:
        httpx.get(f"{base}/health", timeout=5).raise_for_status()
        _ok("Sergio está encendido")
    except httpx.HTTPError:
        _bad("Sergio", "no está encendido: ejecuta `sergio servicio encender`")
        raise SystemExit(1)

    # 3. Chat, 4. voice, 5. hearing
    checks = [
        (
            "Chat (el modelo responde)",
            lambda: httpx.post(
                f"{base}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Responde solo: ok"}],
                    "stream": False,
                },
                timeout=300,
            ),
        ),
        (
            "Voz (Sergio habla)",
            lambda: httpx.post(
                f"{base}/v1/speech/synthesize", json={"text": "Hola"}, timeout=600
            ),
        ),
        (
            "Oído (Sergio entiende audio)",
            lambda: httpx.post(
                f"{base}/v1/speech/transcribe",
                files={"file": ("prueba.wav", _silence_wav(), "audio/wav")},
                data={"language": "es"},
                timeout=600,
            ),
        ),
    ]
    for name, call in checks:
        console.print(f"Probando: {name}…")
        try:
            resp = call()
        except httpx.HTTPError as exc:
            failures += 1
            _bad(name, str(exc))
            continue
        if resp.status_code == 200:
            _ok(name)
        else:
            failures += 1
            _bad(name, f"{resp.status_code} {_detail(resp)}")

    # 6. Cursor companion (Windows side)
    token = read_env(env_file()).get("SERGIO_DESKTOP_TOKEN", "")
    if token:
        try:
            resp = httpx.get(
                "http://127.0.0.1:8765/health",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            if resp.status_code == 200:
                _ok("Compañero del cursor conectado")
            else:
                failures += 1
                _bad("compañero del cursor", f"rechazó la clave ({resp.status_code})")
        except httpx.HTTPError:
            failures += 1
            _bad(
                "compañero del cursor",
                "no responde: ábrelo desde el menú Inicio (Sergio)",
            )
    else:
        console.print("(Compañero del cursor no instalado: sergio escritorio instalar)")

    if failures:
        console.print(f"\n{failures} cosa(s) fallaron. Copia estas líneas y envíalas.")
        raise SystemExit(1)
    console.print("\n[green]Todo funciona.[/green]")

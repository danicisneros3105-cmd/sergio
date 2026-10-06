"""``sergio revisar`` — test every part Sergio needs and fix what it can."""

from __future__ import annotations

import base64
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


# A 64x64 red square: the vision check asks its colour.
_RED_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8l"
    "JCIfIiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoLCw4NDhwQEBw7KCIo"
    "Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAAR"
    "CABAAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAA"
    "AgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkK"
    "FhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWG"
    "h4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl"
    "5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA"
    "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk"
    "NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOE"
    "hYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk"
    "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDmaKKK8Q/UAooooAKKKKACiiigAooooAKK"
    "KKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigD//Z"
)


def _ok(name: str) -> None:
    console.print(f"[green]OK[/green]   {name}")


def _bad(name: str, why: str) -> None:
    console.print(f"[red]FALLA[/red] {name}: {escape(why)}")


def _print_companion_diag(token: str) -> None:
    """What the companion's ear is doing: microphone, levels, last errors."""
    try:
        diag = httpx.get(
            "http://127.0.0.1:8765/diag",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        ).json()
    except (httpx.HTTPError, ValueError):
        return
    mic = diag.get("microphone") or "ninguno"
    peak = diag.get("peak_level")
    console.print(f"  Micrófono: {escape(str(mic))}")
    if peak is not None:
        threshold = float(diag.get("threshold") or 110)
        if float(peak) < threshold:
            hint = (
                " — MUY BAJO: no llega al nivel de voz "
                f"({threshold:.0f}). Habla y vuelve a probar; si sigue bajo, sube "
                "el volumen del micrófono en Windows → Sonido → Entrada."
            )
        else:
            hint = " (bien: te oye)"
        console.print(f"  Volumen más alto oído (últimos 30 s): {peak}{hint}")
    for key, label in (
        ("whisper", "Oído (Whisper)"),
        ("brain", "Cerebro usado"),
        ("last_heard", "Lo último que oyó"),
        ("last_error", "Último error"),
        ("log", "Registro"),
    ):
        if diag.get(key):
            console.print(f"  {label}: {escape(str(diag[key]))[:300]}")


def _probe_ollama(host: str, model: str) -> None:
    """Ask Ollama directly so its own error (memory, model) is visible."""
    console.print(f"  Preguntando directo a Ollama con {model}…")
    try:
        resp = httpx.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "di ok"}],
                "stream": False,
                "think": False,
            },
            timeout=600,
        )
    except httpx.HTTPError as exc:
        console.print(f"  Ollama no respondió: {escape(str(exc))}")
        return
    if resp.status_code == 200:
        console.print(
            "  Ollama responde bien solo: el fallo está en Sergio (envía esto)."
        )
    else:
        console.print(f"  Ollama dice: {escape(_detail(resp))}")


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

    # 1. Ollama and the model (cloud models are checked by the chat test)
    cloud_prefixes = ("kimi", "moonshot", "gemini", "gpt", "claude", "deepseek")
    if model.lower().startswith(cloud_prefixes):
        _ok(f"Modelo en la nube: {model} (respaldo local: qwen3:8b)")
        model_for_ollama = cfg.intelligence.fallback_model or DEFAULT_MODEL
    else:
        model_for_ollama = model
    local = model_for_ollama
    try:
        tags = httpx.get(f"{host}/api/tags", timeout=5).json()
        names = {m.get("name") for m in tags.get("models", [])}
        if local in names or f"{local}:latest" in names:
            _ok(f"Ollama y el modelo {local}")
        else:
            console.print(f"Descargando el modelo {local} (unos 5 GB, solo una vez)…")
            resp = httpx.post(
                f"{host}/api/pull",
                json={"model": local, "stream": False},
                timeout=None,
            )
            if resp.status_code == 200:
                _ok(f"Modelo {local} descargado")
            else:
                failures += 1
                _bad(f"modelo {local}", _detail(resp))
    except httpx.HTTPError as exc:
        failures += 1
        _bad("Ollama", f"no responde en {host} ({exc}). Abre la app Ollama en Windows.")

    # 2. Sergio's server
    # It may have just been (re)started: give it up to two minutes.
    import subprocess
    import time

    deadline = time.monotonic() + 120
    while True:
        try:
            httpx.get(f"{base}/health", timeout=5).raise_for_status()
            _ok("Sergio está encendido")
            break
        except httpx.HTTPError:
            if time.monotonic() > deadline:
                log = subprocess.run(
                    ["journalctl", "--user", "-u", "sergio", "-n", "25", "--no-pager"],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout
                _bad("Sergio", "no arranca. Últimas líneas de su registro:")
                console.print(escape(log or "(sin registro)"))
                raise SystemExit(1)
            console.print("Esperando a que Sergio arranque…")
            time.sleep(5)

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
            "Vista (la cámara: Kimi/Gemini ven imágenes)",
            lambda: httpx.post(
                f"{base}/v1/faces/look",
                files={
                    "image": ("rojo.jpg", base64.b64decode(_RED_JPEG_B64), "image/jpeg")
                },
                data={"question": "¿De qué color es este cuadrado? Una palabra."},
                timeout=200,
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
            if name.startswith("Chat"):
                detail = _detail(resp)
                if "CUDA error" in detail or "0xc0000409" in detail:
                    console.print(
                        "  El modelo local se cae en tu tarjeta gráfica con las "
                        "instrucciones largas de Sergio. Solución: usa Gemini "
                        "(sergio nube configurar --gemini TU_CLAVE)."
                    )
                elif model == model_for_ollama:
                    _probe_ollama(host, model)

    # 6. The 3D globe (God's Eye View): started on demand if needed
    console.print("Probando: Globo 3D (God's Eye View)… (la 1.a vez tarda)")
    try:
        resp = httpx.post(f"{base}/v1/world/open", timeout=240)
        if resp.status_code == 200:
            _ok(f"Globo 3D en {resp.json().get('url')}")
        else:
            failures += 1
            _bad("Globo 3D", _detail(resp))
    except httpx.HTTPError as exc:
        failures += 1
        _bad("Globo 3D", str(exc))

    # 7. Cursor companion (Windows side)
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
                _print_companion_diag(token)
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

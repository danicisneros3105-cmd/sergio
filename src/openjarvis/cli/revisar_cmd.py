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

from openjarvis.cli.probar_cmd import run_with_limit

console = Console()
DEFAULT_MODEL = "qwen3:8b"
CHECK_TIMEOUT = (
    120.0  # one check (chat, voice, sight, hearing) before it counts as failed
)
PULL_LIMIT = 45 * 60.0  # a local model download, with progress, before giving up


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
            timeout=CHECK_TIMEOUT,
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


def _pull(host: str, model: str, limit: float = PULL_LIMIT) -> bool:
    """Download a local model showing progress (never a silent wait)."""
    import json
    import time

    console.print(f"Descargando el modelo {model} (varios GB, solo una vez)…")
    started = time.monotonic()
    shown = -10
    try:
        with httpx.stream(
            "POST",
            f"{host}/api/pull",
            json={"model": model, "stream": True},
            timeout=httpx.Timeout(60, connect=5),
        ) as resp:
            if resp.status_code != 200:
                resp.read()
                _bad(f"modelo {model}", _detail(resp))
                return False
            for line in resp.iter_lines():
                if time.monotonic() - started > limit:
                    _bad(
                        f"modelo {model}",
                        f"la descarga pasó de {limit / 60:.0f} min; "
                        f"termínala con: ollama pull {model}",
                    )
                    return False
                try:
                    event = json.loads(line or "{}")
                except ValueError:
                    continue
                if event.get("error"):
                    _bad(f"modelo {model}", str(event["error"]))
                    return False
                total, done = event.get("total") or 0, event.get("completed") or 0
                if total:
                    pct = int(100 * done / total)
                    if pct >= shown + 10:
                        shown = pct
                        console.print(f"  {pct}% de {total / 1e9:.1f} GB")
        return True
    except httpx.HTTPError as exc:
        _bad(
            f"modelo {model}",
            f"la descarga se cortó ({exc}); repite o usa: ollama pull {model}",
        )
        return False


@click.command("revisar")
def revisar() -> None:
    """Check Ollama, the model, chat, voice, hearing and the cursor companion."""
    try:
        _revisar()
    except KeyboardInterrupt:
        console.print("\n[yellow]Revisión cancelada.[/yellow]")
        raise SystemExit(130) from None


def _revisar() -> None:
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
    cloud = model.lower().startswith(cloud_prefixes)
    local = (cfg.intelligence.fallback_model or DEFAULT_MODEL) if cloud else model
    try:
        tags = httpx.get(f"{host}/api/tags", timeout=5).json()
        names = {m.get("name") for m in tags.get("models", [])}
        have_local = local in names or f"{local}:latest" in names
        if cloud:
            # A cloud brain needs nothing local: never download gigabytes here.
            _ok(
                f"Modelo en la nube: {model}"
                + (
                    f" (respaldo local {local} listo)"
                    if have_local
                    else f" (sin respaldo local; opcional: ollama pull {local})"
                )
            )
        elif have_local:
            _ok(f"Ollama y el modelo {local}")
        elif _pull(host, local):
            _ok(f"Modelo {local} descargado")
        else:
            failures += 1
    except httpx.HTTPError as exc:
        if cloud:
            _ok(f"Modelo en la nube: {model} (Ollama no está; no hace falta)")
        else:
            failures += 1
            _bad(
                "Ollama",
                f"no responde en {host} ({exc}). Abre la app Ollama en Windows.",
            )

    # 2. Sergio's server
    # It may have just been (re)started, or be switched off: ensure_server
    # switches it on if needed and reports progress instead of waiting mute.
    from openjarvis.cli.service_cmd import bypass_proxy_for_local, ensure_server

    bypass_proxy_for_local()
    console.print("Comprobando que Sergio esté encendido…")
    if not ensure_server(base, lambda line: console.print(escape(line))):
        raise SystemExit(1)
    _ok("Sergio está encendido")

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
                timeout=CHECK_TIMEOUT,
            ),
        ),
        (
            "Voz (Sergio habla)",
            lambda: httpx.post(
                f"{base}/v1/speech/synthesize",
                json={"text": "Hola"},
                timeout=CHECK_TIMEOUT,
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
                timeout=CHECK_TIMEOUT,
            ),
        ),
        (
            "Oído (Sergio entiende audio)",
            lambda: httpx.post(
                f"{base}/v1/speech/transcribe",
                files={"file": ("prueba.wav", _silence_wav(), "audio/wav")},
                data={"language": "es"},
                timeout=CHECK_TIMEOUT,
            ),
        ),
    ]
    for name, call in checks:
        console.print(f"Probando: {name}…")
        try:
            resp = run_with_limit(call, CHECK_TIMEOUT * 1.1 + 1)
        except (httpx.HTTPError, TimeoutError) as exc:
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
                elif not cloud:
                    _probe_ollama(host, model)

    # 6. Places and weather (God's Eye View's data; the globe is not shown)
    console.print("Probando: Lugares y clima…")
    try:
        resp = run_with_limit(
            lambda: httpx.get(
                f"{base}/v1/world/place", params={"q": "Quito"}, timeout=40
            ),
            60,
        )
        if resp.status_code == 200:
            _ok(str(resp.json().get("text") or "")[:90])
        else:
            failures += 1
            _bad("Lugares y clima", _detail(resp))
    except (httpx.HTTPError, TimeoutError) as exc:
        failures += 1
        _bad("Lugares y clima", str(exc))

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


__all__ = [
    "CHECK_TIMEOUT",
    "DEFAULT_MODEL",
    "PULL_LIMIT",
    "revisar",
]

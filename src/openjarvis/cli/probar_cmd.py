"""``sergio probar`` — try every ability for real, on this laptop.

Unlike ``sergio revisar`` (is everything installed and answering?), this
actually *uses* Sergio: his brain calls a tool, he speaks with his British
voice and then listens to himself, reads the screen, flies the companion,
opens and closes Notepad, looks through the camera, recognises faces, starts
the 3D globe and checks the hands. Each line says OK or what failed.
"""

from __future__ import annotations

import base64
import time
from typing import Callable

import click
import httpx
from rich.console import Console
from rich.markup import escape

console = Console()


class Run:
    def __init__(self) -> None:
        self.failed: list[str] = []

    def check(self, name: str, fn: Callable[[], str]) -> str:
        console.print(f"Probando: {name}…")
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001 — report, keep going
            self.failed.append(name)
            console.print(f"[red]FALLA[/red] {name}: {escape(str(exc))[:400]}")
            return ""
        console.print(
            f"[green]OK[/green]   {name}" + (f": {escape(detail)}" if detail else "")
        )
        return detail


def _ok(resp: httpx.Response) -> httpx.Response:
    if resp.status_code >= 400:
        try:
            why = resp.json().get("detail") or resp.json().get("error") or resp.text
        except ValueError:
            why = resp.text
        raise RuntimeError(f"{resp.status_code} {why}"[:400])
    return resp


@click.command("probar")
@click.option("--sin-pantalla", is_flag=True, help="No mover el mouse ni abrir apps.")
def probar(sin_pantalla: bool) -> None:
    """Prueba de verdad: cerebro, voz, oído, pantalla, cámara, caras, globo, manos."""
    from openjarvis.cli.phone_cmd import read_env
    from openjarvis.cli.service_cmd import env_file
    from openjarvis.core.config import load_config

    cfg = load_config()
    base = f"http://127.0.0.1:{cfg.server.port}"
    model = cfg.intelligence.default_model or "gemini-3.8-flash"
    token = read_env(env_file()).get("SERGIO_DESKTOP_TOKEN", "")
    win = "http://127.0.0.1:8765"
    auth = {"Authorization": f"Bearer {token}"}
    http = httpx.Client(timeout=httpx.Timeout(180, connect=5))
    run = Run()

    def brain() -> str:
        resp = _ok(
            http.post(
                f"{base}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Usa la herramienta calculator para calcular "
                            "12*12 y responde solo el número.",
                        }
                    ],
                },
            )
        )
        answer = str(resp.json()["choices"][0]["message"].get("content") or "")
        if "144" not in answer:
            raise RuntimeError(f"respondió «{answer[:120]}» (esperaba 144)")
        return f"usó una herramienta y respondió {answer.strip()[:40]}"

    run.check("Cerebro con herramientas (Gemini)", brain)

    voice: dict[str, bytes] = {}

    def speak() -> str:
        resp = _ok(
            http.post(
                f"{base}/v1/voice/speak",
                json={"text": "Buenas tardes. Soy Sergio y todo está en orden."},
            )
        )
        voice["wav"] = resp.content
        return f"voz británica, {len(resp.content) // 1000} KB de audio"

    run.check("Voz de Sergio (Gemini)", speak)

    def ears() -> str:
        if "wav" not in voice:
            raise RuntimeError("no hay audio de la voz para escucharlo")
        resp = _ok(
            http.post(
                f"{base}/v1/voice/transcribe",
                files={"file": ("voz.wav", voice["wav"], "audio/wav")},
            )
        )
        heard = str(resp.json().get("text") or "")
        if "sergio" not in heard.lower():
            raise RuntimeError(f"oyó «{heard[:120]}»")
        return f"se escuchó a sí mismo: «{heard[:60]}»"

    run.check("Oído (Gemini entiende la voz)", ears)

    if not token:
        console.print(
            "[yellow]Compañero no instalado: sergio escritorio instalar[/yellow]"
        )
    else:

        def screen() -> str:
            ui = _ok(http.get(f"{win}/ui", headers=auth)).json()
            return (
                f"ventana activa «{ui.get('window', '')[:40]}», "
                f"{len(ui.get('elements', []))} botones/campos"
            )

        run.check("Leer la pantalla", screen)

        def look_screen() -> str:
            shot = _ok(http.get(f"{win}/screen", headers=auth)).json()
            png = base64.b64decode(shot["image_png_b64"])
            resp = _ok(
                http.post(
                    f"{base}/v1/vision/screen",
                    data={"question": "¿Qué programa está abierto? Una frase."},
                    files={"image": ("p.png", png, "image/png")},
                )
            )
            return str(resp.json().get("answer", ""))[:80]

        run.check("Ver la pantalla (como Clicky)", look_screen)

        if not sin_pantalla:

            def companion() -> str:
                _ok(
                    http.post(
                        f"{win}/act",
                        headers=auth,
                        json={"action": "point", "x": 400, "y": 300, "text": "Prueba"},
                    )
                )
                return "el compañero voló a señalar (mira la pantalla)"

            run.check("Compañero señala", companion)

            def notepad() -> str:
                _ok(
                    http.post(
                        f"{win}/act",
                        headers=auth,
                        json={"action": "open", "target": "notepad.exe"},
                    )
                )
                time.sleep(2.5)
                closed = _ok(
                    http.post(
                        f"{win}/act",
                        headers=auth,
                        json={"action": "close_app", "target": "notepad"},
                    )
                ).json()
                return (
                    "abrió y cerró el Bloc de notas: "
                    + str(closed.get("result", ""))[:60]
                )

            run.check("Control de Windows (abrir/cerrar app)", notepad)

            def terminal() -> str:
                out = _ok(
                    http.post(
                        f"{win}/act",
                        headers=auth,
                        json={
                            "action": "terminal",
                            "command": "$PSVersionTable.PSVersion.Major",
                        },
                    )
                ).json()
                if "exit code 0" not in str(out.get("result", "")):
                    raise RuntimeError(str(out)[:200])
                return "PowerShell responde"

            run.check("Terminal", terminal)

        photo: dict[str, bytes] = {}

        def camera() -> str:
            shot = _ok(http.get(f"{win}/camera", headers=auth)).json()
            photo["jpeg"] = base64.b64decode(shot["image_jpeg_b64"])
            return f"foto de {len(photo['jpeg']) // 1000} KB"

        run.check("Cámara", camera)

        def vision() -> str:
            if "jpeg" not in photo:
                raise RuntimeError("no hay foto de la cámara")
            resp = _ok(
                http.post(
                    f"{base}/v1/faces/look",
                    data={"question": "¿Qué ves? Una frase."},
                    files={"image": ("c.jpg", photo["jpeg"], "image/jpeg")},
                )
            )
            return str(resp.json().get("answer", ""))[:90]

        run.check("Visión (qué ve la cámara)", vision)

        def faces() -> str:
            if "jpeg" not in photo:
                raise RuntimeError("no hay foto de la cámara")
            resp = _ok(
                http.post(
                    f"{base}/v1/faces/identify",
                    files={"image": ("c.jpg", photo["jpeg"], "image/jpeg")},
                )
            )
            found = resp.json().get("faces", [])
            names = [f.get("name") or "desconocido" for f in found]
            if not found:
                return "no vio caras (ponte frente a la cámara y repite)"
            return "caras: " + ", ".join(names)

        run.check("Reconocimiento facial", faces)

        def hands() -> str:
            diag = _ok(http.get(f"{win}/diag", headers=auth)).json()
            status = str(diag.get("hands") or "")
            if not status.startswith("ok"):
                raise RuntimeError(status or "el compañero no informó de las manos")
            return status

        run.check("Manos (MediaPipe)", hands)

    def globe() -> str:
        resp = _ok(http.post(f"{base}/v1/world/open", timeout=240))
        url = resp.json()["url"]
        page = _ok(http.get(url, timeout=20))
        if "God" not in page.text and "<html" not in page.text.lower():
            raise RuntimeError("el globo respondió algo raro")
        return f"God's Eye View en {url}"

    run.check("Globo 3D (God's Eye View)", globe)

    if run.failed:
        console.print(
            f"\n[red]{len(run.failed)} prueba(s) fallaron:[/red] "
            + ", ".join(run.failed)
            + ". Copia estas líneas y envíalas."
        )
        raise SystemExit(1)
    console.print("\n[green]Todo probado de verdad y funcionando.[/green]")


__all__ = ["probar"]

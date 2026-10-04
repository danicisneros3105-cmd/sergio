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


class _Retrying:
    """An httpx client that tries once more when a connection is cut."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def _do(self, method: str, *args: object, **kwargs: object) -> httpx.Response:
        try:
            return getattr(self.client, method)(*args, **kwargs)
        except (httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteError):
            time.sleep(2)
            return getattr(self.client, method)(*args, **kwargs)

    def get(self, *args: object, **kwargs: object) -> httpx.Response:
        return self._do("get", *args, **kwargs)

    def post(self, *args: object, **kwargs: object) -> httpx.Response:
        return self._do("post", *args, **kwargs)


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
    http = _Retrying(httpx.Client(timeout=httpx.Timeout(180, connect=5)))
    run = Run()

    from openjarvis.cli.service_cmd import wait_for_server

    console.print("Esperando a que Sergio esté encendido…")
    if not wait_for_server(base, get=http.client.get):
        console.print(
            f"[red]Sergio no responde en {base}.[/red] Enciéndelo con: "
            "sergio servicio encender  (o mira: journalctl --user -u sergio -n 50)"
        )
        raise SystemExit(1)

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

    def call() -> str:
        return live_call(base)

    run.check("Llamada en tiempo real (Gemini Live)", call)

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
                started = time.monotonic()
                opened = _ok(
                    http.post(
                        f"{win}/act",
                        headers=auth,
                        json={"action": "open_app", "target": "bloc de notas"},
                    )
                ).json()
                took = time.monotonic() - started
                time.sleep(1.0)
                closed = _ok(
                    http.post(
                        f"{win}/act",
                        headers=auth,
                        json={"action": "close_app", "target": "notepad"},
                    )
                ).json()
                return (
                    f"abrió el Bloc de notas en {took:.1f} s "
                    f"({str(opened.get('result', ''))[:40]}) y lo cerró: "
                    + str(closed.get("result", ""))[:50]
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

        def photo_faces() -> str:
            if "jpeg" not in photo:
                raise RuntimeError("no hay foto de la cámara")
            resp = _ok(
                http.post(
                    f"{base}/v1/faces/photo",
                    files={"image": ("c.jpg", photo["jpeg"], "image/jpeg")},
                )
            )
            return str(resp.json().get("text", ""))[:110]

        run.check("Caras en fotos (red neuronal + 175 medidas)", photo_faces)

        def overhead() -> str:
            diag = _ok(http.get(f"{win}/diag", headers=auth, timeout=8)).json()
            where = diag.get("location") or {}
            lat, lon = where.get("lat"), where.get("lon")
            note = where.get("source", "")
            if lat is None:
                lat, lon, note = -2.9001, -79.0059, "sin ubicación de Windows: probé con Cuenca"
            started = time.monotonic()
            report = _ok(
                http.get(f"{base}/v1/world/overhead", params={"lat": lat, "lon": lon}, timeout=12)
            ).json()
            took = time.monotonic() - started
            return f"{took:.1f} s ({note}): {str(report.get('text', ''))[:120]}"

        run.check("Vuelo justo encima de ti (ADS-B en vivo)", overhead)

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

        def scene() -> str:
            if "jpeg" not in photo:
                raise RuntimeError("no hay foto de la cámara")
            resp = _ok(
                http.post(
                    f"{base}/v1/vision/scene",
                    files={"image": ("c.jpg", photo["jpeg"], "image/jpeg")},
                )
            )
            items = resp.json().get("items", [])
            if not items:
                return "no distinguió nada (apunta la cámara a ti o a objetos)"
            return ", ".join(
                (i.get("name") or i.get("label") or "?") for i in items[:6]
            )

        run.check("Analizar escena (personas, especies, objetos)", scene)

        def companion_parts() -> str:
            diag = _ok(http.get(f"{win}/diag", headers=auth)).json()
            parts = {
                "visión": diag.get("vision"),
                "hologramas": diag.get("holograms"),
                "llamada": diag.get("call"),
                "oído": diag.get("wake"),
                "gimnasio": diag.get("gym"),
            }
            missing = [k for k, v in parts.items() if v is None]
            if missing:
                raise RuntimeError(
                    "el compañero es una versión vieja; ejecuta sergio escritorio instalar"
                )
            bad = [f"{k}: {v}" for k, v in parts.items() if str(v).startswith(("sin ", "no "))]
            if bad:
                raise RuntimeError("; ".join(bad))
            return " | ".join(f"{k}: {v}" for k, v in parts.items())

        run.check("Cámara, hologramas, llamada, oído y gimnasio", companion_parts)

        def selftest(kind: str) -> dict:
            resp = http.post(
                f"{win}/selftest", headers=auth, json={"kind": kind}, timeout=60
            )
            if resp.status_code == 404:
                raise RuntimeError(
                    "el compañero es una versión vieja; ejecuta sergio escritorio instalar"
                )
            out = _ok(resp).json()
            if not out.get("ok"):
                raise RuntimeError(str(out.get("error") or out)[:300])
            return out

        def talk_call() -> str:
            out = selftest("call")
            return (
                f"conectó en {out.get('connect_s')} s, habló en {out.get('voice_s')} s "
                f"({out.get('model')}, eco {out.get('echo')}): «{str(out.get('said'))[:60]}»"
            )

        run.check("Hablarle a Sergio: llamada desde tu compañero", talk_call)

        def talk_turn() -> str:
            out = selftest("turn")
            return (
                f"pensó {out.get('think_s')} s, voz {out.get('voice_s')} s con "
                f"{out.get('voice')}: «{str(out.get('answer'))[:60]}»"
            )

        run.check("Hablarle a Sergio: por turnos", talk_turn)

        if not sin_pantalla:

            def open_by_voice() -> str:
                out = selftest("open")
                return f"«{out.get('said')}» → {out.get('answer')} en {out.get('took_s')} s"

            run.check("Abrir apps por voz («abre la calculadora»)", open_by_voice)

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

    if token:
        try:
            diag = http.get(f"{win}/diag", headers=auth, timeout=8).json()
        except Exception:  # noqa: BLE001
            diag = {}
        errors = diag.get("recent_errors") or []
        if errors:
            console.print("\n[yellow]Últimos errores del compañero (sergio.log):[/yellow]")
            for line in errors[-10:]:
                console.print(f"  {escape(str(line))}")
        if diag.get("voice_used"):
            console.print(f"Voz usada al hablar: {escape(str(diag['voice_used']))}")

    if run.failed:
        console.print(
            f"\n[red]{len(run.failed)} prueba(s) fallaron:[/red] "
            + ", ".join(run.failed)
            + ". Copia estas líneas y envíalas."
        )
        raise SystemExit(1)
    console.print("\n[green]Todo probado de verdad y funcionando.[/green]")


def live_call(base: str, timeout: float = 25.0) -> str:
    """Open a real call on /v1/live, ask one thing, and hear Sergio answer."""
    import json

    from websockets.sync.client import connect

    url = base.replace("http://", "ws://").replace("https://", "wss://") + "/v1/live"
    started = time.monotonic()
    audio = 0
    said: list[str] = []
    with connect(url, open_timeout=10, max_size=None) as ws:
        ws.send(json.dumps({"type": "start", "voice": "Algieba", "tools": []}))
        model = ""
        while not model:
            event = json.loads(ws.recv(timeout=timeout))
            if event.get("type") == "error":
                raise RuntimeError(event.get("message", "error"))
            model = str(event.get("model") or "") if event.get("type") == "ready" else ""
        ws.send(json.dumps({"type": "text", "text": "Prueba: responde solo «todo en orden»."}))
        first = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = ws.recv(timeout=timeout)
            if isinstance(msg, bytes):
                audio += len(msg)
                first = first or time.monotonic()
                continue
            event = json.loads(msg)
            if event.get("type") == "said":
                said.append(event.get("text", ""))
            if event.get("type") == "turn_complete" and audio:
                break
            if event.get("type") == "error":
                raise RuntimeError(event.get("message", "error"))
        ws.send(json.dumps({"type": "end"}))
    if not audio:
        raise RuntimeError(f"{model} no contestó con voz")
    return (
        f"{model} contestó «{''.join(said).strip()[:40]}» "
        f"({audio / 48000:.1f} s de voz, conectó en "
        f"{(first or started) - started:.1f} s)"
    )


__all__ = ["live_call", "probar"]

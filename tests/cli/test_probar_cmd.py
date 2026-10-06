"""`sergio probar`: every real-world check, against simulated servers."""

import base64
import json
import sys

import httpx
from click.testing import CliRunner

from openjarvis.cli import probar_cmd


BUSY_CALL = False


def _transport(fail=()):
    def handler(request):
        path = request.url.path
        if path in fail:
            return httpx.Response(502, json={"detail": f"{path} roto"})
        if path == "/v1/chat/completions":
            assert "calculator" in json.loads(request.content)["messages"][0]["content"]
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "144"}}]}
            )
        if path == "/v1/voice/speak":
            return httpx.Response(200, content=b"RIFF" + b"\0" * 4000)
        if path == "/v1/voice/transcribe":
            return httpx.Response(200, json={"text": "Buenas tardes. Soy Sergio."})
        if path == "/ui":
            return httpx.Response(200, json={"window": "Chrome", "elements": [{}] * 12})
        if path == "/screen":
            return httpx.Response(
                200, json={"image_png_b64": base64.b64encode(b"png").decode()}
            )
        if path == "/v1/vision/screen":
            return httpx.Response(200, json={"answer": "Chrome con YouTube."})
        if path == "/act":
            action = json.loads(request.content)["action"]
            result = (
                "exit code 0\noutput:\n7" if action == "terminal" else f"{action} ok"
            )
            return httpx.Response(200, json={"ok": True, "result": result})
        if path == "/camera":
            return httpx.Response(
                200, json={"image_jpeg_b64": base64.b64encode(b"jpg").decode()}
            )
        if path == "/v1/faces/look":
            return httpx.Response(200, json={"answer": "Una persona sonriendo."})
        if path == "/v1/faces/identify":
            return httpx.Response(200, json={"faces": [{"name": "Dani"}]})
        if path == "/diag":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "hands": "ok (modo off)",
                    "vision": "ok",
                    "holograms": "0 hologramas, modo mover; manos off",
                    "call": "lista",
                    "wake": "instantáneo (Vosk)",
                    "gym": "cada 12 min, el próximo en 9 min",
                    "location": {"lat": -2.9, "lon": -79.0, "source": "ubicación de Windows (±30 m)"},
                    "recent_errors": ["22:10:01 Gemini voice failed (429); using the neural voice"],
                    "voice_used": "Gemini (Algieba)",
                },
            )
        if path == "/selftest":
            kind = json.loads(request.content)["kind"]
            return httpx.Response(
                200,
                json={
                    "call": {"ok": True, "busy": True, "model": "gemini-3.8-live", "echo": "webrtc"}
                    if BUSY_CALL
                    else {"ok": True, "connect_s": 0.5, "voice_s": 1.1, "model": "gemini-3.8-live",
                             "echo": "webrtc", "said": "Son las tres."},
                    "turn": {"ok": True, "think_s": 1.2, "voice_s": 0.8,
                             "voice": "Gemini (Algieba)", "answer": "Son las tres."},
                    "open": {"ok": True, "said": "abre la calculadora",
                             "answer": "Abriendo Calculadora.", "took_s": 0.4},
                }[kind],
            )
        if path == "/v1/faces/photo":
            return httpx.Response(200, json={"text": "La cara: Dani (similitud 71%)."})
        if path == "/v1/world/overhead":
            assert request.url.params["lat"] == "-2.9"
            return httpx.Response(200, json={"text": "Justo encima de usted: vuelo LA1442."})
        if path == "/v1/vision/scene":
            return httpx.Response(
                200, json={"items": [{"label": "persona", "name": "Dani"}, {"label": "taza"}]}
            )
        if path == "/v1/world/open":
            return httpx.Response(200, json={"url": "http://127.0.0.1:4173/"})
        if request.url.port == 4173:
            return httpx.Response(
                200, text="<html><title>God's Eye View</title></html>"
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _run(monkeypatch, tmp_path, fail=()):
    real = httpx.Client
    monkeypatch.setattr(
        probar_cmd.httpx,
        "Client",
        lambda **kw: real(transport=_transport(fail), timeout=kw.get("timeout")),
    )
    env = tmp_path / "sergio.env"
    env.write_text("SERGIO_DESKTOP_TOKEN=t\n")
    monkeypatch.setattr("openjarvis.cli.service_cmd.env_file", lambda: env)
    monkeypatch.setattr(probar_cmd.time, "sleep", lambda s: None)
    from rich.console import Console

    monkeypatch.setattr(probar_cmd, "console", Console(width=400))
    monkeypatch.setattr(
        probar_cmd, "live_call", lambda base: "gemini-3.8-live contestó «Todo en orden»"
    )
    return CliRunner().invoke(probar_cmd.probar, [])


def test_everything_ok(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path)
    assert result.exit_code == 0, result.output
    for line in (
        "Cerebro con herramientas",
        "Voz de Sergio",
        "se escuchó a sí mismo",
        "Leer la pantalla",
        "Chrome con YouTube",
        "Compañero señala",
        "PowerShell responde",
        "Una persona sonriendo",
        "caras: Dani",
        "Manos (MediaPipe)",
        "God's Eye View en http://127.0.0.1:4173/",
        "gemini-3.8-live contestó",
        "Dani, taza",
        "hologramas: 0",
        "oído: instantáneo",
        "abrió el Bloc de notas en",
        "Caras en fotos",
        "La cara: Dani",
        "Justo encima de usted",
        "habló en 1.1 s",
        "con Gemini (Algieba)",
        "Abriendo Calculadora",
        "Últimos errores del compañero",
        "Gemini voice failed (429)",
        "Todo probado de verdad",
    ):
        assert line in result.output, line


def test_failures_are_reported_and_the_rest_still_runs(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, fail=("/v1/chat/completions", "/camera"))
    assert result.exit_code == 1
    assert "FALLA Cerebro con herramientas" in result.output
    assert "FALLA Cámara" in result.output
    assert "OK   Globo 3D" in result.output
    assert "6 prueba(s) fallaron" in result.output  # no photo: vision, faces x2, scene


def test_a_call_in_progress_is_not_a_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(sys.modules[__name__], "BUSY_CALL", True)
    result = _run(monkeypatch, tmp_path)
    assert result.exit_code == 0, result.output
    assert "ya estás en una llamada con gemini-3.8-live" in result.output

"""Camera: control-server endpoint, camera_look tool, vision fallbacks, voice."""

import base64
import json

import httpx

from openjarvis.tools import vision_look
from openjarvis.tools.desktop_tools import CameraLookTool

JPEG = b"\xff\xd8\xff\xe0fakejpeg"


def test_camera_endpoint_and_tool_end_to_end(control_server, monkeypatch):
    controller, url = control_server
    controller.camera = lambda: JPEG
    monkeypatch.setenv("SERGIO_DESKTOP_URL", url)
    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "secreto")
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")
    seen = {}
    real = httpx.Client()

    def handler(request):
        if request.url.host == "api.moonshot.ai":
            body = json.loads(request.content)
            seen.update(body)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Tienes una taza azul."}}]},
            )
        forwarded = real.send(request)
        return httpx.Response(forwarded.status_code, content=forwarded.content)

    tool = CameraLookTool(http=httpx.Client(transport=httpx.MockTransport(handler)))
    result = tool.execute(question="¿Qué tengo en la mano?")
    assert result.success and result.content.endswith("Tienes una taza azul.")
    content = seen["messages"][0]["content"]
    assert (
        content[0]["image_url"]["url"]
        == "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
    )
    assert "¿Qué tengo en la mano?" in content[1]["text"]
    assert seen["model"] == "kimi-k2.6" and seen["thinking"] == {"type": "disabled"}


def test_camera_missing_is_explained(control_server, monkeypatch):
    controller, url = control_server
    monkeypatch.setenv("SERGIO_DESKTOP_URL", url)
    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "secreto")
    controller.camera = None
    result = CameraLookTool().execute(question="qué ves")
    assert not result.success and "cámara" in result.content


def test_vision_falls_back_from_kimi_to_gemini(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")
    broken = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    monkeypatch.setattr(
        vision_look, "_gemini", lambda jpeg, prompt: "Un celular negro."
    )
    assert vision_look.ask_vision(JPEG, "qué tengo", broken) == "Un celular negro."


def test_no_vision_model_gives_a_clear_reason(monkeypatch):
    for key in (
        "MOONSHOT_API_KEY",
        "KIMI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "SERGIO_VISION_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    try:
        vision_look.ask_vision(JPEG, "qué ves", httpx.Client())
    except RuntimeError as exc:
        assert "Ningún modelo con visión" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_neural_voice_used_first_with_local_fallback(monkeypatch):
    from sergio_escritorio import neural_voice
    from sergio_escritorio.voice import SergioClient

    server = []

    def handler(request):
        server.append(request.url.path)
        return httpx.Response(200, content=b"RIFFlocal")

    client = SergioClient(
        "http://x", http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    client.voice = "es-EC-LuisNeural"
    monkeypatch.setattr(
        neural_voice, "synthesize", lambda text, voice: b"RIFFneural:" + voice.encode()
    )
    assert client.speak("hola") == b"RIFFneural:es-EC-LuisNeural" and server == []

    def offline(text, voice):
        raise OSError("no internet")

    monkeypatch.setattr(neural_voice, "synthesize", offline)
    assert client.speak("hola") == b"RIFFlocal"


# -- direct camera route ("¿qué tengo en la mano?") -------------------------
import pytest  # noqa: E402
from sergio_escritorio.voice import wants_camera  # noqa: E402


@pytest.mark.parametrize(
    ("text", "camera"),
    [
        ("¿Qué tengo en la mano?", True),
        ("que tengo en la mano", True),
        ("Mírame, ¿cómo me veo?", True),
        ("¿Cuántos dedos te muestro?", True),
        ("¿Quién está aquí?", True),
        ("abre Google y busca Nvidia", False),
        ("qué hora es", False),
    ],
)
def test_wants_camera(text, camera):
    assert wants_camera(text) is camera


def test_look_endpoint_answers_with_vision(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.faces import routes

    class Book:
        def identify(self, _data):
            return [type("M", (), {"name": "Dani"})()]

    monkeypatch.setattr(routes, "_get_book", lambda: Book())
    monkeypatch.setattr(
        vision_look, "ask_vision", lambda data, q: f"Una taza azul ({q})"
    )
    app = FastAPI()
    app.include_router(routes.router)
    resp = TestClient(app).post(
        "/v1/faces/look",
        data={"question": "¿qué tengo?"},
        files={"image": ("c.jpg", JPEG, "image/jpeg")},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "answer": "Veo a Dani. Una taza azul (¿qué tengo?)",
        "people": ["Dani"],
    }


def test_look_endpoint_reports_vision_failure(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.faces import routes

    def broken(_data, _q):
        raise RuntimeError("Ningún modelo con visión respondió")

    monkeypatch.setattr(routes, "_get_book", lambda: None)
    monkeypatch.setattr(vision_look, "ask_vision", broken)
    app = FastAPI()
    app.include_router(routes.router)
    resp = TestClient(app).post(
        "/v1/faces/look", files={"image": ("c.jpg", JPEG, "image/jpeg")}
    )
    assert resp.status_code == 502 and "visión" in resp.json()["detail"]

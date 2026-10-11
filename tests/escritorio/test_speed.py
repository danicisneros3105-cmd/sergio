"""Speed: instant commands, the fast chat path, speech that starts early,
actions that verify themselves, and automatic face recognition."""

import datetime
import json

import httpx
import pytest
from sergio_escritorio.control import Controller
from sergio_escritorio.quick import parse_quick, spoken_date, spoken_time
from sergio_escritorio.voice import (
    Assistant,
    SergioClient,
    needs_agent,
    no_emoji,
    split_sentences,
)


@pytest.mark.parametrize(
    ("said", "kind", "arg"),
    [
        ("abre Spotify", "open_app", "spotify"),
        (
            "Abre YouTube y busca Bad Bunny",
            "open_url",
            "https://www.youtube.com/results?search_query=bad+bunny",
        ),
        ("busca nvidia", "open_url", "https://www.google.com/search?q=nvidia"),
        (
            "busca recetas en youtube",
            "open_url",
            "https://www.youtube.com/results?search_query=recetas",
        ),
        ("abre amazon.com", "open_url", "https://amazon.com"),
        ("abre gmail", "open_url", "https://mail.google.com"),
        ("cierra Chrome", "close_app", "chrome"),
        ("sube el volumen", "volume", "up"),
        ("pausa la música", "key", "playpause"),
        ("¿Qué hora es?", "time", ""),
        ("abre la cámara", "camera", "on"),
        ("modo hologramas", "hands", "holo"),
        ("cállate", "stop", ""),
    ],
)
def test_instant_commands(said, kind, arg):
    q = parse_quick(said)
    assert q is not None and q.kind == kind and q.arg == arg


@pytest.mark.parametrize(
    "said",
    [
        "abre Google, busca Nvidia y entra al primer link",
        "cuéntame un chiste",
        "pon música relajante",
    ],
)
def test_complex_requests_go_to_the_ai(said):
    assert parse_quick(said) is None


def test_spoken_time_and_date():
    assert (
        spoken_time(datetime.datetime(2026, 10, 3, 15, 25))
        == "Son las 3 y 25 de la tarde."
    )
    assert (
        spoken_time(datetime.datetime(2026, 10, 3, 13, 0))
        == "Es la 1 en punto de la tarde."
    )
    assert spoken_date(datetime.datetime(2026, 10, 3)) == "Hoy es sábado 3 de octubre."


def test_chat_or_agent():
    assert not needs_agent("¿cómo estás?")
    assert not needs_agent("¿qué opinas de la inteligencia artificial?")
    assert needs_agent("¿qué clima hace en Quito?")
    assert needs_agent("sí, hazlo", after_agent=True)
    assert not needs_agent("sí", after_agent=False)


def test_emojis_never_reach_the_user():
    assert no_emoji("Hola 👋 señor ✨ todo listo 👍") == "Hola señor todo listo"


def test_split_sentences_starts_short():
    parts = split_sentences(
        "Buenas tardes, señor. El clima en Quito es templado, unos 14 grados con "
        "nubes. Por la tarde podría llover. ¿Desea que le avise?"
    )
    assert parts[0].startswith("Buenas tardes, señor.") and len(parts) >= 2
    assert split_sentences("Listo.") == ["Listo."]


def _client(handler):
    return SergioClient(
        "http://s.test", http=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_conversation_takes_the_fast_path_and_tasks_the_agent():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/v1/info":
            return httpx.Response(200, json={"model": "gemini-3.8-flash"})
        if request.url.path == "/v1/voice/chat":
            body = json.loads(request.content)
            assert body["model"] == "gemini-3.8-flash@low"
            assert "Ecuador" in body["messages"][0]["content"]
            return httpx.Response(200, json={"content": "Muy bien, gracias 😊"})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Hecho."}}]}
        )

    c = _client(handler)
    assert c.ask("¿cómo estás?") == "Muy bien, gracias"
    assert "/v1/voice/chat" in paths and "/v1/chat/completions" not in paths
    paths.clear()
    assert c.ask("abre spotify y pon algo de jazz") == "Hecho."
    assert "/v1/chat/completions" in paths
    paths.clear()
    c.ask("sí, dale")  # continues the task
    assert "/v1/chat/completions" in paths


def test_fast_path_falls_back_to_the_agent():
    def handler(request):
        if request.url.path == "/v1/info":
            return httpx.Response(200, json={"model": "gemini-3.8-flash"})
        if request.url.path == "/v1/voice/chat":
            return httpx.Response(502, json={"detail": "busy"})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Aquí estoy."}}]}
        )

    assert _client(handler).ask("hola") == "Aquí estoy."


class UI:
    def __init__(self):
        self.states, self.captions = [], []

    def state(self, name):
        self.states.append(name)

    def say(self, text):
        self.captions.append(text)


def test_instant_command_skips_the_ai():
    asked = []

    def handler(request):
        asked.append(request.url.path)
        return httpx.Response(200, content=b"RIFFvoz")

    done = []
    a = Assistant(
        _client(handler), ui=UI(), player=lambda w: None, chime=lambda f: None
    )
    a.quick = lambda q: done.append(q.kind) or "Abriendo Spotify."
    a.on_text("abre Spotify")
    assert done == ["open_app"]
    assert asked == ["/v1/voice/speak"] or "/v1/chat/completions" not in asked
    assert a.ui.captions[-1] == "Abriendo Spotify."


def test_speech_plays_sentence_by_sentence_and_stops():
    spoken, played = [], []

    def handler(request):
        text = json.loads(request.content)["text"] if request.content else ""
        spoken.append(text)
        return httpx.Response(200, content=b"RIFF" + text.encode())

    c = _client(handler)
    c.voice = "gemini:Algieba"
    a = Assistant(c, ui=UI(), player=played.append, chime=lambda f: None)
    a.say_aloud("Primera frase corta pero suficiente. " + "Segunda parte larga. " * 20)
    assert len(played) >= 2 and played[0].startswith(b"RIFFPrimera")


def test_actions_report_what_is_in_front(desktop):
    desktop.active_window = lambda: "Spotify Premium"
    c = Controller(desktop, sleep=lambda s: None, approve=lambda _: True)
    assert c.act({"action": "open_app", "target": "Spotify"}).endswith(
        "| now in front: Spotify Premium"
    )
    assert "now in front" not in c.act({"action": "wait", "seconds": 1})


def test_face_watcher_names_faces_and_greets_once(monkeypatch):
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    pytest.importorskip("PySide6")
    from sergio_escritorio.camera import FaceWatcher

    clock = [100.0]
    greeted = []
    frame = np.zeros((720, 1280, 3), np.uint8)
    w = FaceWatcher(
        lambda: frame,
        lambda jpeg: [{"name": "Dani", "score": 0.93, "box": [64, 32, 128, 160]}],
        on_person=greeted.append,
        clock=lambda: clock[0],
    )
    faces = w.check(frame)
    assert faces[0]["name"] == "Dani"
    assert faces[0]["box"] == (128.0, 64.0, 256.0, 320.0)  # back to frame pixels
    assert faces[0]["nbox"] == (0.1, 64 / 720, 0.2, 320 / 720)
    assert greeted == []  # one look could be a lucky guess
    clock[0] += 1.5
    w.check(frame)
    assert greeted == ["Dani"]
    for _ in range(5):  # still here: not greeted on every check
        clock[0] += 1.5
        w.check(frame)
    assert greeted == ["Dani"]
    clock[0] += 601
    w.check(frame)
    assert greeted == ["Dani"]  # back after a while: one look is not enough
    clock[0] += 1.5
    w.check(frame)
    assert greeted == ["Dani", "Dani"]  # second look: greeted again
    clock[0] += 10
    assert w.fresh() == []  # old results are not drawn


@pytest.mark.parametrize(
    ("said", "kind", "arg"),
    [
        ("Sergio, ¿me puedes abrir el Word, por favor?", "open_app", "word"),
        ("quiero que abras spotify", "open_app", "spotify"),
        ("Necesito que me abras la calculadora", "open_app", "calculadora"),
        ("abre la aplicación de configuración", "open_app", "configuracion"),
        ("abre steam porfa", "open_app", "steam"),
        ("cierra el bloc de notas, porfa", "close_app", "bloc de notas"),
        ("puedes abrir youtube", "open_url", "https://www.youtube.com"),
        ("abre whatsapp", "open_app", "whatsapp"),  # the app if installed
        ("oye sergio sube el volumen", "volume", "up"),
        ("muéstrame Madrid en el globo", "globe_goto", "madrid"),
    ],
)
def test_orders_said_politely_are_still_instant(said, kind, arg):
    q = parse_quick(said)
    assert q is not None and (q.kind, q.arg) == (kind, arg)

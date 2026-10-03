"""Clicky features: brain choice, hold Ctrl+Alt to talk, screen-aware turns."""

import httpx
import pytest
from sergio_escritorio import launch
from sergio_escritorio.hold import HoldDetector, key_name
from sergio_escritorio.listen import FRAME, parse_wake, set_wake_name
from sergio_escritorio.voice import (
    Assistant,
    Ears,
    SergioClient,
    choose_brain,
    to_wav,
    wav_seconds,
)

F, D = "gemini-3.8-flash", "gemini-3.1-pro-preview"


@pytest.mark.parametrize(
    ("text", "effort", "brain"),
    [
        ("qué hora es", "auto", f"{F}@low"),
        (
            "cuéntame un chiste sobre programadores y gatos por favor",
            "auto",
            f"{F}@low",
        ),
        (
            "qué clima hace hoy en Quito y mañana en Guayaquil por la tarde",
            "auto",
            f"{F}@medium",
        ),
        ("investiga las mejores laptops del 2026", "auto", f"{D}@high"),
        ("explícame paso a paso cómo instalar Blender", "auto", f"{D}@high"),
        ("hola", "profundo", f"{D}@high"),
        ("investiga todo", "rapido", f"{F}@low"),
        ("hola", "equilibrado", f"{F}@medium"),
    ],
)
def test_choose_brain(text, effort, brain):
    assert choose_brain(text, effort, F, D) == brain


def _client(handler):
    return SergioClient(
        "http://s.test", http=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_pro_unavailable_falls_back_to_flash_high():
    seen = []

    def handler(request):
        if request.url.path == "/v1/info":
            return httpx.Response(200, json={"model": F})
        body = __import__("json").loads(request.content)
        seen.append(body["model"])
        if body["model"].startswith(D):
            return httpx.Response(429, json={"detail": "quota"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = _client(handler)
    assert client.ask("investiga los mejores celulares") == "ok"
    assert seen == [f"{D}@high", f"{F}@high"] and client.last_brain == f"{F}@high"


def test_local_model_gets_no_effort_suffix():
    def handler(request):
        if request.url.path == "/v1/info":
            return httpx.Response(200, json={"model": "qwen3:8b"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = _client(handler)
    assert client.brain("investiga algo") == "qwen3:8b"


def test_personality_goes_into_the_system_prompt():
    sent = []

    def handler(request):
        if request.url.path == "/v1/info":
            return httpx.Response(200, json={"model": F})
        sent.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = _client(handler)
    client.personality = "Tu nombre es Jolly. Usa humor ligero."
    client.ask("hola")
    assert sent[0]["messages"][0]["content"].endswith(
        "Tu nombre es Jolly. Usa humor ligero."
    )


# -- hold Ctrl+Alt ----------------------------------------------------------------
class Key:
    def __init__(self, name):
        self.name = name


class FakeTimer:
    made = []

    def __init__(self, delay, fn):
        self.fn, self.cancelled = fn, False
        FakeTimer.made.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


def _detector():
    events = []
    FakeTimer.made = []
    d = HoldDetector(
        lambda: events.append("start"),
        lambda: events.append("end"),
        lambda: events.append("cancel"),
        timer=FakeTimer,
    )
    return d, events


def test_hold_ctrl_alt_starts_and_release_sends():
    d, events = _detector()
    d.press(Key("ctrl_l"))
    d.press(Key("alt_l"))
    FakeTimer.made[-1].fn()  # held long enough
    d.release(Key("alt_l"))
    assert events == ["start", "end"]


def test_shortcut_with_another_key_never_starts():
    d, events = _detector()
    d.press(Key("ctrl_l"))
    d.press(Key("alt_gr"))
    d.press(Key(None))  # AltGr+2 -> "@"
    assert FakeTimer.made[-1].cancelled
    d.release(Key("alt_gr"))
    d.release(Key("ctrl_l"))
    assert events == []


def test_other_key_during_hold_cancels():
    d, events = _detector()
    d.press(Key("ctrl_r"))
    d.press(Key("alt_r"))
    FakeTimer.made[-1].fn()
    d.press(Key(None))  # Ctrl+Alt+C after all
    d.release(Key("alt_r"))
    assert events == ["start", "cancel"]


def test_key_names():
    assert [key_name(Key(n)) for n in ("ctrl", "ctrl_l", "alt_gr", "space")] == [
        "ctrl",
        "ctrl",
        "alt",
        "other",
    ]


# -- ears + assistant in Clicky mode ------------------------------------------------
class UI:
    def __init__(self):
        self.states, self.captions = [], []

    def state(self, name):
        self.states.append(name)

    def say(self, text):
        self.captions.append(text)


def test_ears_hold_records_until_release():
    a = Assistant(_client(lambda r: httpx.Response(404)), ui=UI(), chime=lambda f: None)
    ears = Ears(a, wake_word=False)
    frame = b"\x10\x00" * FRAME
    ears.hold_start()
    assert all(ears.feed(frame) is None for _ in range(20))
    ears.hold_end()
    wav, addressed, clicky = ears.feed(frame)
    assert (
        addressed and clicky and wav_seconds(wav) == pytest.approx(20 * FRAME / 16000)
    )
    # a quick tap is not speech
    ears.hold_start()
    ears.feed(frame)
    ears.hold_end()
    assert ears.feed(frame) is None
    # Ctrl+Alt+C: dropped
    ears.hold_start()
    ears.feed(frame)
    ears.hold_cancel()
    assert ears.feed(frame) is None and a.ui.states[-1] == "idle"


def test_clicky_turn_always_looks_at_the_screen_but_orders_go_to_the_agent():
    calls = []
    heard = ["¿Cómo exporto esto en mp4?", "abre Spotify"]

    def handler(request):
        path = request.url.path
        calls.append(path)
        if path == "/v1/speech/transcribe":
            return httpx.Response(200, json={"text": heard.pop(0)})
        if path == "/v1/vision/screen":
            return httpx.Response(
                200, json={"answer": "Archivo, Exportar.", "element": None}
            )
        if path == "/v1/info":
            return httpx.Response(200, json={"model": F})
        if path == "/v1/chat/completions":
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "Listo."}}]}
            )
        return httpx.Response(200, content=b"RIFF")

    a = Assistant(
        _client(handler),
        ui=UI(),
        player=lambda _w: None,
        chime=lambda f: None,
        screen=lambda: (b"\x89PNG", [], 1.0),
    )
    wav = to_wav([b"\x00\x00" * 1600])
    a.on_utterance(wav, addressed=True, clicky=True)
    assert "/v1/vision/screen" in calls and "/v1/chat/completions" not in calls
    calls.clear()
    a.on_utterance(wav, addressed=True, clicky=True)
    assert "/v1/chat/completions" in calls and "/v1/vision/screen" not in calls


def test_talking_again_interrupts_the_answer():
    stopped = []

    class Player:
        def __call__(self, _wav):
            pass

        def stop(self):
            stopped.append(1)

    a = Assistant(_client(lambda r: httpx.Response(404)), ui=UI(), player=Player())
    a.busy = True
    Ears(a, wake_word=False).talk()
    assert stopped == [1]


def test_custom_name_wakes_him_too():
    set_wake_name("Jolly")
    try:
        assert parse_wake("Jolly, ¿qué hora es?") == (True, "qué hora es")
        assert parse_wake("Sergio, hola")[0]
    finally:
        set_wake_name("Sergio")
    assert not parse_wake("Jolly, hola")[0]


def test_globe_urls_open_as_app_windows():
    assert launch.is_app_page("http://127.0.0.1:4173/#lat=1")
    assert launch.is_app_page("http://localhost:4173/")
    assert not launch.is_app_page("https://www.google.com/search?q=nvidia")
    assert not launch.is_app_page("http://localhost:8000/globe")


def test_diag_endpoint(control_server):
    controller, url = control_server
    controller.diag = lambda: {"microphone": "Micrófono (Realtek)", "peak_level": 320}
    resp = httpx.get(f"{url}/diag", headers={"Authorization": "Bearer secreto"})
    assert resp.json() == {
        "ok": True,
        "microphone": "Micrófono (Realtek)",
        "peak_level": 320,
    }

"""Tools Sergio uses during a live call, and how a call takes over the mic."""

from datetime import datetime

import httpx
from sergio_escritorio.call_tools import Abilities, call_context, call_tools
from sergio_escritorio.jarvis import Reminder
from sergio_escritorio.listen import FRAME
from sergio_escritorio.voice import Assistant, Ears, SergioClient, to_wav, wav_pcm

NOW = datetime(2026, 10, 4, 15, 20)


def _tools(**kw):
    acts = []
    kw.setdefault("act", lambda a: acts.append(a) or "ok")
    tools = {t.name: t for t in call_tools(Abilities(now=lambda: NOW, **kw))}
    return tools, acts


def test_every_tool_has_a_gemini_safe_declaration():
    tools, _ = _tools()
    assert {"colgar", "abrir", "cerrar", "camara", "hologramas", "recordatorio",
            "estado_sistema", "tarea", "gimnasio_mental", "senalar"} <= set(tools)
    for tool in tools.values():
        decl = tool.declaration()
        assert decl["parameters"]["type"] == "object"
        for prop in decl["parameters"]["properties"].values():
            assert "required" not in prop  # moved to the object level


def test_open_sites_and_apps_and_close():
    tools, acts = _tools()
    tools["abrir"].run({"objetivo": "youtube"})
    tools["abrir"].run({"objetivo": "Spotify"})
    tools["cerrar"].run({"app": "Spotify"})
    tools["buscar_en_navegador"].run({"consulta": "nvidia rtx", "sitio": "youtube"})
    assert acts == [
        {"action": "open", "target": "https://www.youtube.com"},
        {"action": "open_app", "target": "Spotify"},
        {"action": "close_app", "target": "Spotify"},
        {"action": "open", "target": "https://www.youtube.com/results?search_query=nvidia+rtx"},
    ]


def test_volume_and_media_keys():
    tools, acts = _tools()
    tools["volumen"].run({"accion": "subir", "pasos": 3})
    tools["multimedia"].run({"accion": "siguiente"})
    assert [a["keys"] for a in acts] == ["volumeup"] * 3 + ["nexttrack"]


def test_reminders_by_minutes_or_time():
    saved = []
    tools, _ = _tools(remind=lambda due, text: saved.append((due, text)) or "ok")
    said = tools["recordatorio"].run({"minutos": 10, "texto": "sacar la ropa"})
    assert said == "Le avisaré en 10 minutos: sacar la ropa."
    said = tools["recordatorio"].run({"hora": "19:30", "texto": "llamar"})
    assert "a las 7 y 30" in said
    assert datetime.fromtimestamp(saved[1][0]).hour == 19
    assert "minutos" in tools["recordatorio"].run({})


def test_status_and_pending():
    tools, _ = _tools(
        status=lambda: {"battery": 81, "charging": True, "cpu": 12},
        reminders=lambda: [Reminder("a", datetime(2026, 10, 4, 15, 30).timestamp(), "pan")],
    )
    assert "batería al 81%" in tools["estado_sistema"].run({})
    assert tools["recordatorios_pendientes"].run({}) == "pan en 10 minutos"


def test_point_at_something_on_screen():
    pointed = []
    tools, _ = _tools(
        snapshot=lambda: (b"png", [{"id": 1, "x": 100, "y": 50, "name": "Exportar"}], 2.0),
        screen_help=lambda png, q, els: {"answer": "Aquí.", "element": 1, "label": "Exportar"},
        point=lambda x, y, label: pointed.append((x, y, label)),
    )
    assert tools["senalar"].run({"que": "Exportar"}).startswith("Lo señalé")
    assert pointed and pointed[0][2] == "Exportar"


def test_context_for_the_call():
    text = call_context(NOW, {"battery": 50}, [], camera_on=True, owner="Dani")
    assert "domingo 4 de octubre" in text and "Hablas con Dani" in text
    assert "La cámara está abierta" in text


class UI:
    def __init__(self):
        self.states, self.captions = [], []

    def state(self, name):
        self.states.append(name)

    def say(self, text):
        self.captions.append(text)


def test_saying_sergio_opens_a_call_with_that_sentence():
    def handler(request):
        if request.url.path == "/v1/speech/transcribe":
            return httpx.Response(200, json={"text": "Sergio, abre Spotify"})
        return httpx.Response(404)

    client = SergioClient("http://s.test", http=httpx.Client(transport=httpx.MockTransport(handler)))
    a = Assistant(client, ui=UI(), chime=lambda f: None, player=lambda w: None)
    started = []
    a.start_call = lambda wav: started.append(wav) or True
    wav = to_wav([b"\x01\x00" * 1600])
    a.on_utterance(wav, addressed=False)
    assert started == [wav]
    assert wav_pcm(wav) == b"\x01\x00" * 1600


def test_during_a_call_the_microphone_goes_to_it():
    class Call:
        active = True

        def __init__(self):
            self.frames = []

        def feed_mic(self, chunk):
            self.frames.append(chunk)

    a = Assistant(SergioClient("http://s.test"), ui=UI(), chime=lambda f: None)
    ears = Ears(a, wake_word=True)
    ears.call = Call()
    frame = b"\x20\x00" * FRAME
    for _ in range(5):
        assert ears.feed(frame) is None
    assert len(ears.call.frames) == 5
    handled = []
    ears.on_talk = lambda: handled.append(1) or True
    ears.talk()
    assert handled == [1] and not ears.push_to_talk

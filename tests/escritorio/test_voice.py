"""Voice turns: wake word, follow-up, push-to-talk, never hearing itself."""

import io
import json
import wave

import httpx
import numpy as np
from sergio_escritorio.listen import FRAME
from sergio_escritorio.voice import VOICE_STYLE, Assistant, Ears, SergioClient, to_wav

WAV = to_wav([b"\x00\x00" * 1600])


class UI:
    def __init__(self):
        self.states, self.captions = [], []

    def state(self, name):
        self.states.append(name)

    def say(self, text):
        self.captions.append(text)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def _server(heard, log):
    def handler(request):
        path = request.url.path
        if path == "/v1/speech/transcribe":
            assert b"RIFF" in request.content and b"es" in request.content
            return httpx.Response(200, json={"text": heard.pop(0)})
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "qwen3:8b"}]})
        if path == "/v1/chat/completions":
            body = json.loads(request.content)
            log.append(body["messages"])
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Listo, abrí Spotify."}}]},
            )
        if path == "/v1/speech/synthesize":
            return httpx.Response(200, content=b"RIFFvoz")
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _assistant(heard):
    log, played, chimes = [], [], []
    ui, clock = UI(), Clock()
    client = SergioClient("http://sergio.test", http=_server(list(heard), log))
    a = Assistant(client, ui=ui, player=played.append, chime=chimes.append, clock=clock)
    return a, ui, log, played, clock


def test_wake_word_turn_answers_aloud():
    a, ui, log, played, _ = _assistant(["Sergio, abre Spotify."])
    a.on_utterance(WAV, addressed=False)
    assert played == [b"RIFFvoz"]
    assert ui.captions == ["«abre Spotify»", "Listo, abrí Spotify."]
    # after answering he keeps listening for your reply (a conversation)
    assert ui.states[-3:] == ["thinking", "speaking", "listening"]
    sent = log[0]
    assert sent[0] == {"role": "system", "content": VOICE_STYLE}
    assert sent[-1] == {"role": "user", "content": "abre Spotify"}


def test_room_conversation_is_ignored_with_an_occasional_hint():
    a, ui, log, played, clock = _assistant(
        ["mañana vamos al cine con Sergio", "busca en la web el clima", "hola"]
    )
    a.on_utterance(WAV, addressed=False)
    assert log == [] and played == []
    assert "thinking" not in ui.states  # the orb does not flicker for chatter
    assert ui.captions[0].startswith("Oí «mañana vamos al cine con Sergio»")
    assert "Ctrl+Espacio" in ui.captions[0]
    a.on_utterance(WAV, addressed=False)  # within two minutes: no new hint
    assert len(ui.captions) == 1
    clock.now += 121
    a.on_utterance(WAV, addressed=False)  # one word: not an order, no hint
    assert len(ui.captions) == 1


def test_bare_name_then_command_within_follow_up_window():
    a, ui, log, played, clock = _assistant(["Sergio", "pon música tranquila"])
    a.on_utterance(WAV, addressed=False)
    assert ui.captions == ["¿Sí?"] and a.expecting and ui.states[-1] == "listening"
    clock.now += 3
    a.on_utterance(WAV, addressed=False)
    assert log[-1][-1]["content"] == "pon música tranquila" and played


def test_follow_up_window_expires():
    a, ui, log, _, clock = _assistant(["Sergio", "pon música"])
    a.on_utterance(WAV, addressed=False)
    clock.now += 9
    a.on_utterance(WAV, addressed=False)
    assert log == []


def test_push_to_talk_needs_no_wake_word_and_history_is_kept():
    a, _, log, _, _ = _assistant(["¿qué hora es?", "y mañana?"])
    a.on_utterance(WAV, addressed=True)
    a.on_utterance(WAV, addressed=True)
    assert [m["content"] for m in log[-1][1:]] == [
        "¿qué hora es?",
        "Listo, abrí Spotify.",
        "y mañana?",
    ]


def test_errors_are_spoken_not_raised():
    ui = UI()
    broken = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    a = Assistant(
        SergioClient("http://x", http=broken),
        ui=ui,
        player=lambda b: None,
        chime=lambda f: None,
    )
    a.on_utterance(WAV, addressed=True)
    assert ui.captions[-1].startswith("No pude entender el audio") and a.busy is False


def test_each_failing_step_is_named_and_voice_failure_keeps_the_text():
    def handler(request):
        path = request.url.path
        if path == "/v1/speech/transcribe":
            return httpx.Response(200, json={"text": "hola"})
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        if path == "/v1/chat/completions":
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "Hola."}}]}
            )
        return httpx.Response(500, json={"detail": "Speech synthesis failed"})

    ui, played = UI(), []
    client = SergioClient(
        "http://x", http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    a = Assistant(client, ui=ui, player=played.append, chime=lambda f: None)
    a.on_utterance(WAV, addressed=True)
    assert ui.captions[-1] == "Hola." and played == []  # answer shown, no crash

    def no_model(request):
        if request.url.path == "/v1/speech/transcribe":
            return httpx.Response(200, json={"text": "hola"})
        return httpx.Response(500, json={"detail": "model 'qwen3:8b' not found"})

    ui = UI()
    client = SergioClient(
        "http://x", http=httpx.Client(transport=httpx.MockTransport(no_model))
    )
    Assistant(client, ui=ui, player=played.append, chime=lambda f: None).on_utterance(
        WAV, addressed=True
    )
    assert ui.captions[-1] == "El modelo no respondió: model 'qwen3:8b' not found"


def test_broken_hearing_is_reported_once_a_minute_in_wake_mode():
    ui, clock = UI(), Clock()
    broken = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(500, json={"detail": "no whisper"})
        )
    )
    a = Assistant(
        SergioClient("http://x", http=broken),
        ui=ui,
        player=lambda b: None,
        chime=lambda f: None,
        clock=clock,
    )
    for _ in range(5):
        a.on_utterance(WAV, addressed=False)
    assert ui.captions == ["No pude entender el audio: no whisper"]
    clock.now += 61
    a.on_utterance(WAV, addressed=False)
    assert len(ui.captions) == 2


def _tone(seconds, amp):
    t = np.arange(int(16000 * seconds)) / 16000
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.int16).tobytes()


def _frames(raw):
    step = FRAME * 2
    return [raw[i : i + step] for i in range(0, len(raw) - step + 1, step)]


def test_ears_push_to_talk_and_mute_while_busy():
    a, ui, _, _, clock = _assistant([])
    ears = Ears(a, wake_word=False, clock=clock)
    audio = _frames(_tone(1.0, 200) + _tone(1.0, 6000) + _tone(1.5, 100))
    # wake word off and no push-to-talk: nothing is recorded
    assert all(ears.feed(f) is None for f in audio)
    ears.talk()
    assert ui.captions[-1] == "Te escucho…" and ui.states[-1] == "listening"
    results = [r for r in (ears.feed(f) for f in audio) if r]
    assert len(results) == 1 and results[0][1] is True  # addressed
    with wave.open(io.BytesIO(results[0][0])) as w:
        assert w.getframerate() == 16000 and w.getnframes() > 16000 * 0.9
    # while Sergio talks, the microphone is ignored (no self-hearing)
    ears.wake_word = True
    a.busy = True
    assert all(ears.feed(f) is None for f in audio)


def test_push_to_talk_records_quiet_voices_and_sends_on_timeout():
    a, ui, _, _, clock = _assistant([])
    ears = Ears(a, wake_word=False, clock=clock)
    ears.talk()
    quiet = _frames(_tone(0.5, 60))  # a very quiet laptop microphone
    assert all(ears.feed(f) is None for f in quiet)
    clock.now += 11
    wav, addressed, clicky = ears.feed(quiet[0])
    assert addressed is True and clicky is False and len(wav) > 16000
    assert not ears.push_to_talk


def test_pressing_again_sends_immediately():
    a, _, _, _, clock = _assistant([])
    ears = Ears(a, wake_word=False, clock=clock)
    ears.talk()
    ears.feed(_frames(_tone(0.3, 3000))[0])
    ears.talk()  # second press = "done"
    assert ears.feed(_frames(_tone(0.1, 60))[0])[1] is True


def test_microphone_level_is_reported():
    a, _, _, _, clock = _assistant([])
    levels = []
    ears = Ears(a, wake_word=True, clock=clock, on_level=levels.append)
    for f in _frames(_tone(0.2, 50) + _tone(0.2, 4000)):
        ears.feed(f)
    assert levels[0] < 0.2 and max(levels) > 0.8


def test_wav_format():
    data = to_wav([b"\x01\x00" * 160])
    with wave.open(io.BytesIO(data)) as w:
        assert (
            w.getnchannels(),
            w.getsampwidth(),
            w.getframerate(),
            w.getnframes(),
        ) == (1, 2, 16000, 160)


def test_hearing_happens_on_windows_first_then_server(monkeypatch):
    from sergio_escritorio import voice

    class Local:
        def __init__(self, fail=False):
            self.fail = fail

        def transcribe(self, wav):
            if self.fail:
                raise RuntimeError("no model")
            return "Sergio, abre Spotify"

    server_calls = []

    def handler(request):
        server_calls.append(request.url.path)
        return httpx.Response(200, json={"text": "desde el servidor"})

    client = SergioClient(
        "http://x", http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(voice, "_LOCAL", [Local()])
    assert client.transcribe(WAV) == "Sergio, abre Spotify" and server_calls == []
    monkeypatch.setattr(voice, "_LOCAL", [Local(fail=True)])
    assert client.transcribe(WAV) == "desde el servidor"
    assert server_calls == ["/v1/speech/transcribe"]


def _look_assistant(heard, look_status=200):
    log, played, seen, shots = [], [], [], []
    base = _server(list(heard), log)

    def handler(request):
        if request.url.path == "/v1/faces/look":
            assert b"image/jpeg" in request.content
            if look_status != 200:
                return httpx.Response(look_status, json={"detail": "sin visión"})
            return httpx.Response(200, json={"answer": "Tienes una taza azul."})
        return base.send(request)

    client = SergioClient(
        "http://sergio.test", http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    ui = UI()

    def eyes():
        shots.append(1)
        return b"\xff\xd8jpeg"

    a = Assistant(
        client,
        ui=ui,
        player=played.append,
        chime=lambda f: None,
        eyes=eyes,
        on_seen=seen.append,
    )
    return a, ui, log, played, shots, seen


def test_camera_question_goes_straight_to_the_eyes():
    a, ui, log, played, shots, seen = _look_assistant(
        ["Sergio, ¿qué tengo en la mano?"]
    )
    a.on_utterance(WAV, addressed=False)
    assert shots == [1] and seen == ["Tienes una taza azul."]
    assert log == []  # the agent was not needed
    assert ui.captions[-1] == "Tienes una taza azul." and played == [b"RIFFvoz"]
    assert a.client.history[-1]["content"].endswith("Tienes una taza azul.")


def test_camera_failure_falls_back_to_the_agent():
    a, ui, log, played, shots, _ = _look_assistant(
        ["Sergio, ¿qué ves?"], look_status=502
    )
    a.on_utterance(WAV, addressed=False)
    assert shots == [1] and len(log) == 1
    assert any("No pude ver bien" in c for c in ui.captions)
    assert ui.captions[-1] == "Listo, abrí Spotify."


def test_normal_orders_do_not_use_the_camera():
    a, ui, log, played, shots, _ = _look_assistant(["Sergio, abre Spotify."])
    a.on_utterance(WAV, addressed=False)
    assert shots == [] and len(log) == 1


def test_spent_gemini_voice_is_skipped_for_a_while(monkeypatch):
    """Free keys get a few Gemini voice requests a day: once spent, every
    sentence went through failing models first. Now the backup voice speaks
    at once, and `sergio probar` says which voice spoke."""
    from sergio_escritorio import neural_voice

    asked = []

    def handler(request):
        asked.append(request.url.path)
        return httpx.Response(502, json={"detail": "429 RESOURCE_EXHAUSTED quota"})

    client = SergioClient("http://s", http=httpx.Client(transport=httpx.MockTransport(handler)))
    client.voice = "gemini:Algieba"
    monkeypatch.setattr(neural_voice, "synthesize", lambda text, voice, rate: b"EDGE")
    assert client._speak("Hola.") == b"EDGE"
    assert client._speak("Otra frase.") == b"EDGE"
    assert asked == ["/v1/voice/speak"]  # asked once, then skipped
    assert client.last_voice.startswith("respaldo Edge")


def test_a_failed_turn_does_not_stay_in_the_history():
    def handler(request):
        if request.url.path == "/v1/voice/chat":
            return httpx.Response(502, json={"detail": "fast chat down"})
        if request.url.path == "/v1/info":
            return httpx.Response(200, json={"model": "gemini-3.8-flash"})
        return httpx.Response(500, json={"detail": "boom"})

    client = SergioClient("http://s", http=httpx.Client(transport=httpx.MockTransport(handler)))
    import pytest as _pytest

    with _pytest.raises(httpx.HTTPStatusError):
        client.ask("abre el correo y resume lo nuevo")
    assert client.history == []


def test_a_typed_order_while_busy_waits_its_turn():
    import threading
    import time as _time

    done = []

    class UI:
        def state(self, name):
            pass

        def say(self, text):
            done.append(text)

    a = Assistant(SergioClient("http://s"), ui=UI(), player=lambda wav: None, chime=lambda f: None)
    a.quick = lambda q: "Hecho."
    a.say_aloud = lambda text: done.append(f"dijo {text}")
    a.busy = True
    t = threading.Thread(target=a.on_text, args=("sube el volumen",))
    t.start()
    _time.sleep(0.2)
    assert "dijo Hecho." not in done
    a.busy = False
    t.join(2)
    assert "dijo Hecho." in done

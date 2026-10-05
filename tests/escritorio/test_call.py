"""Calls with Sergio (Gemini Live): the Windows side, with a fake line."""

import json
import queue
import threading
import time

import numpy as np
import pytest
from sergio_escritorio.call import (
    FRAME_BYTES,
    SEND_BYTES,
    CallSession,
    ClientTool,
    EchoCanceller,
    Speaker,
    resample,
    rms,
    ws_url,
)


class FakeLine:
    """The websocket to Sergio's server: scripted answers, recorded sends."""

    def __init__(self, script=()):
        self.inbox = queue.Queue()
        for msg in script:
            self.inbox.put(msg)
        self.sent = []
        self.closed = False

    def __call__(self, url, **kw):
        self.url = url
        return self

    def send(self, data):
        self.sent.append(data)

    def recv(self, timeout=None):
        try:
            return self.inbox.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError from None

    def close(self):
        self.closed = True

    def json_sent(self):
        return [json.loads(m) for m in self.sent if isinstance(m, str)]

    def audio_sent(self):
        return b"".join(m for m in self.sent if isinstance(m, bytes))


class SilentStream:
    def __init__(self, callback):
        self.callback = callback

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


def _call(line, **kw):
    kw.setdefault("speaker", Speaker(stream_factory=SilentStream))
    kw.setdefault("echo", EchoCanceller(factory=lambda: lambda mic, ref: mic))
    return CallSession("http://localhost:8000", connect=line, **kw)


def _wait(cond, seconds=3.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_ws_url():
    assert ws_url("http://localhost:8000/") == "ws://localhost:8000/v1/live"
    assert ws_url("https://sergio.example") == "wss://sergio.example/v1/live"


def test_resample_and_rms():
    tone = (np.sin(np.arange(2400) / 5) * 8000).astype(np.int16).tobytes()
    out = resample(tone, 24000, 16000)
    assert len(out) == 1600 * 2
    assert rms(out) == pytest.approx(rms(tone), rel=0.05)


def test_start_sends_who_he_is_and_waits_for_ready():
    line = FakeLine([json.dumps({"type": "ready", "model": "gemini-3.8-live"})])
    tool = ClientTool("colgar", "Termina la llamada.", lambda a: "ok")
    call = _call(
        line,
        voice="gemini:Charon",
        personality="Humor seco.",
        context=lambda: "Son las 15:20.",
        tools=[tool],
    )
    assert call.start(prefill=b"\1\0" * 4000)
    try:
        start = line.json_sent()[0]
        assert start["type"] == "start" and start["voice"] == "Charon"
        assert start["context"] == "Son las 15:20." and start["personality"] == "Humor seco."
        assert start["tools"][0]["name"] == "colgar"
        assert line.url == "ws://localhost:8000/v1/live"
        assert call.model == "gemini-3.8-live" and call.active
        # the sentence that woke him goes first, in 100 ms pieces
        assert line.audio_sent() == b"\1\0" * 4000
        assert all(len(m) <= SEND_BYTES for m in line.sent if isinstance(m, bytes))
    finally:
        call.hang_up()
    assert line.json_sent()[-1] == {"type": "end"} and line.closed


def test_no_live_model_means_no_call():
    line = FakeLine([json.dumps({"type": "error", "message": "sin cuota"})])
    call = _call(line)
    assert not call.start()
    assert "sin cuota" in call.error and line.closed and not call.active


def test_edge_voices_and_the_default_use_gemini_lives_own_voice():
    assert _call(FakeLine(), voice="es-ES-AlvaroNeural").voice == ""
    assert _call(FakeLine(), voice="gemini:Predeterminada").voice == ""
    assert _call(FakeLine(), voice="gemini:Charon").voice == "Charon"


def test_microphone_goes_through_the_echo_canceller_in_10ms_frames():
    seen = []

    def canceller(mic, ref):
        seen.append((len(mic), len(ref)))
        return mic

    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    call = _call(line, echo=EchoCanceller(factory=lambda: canceller))
    assert call.start()
    try:
        voice = (np.random.default_rng(1).normal(0, 3000, 512 * 7)).astype(np.int16)
        for i in range(7):
            call.feed_mic(voice[i * 512 : (i + 1) * 512].tobytes())
        assert seen and all(s == (FRAME_BYTES, FRAME_BYTES) for s in seen)
        # 7 x 32 ms = 224 ms: two 100 ms messages sent, the rest waits
        assert len(line.audio_sent()) == 2 * SEND_BYTES
    finally:
        call.hang_up()


def test_while_he_talks_his_own_echo_is_not_sent():
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    speaker = Speaker(stream_factory=SilentStream)
    call = _call(line, speaker=speaker)
    assert call.start()
    try:
        speaker.play(b"\x10\x10" * 24000)  # he is talking
        faint = (np.ones(1600) * 120).astype(np.int16).tobytes()  # leftover echo
        call.feed_mic(faint)
        assert set(line.audio_sent()) == {0}
        loud = (np.random.default_rng(2).normal(0, 4000, 1600)).astype(np.int16)
        call.feed_mic(loud.tobytes())  # you talk over him: it goes through
        assert rms(line.audio_sent()[-SEND_BYTES:]) > 1000
    finally:
        call.hang_up()


def test_his_voice_captions_interruptions_and_tools():
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    speaker = Speaker(stream_factory=SilentStream)
    states, captions, heard = [], [], []
    opened = []
    tool = ClientTool(
        "camara",
        "Abre la cámara.",
        lambda args: opened.append(args) or "Cámara abierta.",
    )
    call = _call(
        line,
        speaker=speaker,
        tools=[tool],
        on_state=states.append,
        on_caption=captions.append,
        on_heard=heard.append,
    )
    assert call.start()
    try:
        line.inbox.put(json.dumps({"type": "heard", "text": "Sergio, abre"}))
        line.inbox.put(json.dumps({"type": "heard", "text": " la cámara"}))
        line.inbox.put(json.dumps({"type": "call", "id": "c1", "name": "camara", "args": {"accion": "abrir"}}))
        line.inbox.put(b"\x20\x00" * 2400)
        line.inbox.put(json.dumps({"type": "said", "text": "Aquí "}))
        line.inbox.put(json.dumps({"type": "said", "text": "la tiene."}))
        assert _wait(lambda: any(m.get("type") == "tool_result" for m in line.json_sent()))
        result = next(m for m in line.json_sent() if m.get("type") == "tool_result")
        assert result == {"type": "tool_result", "id": "c1", "result": "Cámara abierta."}
        assert opened == [{"accion": "abrir"}]
        assert _wait(lambda: captions and captions[-1] == "Aquí la tiene.")
        assert heard[-1] == "Sergio, abre la cámara"
        assert "speaking" in states and "acting" in states
        assert speaker.talking
        line.inbox.put(json.dumps({"type": "interrupted"}))
        assert _wait(lambda: not speaker._buf)  # you talked: he stops at once
    finally:
        call.hang_up()
    assert states[-1] == "idle"


def test_unknown_or_failing_tools_answer_the_model():
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])

    def broken(_args):
        raise PermissionError

    call = _call(line, tools=[ClientTool("abrir", "Abre.", broken)])
    assert call.start()
    try:
        line.inbox.put(json.dumps({"type": "call", "id": "a", "name": "abrir", "args": {}}))
        line.inbox.put(json.dumps({"type": "call", "id": "b", "name": "volar", "args": {}}))
        assert _wait(lambda: len([m for m in line.json_sent() if m.get("type") == "tool_result"]) == 2)
        results = {m["id"]: m["result"] for m in line.json_sent() if m.get("type") == "tool_result"}
        assert "pausa" in results["a"] and "No conozco volar" in results["b"]
    finally:
        call.hang_up()


def test_silence_ends_the_call():
    now = [100.0]
    ended = []
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    call = _call(line, clock=lambda: now[0], idle_hang_up=30, on_end=ended.append)
    assert call.start()
    now[0] += 31
    assert _wait(lambda: not call.active)
    assert ended == ["silencio"]


def test_goodbye_hangs_up_after_his_last_words():
    ended = []
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    speaker = Speaker(stream_factory=SilentStream)
    call = _call(line, speaker=speaker, on_end=ended.append)
    assert call.start()
    speaker.play(b"\x30\x30" * 4800)  # "Ha sido un placer, señor."
    call.hang_up_after_goodbye()
    time.sleep(0.3)
    assert call.active  # still saying goodbye
    speaker.flush()
    speaker.last_sound = 0
    assert _wait(lambda: not call.active, 4)
    assert ended == ["te despediste"]


def test_shares_camera_frames_while_on():
    line = FakeLine([json.dumps({"type": "ready", "model": "m"})])
    call = _call(line, video=lambda: (b"jpeg!", "cámara"))
    assert call.start()
    try:
        assert _wait(lambda: any(m.get("type") == "image" for m in line.json_sent()))
        image = next(m for m in line.json_sent() if m.get("type") == "image")
        assert image["source"] == "cámara"
    finally:
        call.hang_up()


def test_lost_connection_ends_the_call():
    class Broken(FakeLine):
        def recv(self, timeout=None):
            if self.inbox.empty() and self.sent:
                raise ConnectionError("cortado")
            return super().recv(timeout)

    ended = []
    line = Broken([json.dumps({"type": "ready", "model": "m"})])
    call = _call(line, on_end=ended.append)
    assert call.start()
    assert _wait(lambda: not call.active)
    assert ended == ["se cortó"]


def test_speaker_waits_for_a_little_voice_before_starting():
    import time as _time

    import numpy as np
    from sergio_escritorio.call import PREBUFFER, Speaker

    spk = Speaker(stream_factory=lambda cb: type("S", (), {"start": lambda self: None})())
    out = bytearray(960)  # what sounddevice hands the callback
    tone = (np.ones(240) * 3000).astype(np.int16).tobytes()  # 10 ms
    spk.play(tone)
    spk._callback(out, 480, None, None)
    assert not any(out)  # only 10 ms ready and more is coming: wait
    for _ in range(PREBUFFER // len(tone)):
        spk.play(tone)
    spk._callback(out, 480, None, None)
    assert all(np.frombuffer(bytes(out), np.int16))  # 150 ms ready: he speaks
    spk.flush()
    spk.play(tone)
    spk._last_push = _time.monotonic() - 1  # the sentence ended: play the tail
    out[:] = bytes(960)
    spk._callback(out, 480, None, None)
    assert all(np.frombuffer(bytes(out), np.int16)[:240])

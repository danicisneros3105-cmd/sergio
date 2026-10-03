"""Push-to-talk turn: transcribe -> ask Sergio (agent) -> speak the answer."""

import io
import json
import wave

import httpx
from sergio_escritorio.voice import SergioClient, VoiceChat, to_wav


def _server(log):
    def handler(request):
        path = request.url.path
        log.append(path)
        if path == "/v1/speech/transcribe":
            assert b"RIFF" in request.content
            return httpx.Response(200, json={"text": " abre Spotify "})
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "qwen3:8b"}]})
        if path == "/v1/chat/completions":
            body = json.loads(request.content)
            assert body["model"] == "qwen3:8b" and body["stream"] is False
            log.append(body["messages"])
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Listo, abrí Spotify."}}]},
            )
        if path == "/v1/speech/synthesize":
            assert json.loads(request.content)["text"] == "Listo, abrí Spotify."
            return httpx.Response(200, content=b"RIFFvoz")
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_full_voice_turn_and_history():
    log, played, notes, states = [], [], [], []
    client = SergioClient("http://sergio.test", http=_server(log))
    chat = VoiceChat(
        client, notify=notes.append, on_state=states.append, player=played.append
    )
    chat.process(to_wav([b"\x00\x00" * 1600]))
    assert played == [b"RIFFvoz"]
    assert notes == ["Tú: abre Spotify", "Sergio: Listo, abrí Spotify."]
    assert states == ["thinking", "speaking", "idle"]
    assert client.history[-2:] == [
        {"role": "user", "content": "abre Spotify"},
        {"role": "assistant", "content": "Listo, abrí Spotify."},
    ]
    chat.process(to_wav([b"\x00\x00"]))
    sent = [entry for entry in log if isinstance(entry, list)][-1]
    assert len(sent) == 3  # previous turn is remembered


def test_failures_are_told_not_raised():
    notes = []
    broken = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    chat = VoiceChat(
        SergioClient("http://x", http=broken),
        notify=notes.append,
        player=lambda _b: None,
    )
    chat.process(b"")
    assert notes and notes[0].startswith("No pude responder")
    assert chat.busy is False


def test_wav_format():
    data = to_wav([b"\x01\x00" * 160])
    with wave.open(io.BytesIO(data)) as w:
        assert (
            w.getnchannels(),
            w.getsampwidth(),
            w.getframerate(),
            w.getnframes(),
        ) == (1, 2, 16000, 160)

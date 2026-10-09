"""Meeting minutes: recording, who spoke when, the trip to the server."""

from __future__ import annotations

import math
import wave

import pytest

np = pytest.importorskip("numpy")

from sergio_escritorio import meeting  # noqa: E402
from sergio_escritorio.speakers import Voice  # noqa: E402

RATE = 16000


def _tone(freq, seconds, amp=0.3):
    t = np.arange(int(RATE * seconds)) / RATE
    return (amp * np.sin(2 * math.pi * freq * t)).astype(np.float32)


def _silence(seconds):
    return np.zeros(int(RATE * seconds), np.float32)


def test_speech_segments_find_the_talking():
    audio = np.concatenate(
        [
            _silence(1),
            _tone(200, 2),
            _silence(1),
            _tone(300, 1.5),
            _silence(0.3),
            _tone(300, 1),
            _silence(1),
        ]
    )
    segs = meeting.speech_segments(audio)
    assert len(segs) == 2  # the 0.3 s pause stays inside the second one
    (a1, b1), (a2, b2) = segs
    assert abs(a1 - 1.0) < 0.1 and abs(b1 - 3.0) < 0.1
    assert abs(a2 - 4.0) < 0.1 and abs(b2 - 6.8) < 0.15
    assert meeting.speech_segments(_silence(3)) == []


def _unit(v):
    v = np.asarray(v, np.float32)
    return v / np.linalg.norm(v)


VOICES = {
    200: _unit([1, 0, 0, 0]),
    300: _unit([0, 1, 0, 0]),
    450: _unit([0, 0, 1, 0]),
    600: _unit([0, 0, 0, 1]),
}


def _fake_embed(chunk):
    spectrum = np.abs(np.fft.rfft(chunk))
    freq = np.argmax(spectrum) * RATE / chunk.size
    key = min(VOICES, key=lambda f: abs(f - freq))
    return VOICES[key]


def _identify_known(names):
    def identify(print_):
        for freq, name in names.items():
            if float(print_ @ VOICES[freq]) > 0.9:
                return Voice(name, 0.9, 0.5, name == "Dani", name)
        return Voice("", 0.1, 0.0)

    return identify


def test_diarize_names_known_voices_and_numbers_the_rest():
    room = np.concatenate(
        [
            _tone(200, 3),
            _silence(1),
            _tone(450, 3),
            _silence(1),
            _tone(200, 2),
            _silence(1),
        ]
    )
    call = np.concatenate([_silence(9), _tone(600, 3), _silence(1)])
    turns = meeting.diarize(
        {"sala": room, "llamada": call}, _fake_embed, _identify_known({200: "Dani"})
    )
    said = [(t.speaker, t.track) for t in turns]
    assert said == [
        ("Dani", "sala"),
        ("Persona 1", "sala"),
        ("Dani", "sala"),
        ("Persona 2", "llamada"),
    ]
    text = meeting.timeline_text(turns)
    assert "00:00-00:03 Dani" in text and "Persona 2 (videollamada)" in text


def test_the_call_heard_through_the_speakers_is_not_a_person_in_the_room():
    voice = _tone(600, 3)
    room = np.concatenate([_silence(1), voice * 0.4, _silence(1)])  # echo of the call
    call = np.concatenate([_silence(1), voice, _silence(1)])
    turns = meeting.diarize(
        {"sala": room, "llamada": call}, _fake_embed, _identify_known({})
    )
    assert [(t.speaker, t.track) for t in turns] == [("Persona 1", "llamada")]


def test_recorder_writes_both_tracks_to_disk(tmp_path):
    taps = []

    def tap(fn):
        taps.append(fn)
        return lambda: taps.remove(fn)

    class FakeLoop:
        def __init__(self, write):
            self.write, self.ok, self.error = write, True, ""

        def start(self):
            return True

        def stop(self):
            pass

    clock = [1000.0]
    rec = meeting.MeetingRecorder(
        tap, tmp_path, loopback=FakeLoop, clock=lambda: clock[0]
    )
    folder = rec.start("reunión")
    assert rec.active and rec.start() == "Ya estoy tomando notas."
    for _ in range(50):
        taps[0](b"\x10\x00" * 512)
        rec._loop.write(b"\x20\x00" * 512)
    clock[0] += 61
    done = rec.stop()
    assert not rec.active and taps == [] and done.seconds == 61
    assert str(done.folder) == folder and done.room.exists() and done.call.exists()
    with wave.open(str(done.room)) as w:
        assert w.getframerate() == RATE and w.getnframes() == 50 * 512
    assert meeting.read_wav(done.call).size == 50 * 512
    assert rec.stop() is None


def test_a_meeting_without_call_audio_keeps_only_the_room(tmp_path):
    class NoLoop:
        def __init__(self, write):
            self.ok, self.error = False, "sin WASAPI"

        def start(self):
            return False

        def stop(self):
            pass

    rec = meeting.MeetingRecorder(lambda fn: lambda: None, tmp_path, loopback=NoLoop)
    rec.start()
    assert rec.loopback_error == "sin WASAPI"
    done = rec.stop()
    assert done.call is None and done.room.exists()


def test_to_mono_16k_and_mixing():
    stereo48 = (np.ones((4800, 2)) * 1000).astype(np.int16).tobytes()
    mono = np.frombuffer(meeting.to_mono_16k(stereo48, 48000, 2), np.int16)
    assert mono.size == 1600 and abs(int(mono.mean()) - 1000) <= 1
    mixed = meeting.mix({"sala": _tone(200, 1, 0.05), "llamada": _tone(300, 2, 0.9)})
    assert mixed.size == 2 * RATE and float(np.max(np.abs(mixed))) <= 1.0


def test_encode_writes_audio_the_server_can_read(tmp_path):
    path, mime = meeting.encode(_tone(200, 1), tmp_path)
    assert (
        path.exists()
        and mime in ("audio/ogg", "audio/wav")
        and path.stat().st_size > 1000
    )


def test_spoken_summary_is_short_and_mentions_a_task():
    data = {
        "resumen": "Se aprobó el presupuesto.\nDetalle largo.",
        "tareas": [{"quien": "Ana", "que": "enviar el informe"}, {"que": "x"}],
    }
    said = meeting.spoken_summary(data)
    assert (
        said.startswith("Se aprobó el presupuesto.")
        and "Ana, enviar el informe y 1 más" in said
    )
    assert meeting.spoken_summary({}) == "Listo, tengo las notas."


@pytest.mark.parametrize(
    ("said", "kind", "arg"),
    [
        ("Sergio, toma notas de la reunión", "meeting_start", "reunión"),
        ("graba la videollamada", "meeting_start", "videollamada"),
        ("toma notas de esta conversación", "meeting_start", "conversación"),
        ("termina la reunión", "meeting_stop", ""),
        ("resume la conversación", "meeting_stop", ""),
        ("léeme el acta", "meeting_last", ""),
    ],
)
def test_meeting_orders(said, kind, arg):
    from sergio_escritorio.quick import parse_quick

    q = parse_quick(said)
    assert q is not None and (q.kind, q.arg) == (kind, arg)

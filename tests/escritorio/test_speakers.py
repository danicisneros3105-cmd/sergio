"""Who is talking: voiceprints, live labels, voice orders (no network)."""

from __future__ import annotations

import math

import pytest

np = pytest.importorskip("numpy")

from sergio_escritorio import speakers  # noqa: E402
from sergio_escritorio.speakers import LiveVoices, VoiceBook  # noqa: E402


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def _near(v, noise, seed):
    rng = np.random.default_rng(seed)
    return _unit(np.asarray(v) + rng.normal(0, noise, len(v)))


rng = np.random.default_rng(0)
DANI = _unit(rng.normal(size=192))
ANA = _unit(rng.normal(size=192))


def test_voices_are_named_only_when_sure(tmp_path):
    book = VoiceBook(tmp_path / "voces.json")
    assert book.enroll("Daniel Cisneros", [_near(DANI, 0.04, i) for i in range(4)]) == 4
    book.enroll("Ana", [_near(ANA, 0.04, 10 + i) for i in range(3)])
    me = book.identify(_near(DANI, 0.06, 99), owner="daniel cisneros")
    assert me.name == "Daniel Cisneros" and me.owner and me.known
    her = book.identify(_near(ANA, 0.06, 98), owner="Daniel Cisneros")
    assert her.name == "Ana" and not her.owner
    stranger = book.identify(_unit(rng.normal(size=192)))
    assert stranger.name == "" and not stranger.known
    # kept on disk as numbers, read back by a new book
    again = VoiceBook(tmp_path / "voces.json")
    assert [p["name"] for p in again.people()] == ["Ana", "Daniel Cisneros"]
    assert again.forget("ana") and not again.forget("ana")


def test_a_voice_already_saved_as_someone_else_is_refused(tmp_path):
    book = VoiceBook(tmp_path / "voces.json")
    book.enroll("Dani", [_near(DANI, 0.04, i) for i in range(3)])
    with pytest.raises(ValueError, match="ya la tengo guardada como Dani"):
        book.enroll("Ana", [_near(DANI, 0.05, 50 + i) for i in range(3)])
    with pytest.raises(ValueError):
        book.enroll("", [DANI])
    with pytest.raises(ValueError):
        book.enroll("Ana", [])


def test_voiced_drops_silence():
    silence = np.zeros(16000, np.float32)
    tone = 0.3 * np.sin(np.linspace(0, 2 * math.pi * 200, 16000)).astype(np.float32)
    kept = speakers.voiced(np.concatenate([silence, tone, silence]))
    assert 14000 <= kept.size <= 16500


class FakeEncoder:
    """Loud frames of "pitch" 200 -> Dani, 400 -> Ana (no network)."""

    def embed(self, samples):
        spectrum = np.abs(np.fft.rfft(samples[:16000]))
        freq = np.argmax(spectrum) * 16000 / min(len(samples), 16000)
        return DANI if freq < 300 else ANA


def _speech(freq, seconds):
    t = np.arange(int(16000 * seconds)) / 16000
    pcm = (0.4 * 32767 * np.sin(2 * math.pi * freq * t)).astype(np.int16).tobytes()
    return [pcm[i : i + 1024] for i in range(0, len(pcm), 1024)]


def _pause(seconds=0.6):
    return [b"\0" * 1024] * int(seconds * 16000 / 512)


def test_live_voices_notice_when_the_speaker_changes(tmp_path):
    book = VoiceBook(tmp_path / "voces.json")
    book.enroll("Dani", [DANI] * 3)
    book.enroll("Ana", [ANA] * 3)
    changes = []
    clock = [0.0]
    live = LiveVoices(
        FakeEncoder,
        book,
        owner=lambda: "Dani",
        on_change=lambda new, old: changes.append((new.name, old.name if old else None)),
        clock=lambda: clock[0],
        background=False,
    )
    for frame in _speech(200, 1.6) + _pause():
        live.feed(frame)
    for frame in _speech(400, 1.6) + _pause():
        live.feed(frame)
    for frame in _speech(400, 1.5) + _pause():  # still Ana: no new note
        live.feed(frame)
    assert changes == [("Dani", None), ("Ana", "Dani")]
    assert live.describe() == "Ana" and live.describe(live.history[0][1]) == "el señor"


def test_live_voices_ignore_short_sounds_and_sergio_himself(tmp_path):
    book = VoiceBook(tmp_path / "voces.json")
    book.enroll("Dani", [DANI] * 3)
    talking = [True]
    seen = []
    live = LiveVoices(
        FakeEncoder, book, mute=lambda: talking[0], on_change=lambda n, o: seen.append(n), background=False
    )
    taps = []
    remove = live.tap(taps.append)
    for frame in _speech(200, 2.0) + _pause():
        live.feed(frame)  # Sergio was talking: not a person
    assert seen == [] and len(taps) > 50  # the tap (voice learning) still hears
    remove()
    talking[0] = False
    for frame in _speech(200, 0.5) + _pause():  # a cough: too short
        live.feed(frame)
    assert seen == []


def test_model_download_is_checked(tmp_path):
    def fake_fetch(url, dest):
        dest.write_bytes(b"not the model")

    with pytest.raises(RuntimeError, match="SHA-256"):
        speakers.ensure_model(tmp_path, fetch=fake_fetch)
    assert not (tmp_path / speakers.MODEL_NAME).exists()


@pytest.mark.parametrize(
    ("said", "kind", "arg"),
    [
        ("Sergio, aprende mi voz", "voice_enroll", ""),
        ("aprende la voz de Ana", "voice_enroll", "Ana"),
        ("memoriza mi voz, soy Daniel", "voice_enroll", "Daniel"),
        ("¿quién está hablando?", "voice_who", ""),
        ("¿reconoces mi voz?", "voice_who", ""),
        ("olvida la voz de Ana", "voice_forget", "Ana"),
    ],
)
def test_voice_orders(said, kind, arg):
    from sergio_escritorio.quick import parse_quick

    q = parse_quick(said)
    assert q is not None and (q.kind, q.arg) == (kind, arg)


def test_the_real_network_matches_its_checkpoint():
    """The ported ECAPA-TDNN loads the published weights exactly (strict)."""
    torch = pytest.importorskip("torch")
    net = speakers._build(torch)
    names = set(net.state_dict())
    assert "fbank.fb" in names and "fc6.weight" in names and "layer3.se.se.1.weight" in names
    out = net.eval()(torch.zeros(1, 16000))
    assert tuple(out.shape) == (1, 192)

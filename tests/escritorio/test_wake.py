"""Instant wake word: "Sergio" heard mid-phrase, the call connects meanwhile."""

import io
import json
import wave
import zipfile

from sergio_escritorio.listen import FRAME
from sergio_escritorio.voice import Assistant, Ears, SergioClient
from sergio_escritorio.wake import WakeSpotter, download_model, model_dir

SILENCE = b"\0\0" * FRAME


class FakeRec:
    """A Vosk recogniser that replays a script: one entry per frame.

    Entries: None (nothing new), ("partial", text) or ("final", words) where
    words are (word, start_seconds, conf).
    """

    def __init__(self, script):
        self.script = list(script)
        self.grammar = None
        self._partial = ""
        self._final = {}
        self.resets = 0

    def AcceptWaveform(self, _data):  # noqa: N802 — Vosk's API
        step = self.script.pop(0) if self.script else None
        if step and step[0] == "final":
            self._final = {
                "result": [{"word": w, "start": s, "conf": c} for w, s, c in step[1]],
                "text": " ".join(w for w, _s, _c in step[1]),
            }
            self._partial = ""
            return True
        if step and step[0] == "partial":
            self._partial = step[1]
        return False

    def PartialResult(self):  # noqa: N802
        return json.dumps({"partial": self._partial})

    def Result(self):  # noqa: N802
        return json.dumps(self._final)

    def Reset(self):  # noqa: N802
        self.resets += 1


def spotter(script, **kw):
    made = []

    def factory(grammar):
        rec = FakeRec(script)
        rec.grammar = grammar
        made.append(rec)
        return rec

    return WakeSpotter(factory, **kw), made


def run(sp, n):
    return [e for e in (sp.feed(SILENCE) for _ in range(n)) if e]


def test_grammar_only_knows_the_name_and_unknown():
    _sp, made = spotter([])
    assert "sergio" in made[0].grammar and "[unk]" in made[0].grammar


def test_maybe_from_the_partial_then_yes_when_the_phrase_ends():
    sp, _ = spotter(
        [
            None,
            ("partial", "sergio"),
            ("partial", "sergio [unk]"),
            ("final", [("sergio", 0.4, 0.98), ("[unk]", 1.0, 0.6)]),
        ]
    )
    assert run(sp, 4) == ["maybe", "yes"]


def test_name_in_the_middle_of_a_sentence_is_not_for_him():
    sp, _ = spotter(
        [
            ("partial", "[unk] [unk] sergio"),
            ("final", [("[unk]", 0.1, 1), ("[unk]", 0.8, 1), ("sergio", 1.9, 1)]),
        ]
    )
    assert run(sp, 2) == ["maybe", "no"]


def test_oye_sergio_is_fine_and_low_confidence_is_not():
    sp, _ = spotter([("final", [("oye", 0.2, 1), ("sergio", 0.6, 0.9)])])
    assert run(sp, 1) == ["yes"]
    sp, _ = spotter([("partial", "sergio"), ("final", [("sergio", 0.2, 0.2)])])
    assert run(sp, 2) == ["maybe", "no"]


def test_chatter_without_the_name_says_nothing():
    sp, _ = spotter([("partial", "[unk]"), ("final", [("[unk]", 0.1, 1)])])
    assert run(sp, 2) == []


# -- the microphone loop with the spotter ---------------------------------
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


class Call:
    def __init__(self):
        self.active = False
        self.heard = []

    def feed_mic(self, chunk):
        self.heard.append(chunk)


def frame(n):
    return bytes([n % 256, 0]) * FRAME


def ears_with(script):
    clock = Clock()
    a = Assistant(
        SergioClient("http://x"),
        ui=UI(),
        player=lambda b: None,
        chime=lambda f: None,
        clock=clock,
    )
    ears = Ears(a, wake_word=True, clock=clock)
    ears.spotter, _ = spotter(script)
    events = []
    ears.on_wake = events.append
    return ears, events, clock


def test_words_are_kept_while_the_call_connects_then_streamed_live():
    script = (
        [None] * 5
        + [("partial", "sergio")]
        + [None] * 4
        + [("final", [("sergio", 0.2, 1)])]
    )
    ears, events, _clock = ears_with(script)
    call = Call()
    out = [ears.feed(frame(i)) for i in range(6)]
    assert events == ["maybe"] and not any(out)
    ears.call = call  # connecting...
    for i in range(6, 11):
        ears.feed(frame(i))
    assert events == ["maybe", "yes"]
    assert call.heard == []  # not on the line yet: nothing lost, nothing sent
    call.active = True
    ears.feed(frame(11))
    # Everything since before the name, in order, then live audio.
    assert call.heard[0] == frame(0) and call.heard[-1] == frame(11)
    assert len(call.heard) == 12
    ears.feed(frame(12))
    assert call.heard[-1] == frame(12)
    assert any("confirmado" in line for line in ears.timeline)


def test_not_for_him_drops_the_call_before_it_hears_anything():
    script = [
        ("partial", "sergio"),
        ("final", [("[unk]", 0.1, 1), ("[unk]", 0.9, 1), ("sergio", 2.0, 1)]),
    ]
    ears, events, _ = ears_with(script)
    call = Call()
    ears.call = call
    ears.feed(frame(0))
    call.active = True
    ears.feed(frame(1))
    assert events == ["maybe", "no"]
    assert call.heard == []


def test_turn_fallback_requires_opt_in_and_preserves_the_whole_phrase():
    script = [("partial", "sergio"), None, ("final", [("sergio", 0.1, 1)])]
    ears, events, _ = ears_with(script)
    ears.feed(frame(0))
    ears.wake_failed()  # the app could not open the call
    ears.assistant.allow_turn_fallback = True
    ears.feed(frame(1))
    wav, addressed, clicky = ears.feed(frame(2))
    assert addressed is True and clicky is False
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getnframes() >= 3 * FRAME


def test_an_undecided_maybe_expires():
    ears, events, clock = ears_with([("partial", "sergio")])
    ears.feed(frame(0))
    clock.now += 13
    ears.feed(frame(1))
    assert events == ["maybe", "no"] and ears._wake is None


def test_model_download_unzips_once(tmp_path):
    def fetch(_url, dst):
        with zipfile.ZipFile(dst, "w") as zf:
            zf.writestr("vosk-model-small-es-0.42/conf/model.conf", "x")
            zf.writestr("vosk-model-small-es-0.42/am/final.mdl", "x")

    calls = []
    path = download_model(tmp_path, fetch=lambda u, d: (calls.append(u), fetch(u, d)))
    assert path == model_dir(tmp_path) and (path / "conf" / "model.conf").exists()
    download_model(tmp_path, fetch=lambda u, d: calls.append(u))
    assert len(calls) == 1  # already there

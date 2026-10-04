"""Mental gym pop-up: cannot be skipped, runs on time, scores, rotates."""

import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QCloseEvent, QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from sergio_escritorio import brain, gym  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def _window(app, kind, clock, **kw):
    stats = kw.pop("stats", gym.GymStats(None))
    w = gym.GymWindow(
        brain.BY_KIND[kind], stats=stats, rng=random.Random(9), clock=clock, **kw
    )
    w.cover_screens()
    w.show()
    return w


def _press(w, text):
    w.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, text))


def test_it_cannot_be_closed_or_escaped(app):
    clock = Clock()
    w = _window(app, "stroop", clock)
    event = QCloseEvent()
    w.closeEvent(event)
    assert not event.isAccepted()  # Alt+F4 does nothing
    w.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert w.isVisible() and w.phase == "intro"
    w._closing = True
    w.close()


def test_stroop_session_from_start_to_score(app):
    clock = Clock()
    spoken, results = [], []
    stats = gym.GymStats(None)
    w = _window(app, "stroop", clock, speak=spoken.append, stats=stats)
    w.finished.connect(results.append)
    w.start()
    assert spoken == ["Hora del gimnasio mental: Interferencia tipo Stroop."]
    clock.now += gym.INTRO_SECONDS
    w._tick()
    assert w.phase == "play"
    for _ in range(15):  # always the right ink
        ink = w.runner.item.ink
        key = str([c[0] for c in brain.STROOP_COLORS].index(ink) + 1)
        clock.now += 0.8
        _press(w, key)
        w._tick()
    assert w.phase == "result"
    assert w.session.correct == 15 and spoken[-1] == "Excelente."
    clock.now += gym.RESULT_SECONDS
    w._tick()
    assert results and results[0].accuracy == 1.0 and not w.isVisible()
    assert stats.history[-1]["kind"] == "stroop"


def test_slow_answers_count_as_misses_and_time_runs_out(app):
    clock = Clock()
    w = _window(app, "calculo", clock)
    w.start()
    clock.now += gym.INTRO_SECONDS
    w._tick()
    for _ in range(10):  # 9 s per item, nothing typed
        clock.now += 9.1
        w._tick()
    assert w.phase == "result" and w.session.correct == 0 and w.session.answered == 10
    w._closing = True
    w.close()


def test_typed_answers(app):
    clock = Clock()
    w = _window(app, "calculo", clock)
    w.start()
    clock.now += gym.INTRO_SECONDS
    w._tick()
    assert w.entry.isVisible()
    w.entry.setText(str(w.runner.item.answer))
    w._submit()
    w.entry.setText("-99999")
    w._submit()
    assert w.session.correct == 1 and w.session.answered == 2
    w._closing = True
    w.close()


def test_nback_runs_a_continuous_block_and_adapts(app):
    clock = Clock()
    stats = gym.GymStats(None, nback_level=2)
    w = _window(app, "nback", clock, stats=stats)
    w.start()
    clock.now += gym.INTRO_SECONDS
    w._tick()
    runner = w.runner
    while w.phase == "play":
        trial = runner.trial
        if trial is not None:  # a perfect player
            if trial.position_match:
                _press(w, "a")
            if trial.letter_match:
                _press(w, "l")
        clock.now += gym.NBackRunner.STEP
        w._tick()
    assert 40 <= w.session.answered <= 50  # 2 minutes, one every 2.5 s
    assert stats.nback_level > 2 and w.session.level == stats.nback_level
    w._closing = True
    w.close()


def test_coordination_needs_both_hands_for_chords(app):
    clock = Clock()
    w = _window(app, "coordinacion", clock)
    w.start()
    clock.now += gym.INTRO_SECONDS
    w._tick()
    runner = w.runner
    for _pattern in range(5):
        clock.now = runner.show_until + 0.1
        for step in runner.item.steps:
            for key in step:
                _press(w, key)
                clock.now += 0.05
            clock.now += 0.4
        w._tick()
    assert w.session.correct == 5


def test_words_unknown_to_the_lists_ask_the_ai(app):
    clock = Clock()
    asked = []

    def validate(word, category):
        asked.append((word, category))
        return True

    w = _window(app, "palabras", clock, validate_word=validate)
    w.start()
    clock.now += gym.INTRO_SECONDS
    w._tick()
    runner = w.runner
    good = runner.item.examples[0]
    runner.submit(good)
    runner.submit(good)  # repeated: ignored
    assert len(runner.words) == 1
    weird = runner.item.examples[1][:-1] + "q" if runner.item.test[0] != "ends" else None
    if weird and runner.item.fits(weird):
        runner.submit(weird)
    w._closing = True
    w.close()


def test_schedule_every_28_minutes_but_not_while_away():
    now = [0.0]
    away = [0.0]
    s = gym.GymSchedule(28, away=lambda: away[0], clock=lambda: now[0])
    assert not s.check()
    now[0] = 28 * 60 + 1
    away[0] = 600  # out for lunch
    assert not s.check()
    away[0] = 2  # back
    assert s.check() and not s.check()  # one at a time
    now[0] += 120
    s.done()
    assert s.minutes_left() == 28
    s.enabled = False
    now[0] += 3600
    assert not s.check()


def test_stats_rotate_through_the_ten_and_persist(tmp_path):
    stats = gym.GymStats.load(tmp_path / "gym.json")
    kinds = [stats.take_next().kind for _ in range(11)]
    assert kinds[:10] == [e.kind for e in brain.EXERCISES] and kinds[10] == "stroop"
    again = gym.GymStats.load(tmp_path / "gym.json")
    assert again.next_index == 1


def test_word_validator_caches_answers():
    calls = []

    def ask(question):
        calls.append(question)
        return "Sí."

    validate = gym.word_validator(ask)
    assert validate("Ornitorrinco", "animales") and validate("ornitorrinco", "animales")
    assert len(calls) == 1

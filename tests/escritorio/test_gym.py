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
    assert w.session.correct == 15 and spoken[-1].startswith("Excelente.")
    assert "punto de partida" in w.feedback  # the first time: your baseline
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


def test_schedule_every_12_real_minutes_start_to_start_but_not_while_away():
    now = [1_000_000.0]
    away = [0.0]
    saved = []
    s = gym.GymSchedule(12, away=lambda: away[0], clock=lambda: now[0], on_change=saved.append)
    assert s.interval == 720 and not s.check()
    now[0] += 12 * 60 + 1
    away[0] = 600  # out for lunch
    assert not s.check()
    away[0] = 2  # back
    assert s.check() and not s.check()  # one at a time
    assert saved[-1] == now[0] + 720  # the next one: 12 min after this START
    now[0] += 130  # the exercise took two minutes
    s.done()
    assert s.minutes_left() == 10  # 12 minutes start to start
    s.enabled = False
    now[0] += 3600
    assert not s.check()


def test_schedule_survives_a_restart():
    now = [5_000.0]
    s = gym.GymSchedule(12, clock=lambda: now[0], due=5_300.0)
    assert s.due == 5_300.0  # kept
    late = gym.GymSchedule(12, clock=lambda: now[0], due=1_000.0)
    assert late.due == now[0] + gym.MIN_GAP  # missed while off: soon, not at once
    fresh = gym.GymSchedule(12, clock=lambda: now[0])
    assert fresh.due == now[0] + 720


def test_stats_start_each_day_with_the_control_test_then_rotate(tmp_path):
    stats = gym.GymStats.load(tmp_path / "gym.json")
    first = stats.take_next()
    assert first.kind == "prueba"
    stats.record(brain.Session(first, correct=30, answered=31))
    assert stats.history[-1]["rate"] == 20.0  # 30 correct in 90 s
    n = len(brain.SCHEDULE)
    kinds = [stats.take_next().kind for _ in range(n + 1)]
    assert kinds[:n] == list(brain.SCHEDULE) and kinds[n] == brain.SCHEDULE[0]
    again = gym.GymStats.load(tmp_path / "gym.json")
    assert again.next_index == 1 and again.probe_today()


def test_control_test_runner(app):
    w = gym.GymWindow(brain.PROBE, rng=random.Random(4), clock=Clock(), unskippable=False)
    w._begin_play()
    runner = w.runner
    assert isinstance(runner, gym.ProbeRunner)
    right = str(runner.key_map.digit(runner.symbol))
    runner.key(right)
    wrong = str(runner.key_map.digit(runner.symbol) % 9 + 1)
    runner.key(wrong)
    assert w.session.correct == 1 and w.session.answered == 2
    runner.tick(10_000)  # no per-item time limit
    assert w.session.answered == 2 and not runner.done()
    w.resize(1200, 800)
    w.grab()  # paints the key and the symbol without errors
    w._closing = True
    w.close()


def _history(trained_acc, probe_rates, day=86400.0):
    hist = []
    for i, acc in enumerate(trained_acc):
        hist.append({"kind": "stroop", "time": i * 3600.0, "accuracy": acc})
    for i, rate in enumerate(probe_rates):
        hist.append({"kind": "prueba", "time": i * day, "rate": rate, "correct": rate * 1.5})
    return hist


def test_effectiveness_near_and_far_transfer():
    flat = brain.effectiveness(_history([0.5, 0.55, 0.8, 0.85], [40, 42, 39, 41, 40, 41, 40]))
    assert flat["near"]["stroop"] == 30.0  # trained: up 30 points
    assert flat["far"] == "no" and flat["low"] < 0 < flat["high"]
    rising = brain.effectiveness(_history([], [40, 42, 44, 46, 48, 50, 52]))
    assert rising["far"] == "sí" and rising["percent_per_week"] > 20
    few = brain.effectiveness_text(_history([0.5] * 4, [40, 41]))
    assert "llevas 2" in few
    text = brain.effectiveness_text(_history([0.5, 0.5, 0.9, 0.9], [40, 42, 39, 41, 40, 41, 40]))
    assert "incluye el cero" in text and "+40 puntos" in text


def test_trend_matches_least_squares():
    slope, low, high = brain.trend([(0, 1.0), (1, 3.0), (2, 5.0), (3, 7.0)])
    assert slope == 2.0 and low == high == 2.0


def test_word_validator_caches_answers():
    calls = []

    def ask(question):
        calls.append(question)
        return "Sí."

    validate = gym.word_validator(ask)
    assert validate("Ornitorrinco", "animales") and validate("ornitorrinco", "animales")
    assert len(calls) == 1


def test_spaced_recall_runner_shows_the_answer_and_remembers(app, tmp_path):
    clock = Clock()
    stats = gym.GymStats.load(tmp_path / "gym.json")
    w = gym.GymWindow(brain.BY_KIND["repaso"], stats=stats, rng=random.Random(2), clock=clock, unskippable=False)
    w._begin_play()
    runner = w.runner
    assert isinstance(runner, gym.RecallRunner) and len(runner.cards) == 6
    card = runner.cards[0]
    runner.submit(brain.CARDS[card][1].split("|")[0])
    assert w.session.correct == 1 and runner.shown[0]
    clock.now += 3
    runner.tick(clock.now)
    assert runner.index == 1 and runner.shown is None
    runner.submit("no sé")
    want = brain.CARDS[runner.cards[1]][1].split("|")[0]
    assert runner.shown == (False, want[:1].upper() + want[1:])
    w.resize(1200, 800)
    w.grab()
    again = gym.GymStats.load(tmp_path / "gym.json")
    assert again.deck.boxes[str(card)] == 1


def test_active_break_counts_down_a_minute(app):
    clock = Clock()
    w = gym.GymWindow(brain.BY_KIND["pausa"], rng=random.Random(2), clock=clock, unskippable=False)
    w._begin_play()
    w.runner.key("\r")
    assert w.session.answered == 0  # not before the minute is (almost) over
    clock.now += 60
    w.runner.tick(clock.now)
    assert w.runner.done() and w.session.correct == 1
    w.resize(1200, 800)
    w.grab()


class Ticker:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_sleeping_mid_exercise_starts_it_over_instead_of_scoring_zero(app):
    clock, ticker = Clock(), Ticker()
    w = gym.GymWindow(brain.BY_KIND["stroop"], rng=random.Random(1), clock=clock,
                      unskippable=False, ticker=ticker)
    clock.now += gym.INTRO_SECONDS
    ticker.now += 0.03
    w._tick()
    assert w.phase == "play"
    clock.now += 3600  # lid closed for an hour
    ticker.now += 3600
    w._tick()
    assert w.phase == "intro" and w.session.answered == 0


def test_nobody_answering_is_not_a_zero(app):
    clock = Clock()
    stats = gym.GymStats()
    w = gym.GymWindow(brain.BY_KIND["stroop"], stats=stats, rng=random.Random(1), clock=clock, unskippable=False)
    w._begin_play()
    clock.now += 200
    w._tick()
    assert w.phase == "result" and w.session.absent
    assert stats.history == []  # not recorded
    assert "no estabas" in w.session.verdict()
    w.resize(1200, 800)
    w.grab()


def test_after_the_laptop_wakes_up_the_gym_waits(app):
    now, ticker = [10_000.0], Ticker()
    s = gym.GymSchedule(12, clock=lambda: now[0], ticker=ticker)
    s.check()
    now[0] += 3 * 3600  # off for three hours: long past due
    ticker.now += 3 * 3600
    assert not s.check()
    assert s.due >= now[0] + 100


def test_every_exercise_has_steps_and_an_animated_example(app):
    from PySide6.QtGui import QImage, QPainter

    from sergio_escritorio import gym_demo

    kinds = {e.kind for e in (*brain.EXERCISES, brain.PROBE)}
    assert kinds <= set(gym_demo.STEPS) and kinds <= set(gym_demo.DEMOS)
    assert gym.INTRO_SECONDS == 11.0
    image = QImage(360, 420, QImage.Format.Format_ARGB32)
    for kind in kinds:
        frames = []
        for step in range(12):
            image.fill(0)
            p = QPainter(image)
            gym_demo.paint_demo(p, gym.QRectF(0, 0, 360, 420), kind, step * gym_demo.LOOP / 12)
            p.end()
            frames.append(bytes(image.constBits()))
        assert len(set(frames)) > 1, kind  # it moves


def _h(kind, acc, t=0.0, **kw):
    return {"kind": kind, "accuracy": acc, "time": t, "correct": 1, "total": 1, **kw}


def test_profile_scores_each_skill_from_the_answers():
    history = [_h("matrices", 0.9), _h("relacional", 0.8), _h("stroop", 0.4), _h("stroop", 0.5),
               _h("nback", 0.8, level=3), _h("prueba", 1.0)]
    prof = brain.profile(history)
    assert prof["razonamiento"]["score"] == 83 and prof["razonamiento"]["sessions"] == 2
    assert prof["memoria de trabajo"]["score"] == 90  # 3-back counts more than 2-back
    assert prof["atención"]["score"] == 47  # recent sessions weigh more
    assert "prueba" not in str(prof)  # the control test is not trained


def test_weakest_skill_comes_up_every_third_pop_up():
    history = [_h(k, a) for k, a in [("matrices", 0.9), ("matrices", 0.9), ("nback", 0.9), ("nback", 0.9),
                                     ("stroop", 0.3), ("stroop", 0.4), ("rotacion", 0.9), ("rotacion", 0.8)]]
    assert brain.weakest(brain.profile(history)) == "atención"
    picked = [brain.personal_next(i, history)[0].kind for i in range(6)]
    plain = [brain.next_exercise(i)[0].kind for i in range(6)]
    assert picked[2] == plain[2] == "repaso"  # retrieval practice is never swapped
    assert picked[5] == "stroop" and plain[5] != "stroop"
    assert picked[:2] == plain[:2] and picked[3:5] == plain[3:5]
    assert brain.personal_next(5, [])[0].kind == plain[5]  # no data: the plain rotation


def test_feedback_compares_you_with_yourself():
    history = [_h("matrices", 0.6, speed=5.0), _h("matrices", 0.6, speed=5.0)]
    better = _h("matrices", 0.9, speed=3.0)
    history.append(better)
    line = brain.feedback(history, better)
    assert "Mejor que tu media en razonamiento (60%)" in line and "más rápido" in line
    worse = _h("matrices", 0.3)
    assert "Por debajo" in brain.feedback(history + [worse], worse)
    text = brain.profile_text(history)
    assert text.startswith("Tu perfil: razonamiento 75")
    assert brain.profile_text([]).startswith("Aún no tengo tu perfil")


def test_stats_record_speed_and_report_includes_profile():
    stats = gym.GymStats(None)
    session = brain.Session(brain.BY_KIND["calculo"])
    session.record(1, 2.0)
    session.record(1, 4.0)
    entry = stats.record(session)
    assert entry["speed"] == 3.0
    assert stats.report().startswith("Tu perfil: cálculo mental")


def test_nobody_in_front_of_the_camera_postpones_a_minute():
    clock = Clock()
    s = gym.GymSchedule(12, clock=clock, ticker=clock)
    clock.now = s.due
    assert s.check() and s.running
    s.not_here()
    assert not s.running and s.due == clock.now + gym.ABSENT_RETRY
    clock.now += gym.ABSENT_RETRY
    assert s.check()


class _Feed:
    def __init__(self, frames, error=""):
        self.frames, self.error, self.keep_on, self.running = list(frames), error, False, False
        self._first_frame_at = -10.0
        self.stopped = False

    def start(self):
        self.running = True

    def stop(self):
        self.stopped = True

    def frame(self):
        return self.frames.pop(0) if self.frames else None


def test_someone_there_looks_a_few_frames_then_turns_the_camera_off():
    from sergio_escritorio.camera import someone_there

    feed = _Feed(["empty", "empty", "face"])
    assert someone_there(feed, seconds=3, detect=lambda f: f == "face") is True
    assert feed.stopped  # the light goes off right after
    assert someone_there(_Feed(["empty"] * 3), seconds=0.6, detect=lambda f: False) is False
    assert someone_there(_Feed([], error="ocupada"), seconds=0.5) is None  # no camera: no blocking

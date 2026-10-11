import math

import pytest
from sergio_escritorio.activities import Activities, Fold
from sergio_escritorio.tareas import Orchestrator


@pytest.mark.parametrize("needs", [[1], [True], [0], [-1], [2], ["1"], "1", {}])
def test_invalid_dependencies_fail_before_execution(needs):
    with pytest.raises(ValueError, match="Dependencias"):
        Orchestrator._steps({"pasos": [{"paso": "first", "depende_de": needs}]})


def test_empty_steps_cannot_renumber_dependencies():
    with pytest.raises(ValueError, match="vacíos"):
        Orchestrator._steps(
            {"pasos": [{"paso": ""}, {"paso": "second", "depende_de": [1]}]}
        )


def test_oversized_fanout_is_not_silently_truncated():
    from sergio_escritorio.tareas import MAX_FANOUT

    with pytest.raises(ValueError, match="para_cada"):
        Orchestrator._steps(
            {"pasos": [{"paso": "each", "para_cada": list(range(MAX_FANOUT + 1))}]}
        )


def test_single_fanout_item_still_reaches_its_agent():
    steps = Orchestrator._steps(
        {"pasos": [{"paso": "Check", "para_cada": ["README.md"]}]}
    )
    assert len(steps) == 1 and "README.md" in steps[0].text


def test_finish_is_idempotent_and_progress_rejects_nan():
    now = [1.0]
    activities = Activities(clock=lambda: now[0])
    aid = activities.start("build")
    with pytest.raises(ValueError, match="finito"):
        activities.update(aid, progress=math.nan)
    activities.finish(aid, ok=False)
    now[0] = 3.0
    activities.finish(aid, ok=True)
    assert activities.snapshot()[0].state == "failed"
    now[0] = 6.0
    assert activities.snapshot() == []


def test_duo_open_resolves_frost_before_the_flat_endpoint():
    fold = Fold()
    fold.angle = 172
    assert fold.effect() == fold.tilt() == 0
    fold.angle = 100
    assert 0 < fold.tilt() < 45
    fold.snap(True)
    assert fold.settled() and fold.angle == 180
    with pytest.raises(ValueError, match="finito"):
        fold.step(math.inf)


@pytest.fixture
def notch_app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_hidden_notch_stops_rendering_and_wakes_on_recall(notch_app):
    from sergio_escritorio.notch import Notch

    n = Notch(reduced_motion=False)
    try:
        n.show()
        n.hide_notch(instant=True)
        assert not n._timer.isActive() and n._edge.isActive()
        n.show_notch()
        assert n._timer.isActive() and not n._edge.isActive()
        n.hide()
        assert not n._timer.isActive()
        n.set_state("thinking")
        assert not n._timer.isActive()
        n.show()
        assert n._timer.isActive()
    finally:
        n._edge.stop()
        n.close()


def test_reduced_motion_snaps_without_hiding_activity(notch_app):
    from sergio_escritorio.notch import Notch

    n = Notch(reduced_motion=True)
    try:
        n.show()
        n.set_multitasking(True)
        n._tick()
        assert n._duo.angle == 180 and n._duo.effect() == 0
        n.hide_notch()
        assert n.hidden and not n._timer.isActive()
        n.pour_in(n.x() + 100)
        assert not n.hidden and not n._pour.active and n.isVisible()
    finally:
        n._edge.stop()
        n.close()


def test_liquid_bridge_is_bounded_and_does_not_capture_the_settled_gap(notch_app):
    from PySide6.QtCore import QRectF
    from sergio_escritorio.notch import liquid_bridge

    pill, bubble = QRectF(0, 0, 236, 36), QRectF(245, 0, 36, 36)
    assert liquid_bridge(pill, bubble, 180).isEmpty()
    bounds = liquid_bridge(pill, bubble, 135).boundingRect()
    assert bounds.width() <= 13 and bounds.height() <= 16


def test_activity_snapshot_is_not_taken_every_frame(notch_app):
    from unittest.mock import Mock

    from sergio_escritorio.notch import Notch

    n = Notch()
    n.activities = Mock(snapshot=Mock(return_value=[]))
    try:
        for _ in range(20):
            n._tick()
        assert n.activities.snapshot.call_count == 1
    finally:
        n.close()

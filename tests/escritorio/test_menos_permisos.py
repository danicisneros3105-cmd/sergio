"""Owner, 29 Oct 2026: fewer permissions, no Python windows, Vista hidden,
an app that always opens, a gym that waits and a guide step by step."""

import json

import pytest
from sergio_escritorio import control, sin_consola
from sergio_escritorio.guia import CLICK_GRACE, Clock


@pytest.mark.parametrize(
    "action,asks",
    [
        ({"action": "click", "x": 1, "y": 1}, False),
        ({"action": "type", "text": "hola"}, False),
        ({"action": "key", "keys": "ctrl+c"}, False),
        ({"action": "open_app", "target": "Spotify"}, False),
        ({"action": "open", "target": "https://youtube.com"}, False),
        ({"action": "open", "target": "C:/Docs/informe.pdf"}, False),
        ({"action": "organize"}, False),  # only a preview
        ({"action": "open", "target": "C:/Descargas/setup.exe"}, True),
        ({"action": "key", "keys": "Shift + Delete"}, True),
        ({"action": "terminal", "command": "dir"}, True),
        ({"action": "python", "code": "print(1)"}, True),
        ({"action": "close_app", "target": "Word"}, True),
        ({"action": "message", "text": "hola"}, True),
        ({"action": "organize", "apply": True}, True),
        ({"action": "skill", "name": "health_summary"}, False),
        ({"action": "skill", "name": "face_scan"}, True),
        (
            {"action": "skill", "name": "creator_apps", "args": {"action": "install"}},
            True,
        ),
    ],
)
def test_only_what_cannot_be_undone_asks(action, asks):
    assert control.risky(action) is asks


def test_helper_programs_start_without_a_console_window():
    out = sin_consola.hidden_kwargs({"capture_output": True})
    assert out["creationflags"] == sin_consola.CREATE_NO_WINDOW
    asked = sin_consola.hidden_kwargs(
        {"creationflags": 0x10}
    )  # a terminal he asked to see
    assert asked["creationflags"] == 0x10


def test_a_missing_or_broken_settings_file_never_stops_the_app(tmp_path, monkeypatch):
    from sergio_escritorio import app

    monkeypatch.setattr(app, "CONFIG", tmp_path / "config.json")
    assert app.load_config()["server_url"].startswith("http")  # missing: defaults
    (tmp_path / "config.json").write_text("{roto", encoding="utf-8")
    assert app.load_config()["port"] == 8765  # broken: defaults, kept aside
    assert (tmp_path / "config.roto.json").exists()


def test_the_guide_goes_step_by_step():
    clock = Clock(10.0, steps=3)
    assert clock.current == 0
    assert not clock.click(10.0 + CLICK_GRACE / 2)  # the click that asked
    assert clock.click(11.0) and clock.current == 1 and clock.ending is None
    clock.back(11.5)
    assert clock.current == 0
    clock.click(12.5)
    clock.click(13.5)
    assert clock.current == 2 and clock.ending is None
    clock.click(14.5)  # the last step: now it ends
    assert clock.ending == 14.5


def test_the_gym_waits_during_a_call_and_can_be_put_off_once():
    from sergio_escritorio.gym import BUSY_RETRY, SNOOZE, GymSchedule

    now = [1000.0]
    busy = [True]
    schedule = GymSchedule(
        12,
        clock=lambda: now[0],
        ticker=lambda: now[0],
        busy=lambda: busy[0],
        due=1001.0,
    )
    now[0] = 1002.0
    assert not schedule.check()  # in a call: it waits
    assert schedule.due == pytest.approx(1002.0 + BUSY_RETRY)
    busy[0] = False
    now[0] = schedule.due + 1
    schedule._last_check = 0.0
    assert schedule.check()
    schedule.snooze()
    assert not schedule.running and schedule.due == pytest.approx(now[0] + SNOOZE)


def test_vista_sees_without_showing_its_window():
    pytest.importorskip("PySide6")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from sergio_escritorio.camera import CameraWindow

    QApplication.instance() or QApplication([])

    class Feed:
        keep_on = False
        started = 0

        def start(self):
            self.started += 1

    feed = Feed()
    window = CameraWindow(feed)
    window.open()
    assert window.active and feed.keep_on and feed.started == 1
    assert not window.isVisible()  # seeing, no window
    window.allow = lambda: False
    window.close_camera()
    window.open()
    assert not window.active  # no permission: the camera stays off


def test_sergio_ve_is_hidden_even_when_asked():
    pytest.importorskip("PySide6")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from sergio_escritorio.camera import CameraWindow

    QApplication.instance() or QApplication([])

    class Feed:
        keep_on = False

        def start(self):
            pass

    window = CameraWindow(Feed())
    assert window.vista_off  # owner, 2 Nov 2026: hidden while it fails
    window.open(show=True)
    assert window.active and not window.isVisible()
    window.toggle()
    assert not window.isVisible()
    window.close_camera()


def test_risky_requests_carry_the_whole_action():
    asked = []
    c = control.Controller.__new__(control.Controller)
    c.enabled, c.strict_permissions = True, True
    c.approve = lambda request: asked.append(json.loads(request)) or False
    with pytest.raises(PermissionError):
        c.act({"action": "terminal", "command": "dir"})
    assert asked == [{"action": "terminal", "command": "dir"}]

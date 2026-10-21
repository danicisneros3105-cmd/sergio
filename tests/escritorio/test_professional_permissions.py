"""No desktop mutation or skill bypasses the professional approval gate."""

import json

import httpx
import pytest


@pytest.mark.parametrize(
    "action",
    [
        {"action": "click", "x": 1, "y": 1},
        {"action": "type", "text": "professional mail"},
        {"action": "key", "keys": "enter"},
        {"action": "open", "target": "https://example.invalid"},
        {"action": "undo_organize"},
        {"action": "message", "text": "send"},
    ],
)
def test_mutations_deny_before_backend(control_server, desktop, action):
    controller, url = control_server
    controller.strict_permissions = True
    approved = []
    controller.approve = lambda request: approved.append(json.loads(request)) or False
    response = httpx.post(
        url + "/act", headers={"Authorization": "Bearer secreto"}, json=action
    )
    assert response.status_code == 423
    assert approved == [action] and not desktop.calls


def test_skill_cannot_bypass_permissions(control_server):
    controller, url = control_server
    controller.strict_permissions = True
    controller.approve = lambda request: False
    calls = []
    controller.skills["publish"] = lambda args: calls.append(args) or "done"
    response = httpx.post(
        url + "/skill",
        headers={"Authorization": "Bearer secreto"},
        json={"name": "publish", "args": {"text": "report"}},
    )
    assert response.status_code == 423 and not calls


def _ctl(approve, clock):
    from sergio_escritorio.control import Controller

    class Backend:
        def click(self, *_a):
            pass

        def type_text(self, *_a, **_k):
            pass

    c = Controller.__new__(Controller)
    c.enabled, c.backend = True, Backend()
    c.strict_permissions, c.approve = True, approve
    c.on_click = lambda *_a: None
    c._front = lambda: ""
    c.SETTLE = set()
    c._on_activity = lambda result: None
    return c


def test_one_approval_covers_the_routine_moves_of_a_task(monkeypatch):
    import sergio_escritorio.control as control

    now = [100.0]
    monkeypatch.setattr(control.time, "monotonic", lambda: now[0])
    asked = []
    c = _ctl(lambda request: asked.append(request) or True, None)
    c.act({"action": "click", "x": 1, "y": 1})
    c.act({"action": "click", "x": 2, "y": 2})
    now[0] += 60
    c.act({"action": "click", "x": 3, "y": 3})  # the window slides while in use
    assert len(asked) == 1
    now[0] += control.APPROVAL_WINDOW_S + 1
    c.act({"action": "click", "x": 4, "y": 4})
    assert len(asked) == 2  # idle too long: asks again


def test_sensitive_actions_always_ask_even_inside_the_window():
    asked = []
    c = _ctl(lambda request: asked.append(request) or True, None)
    c.act({"action": "click", "x": 1, "y": 1})
    for action in (
        {"action": "terminal", "command": "dir"},
        {"action": "close_app", "target": "x"},
    ):
        try:
            c.act(action)
        except Exception:  # noqa: BLE001 - the fake backend has no such action
            pass
    kinds = [json.loads(r)["action"] for r in asked]
    assert kinds == ["click", "terminal", "close_app"]


def test_pausing_the_control_takes_the_approval_back():
    asked = []
    c = _ctl(lambda request: asked.append(request) or True, None)
    c.act({"action": "click", "x": 1, "y": 1})
    c.enabled = False
    c.enabled = True
    c.act({"action": "click", "x": 2, "y": 2})
    assert len(asked) == 2

"""No desktop mutation or skill bypasses the professional approval gate."""

import json

import httpx
import pytest


@pytest.mark.parametrize(
    "action",
    [
        {"action": "message", "text": "send"},
        {"action": "terminal", "command": "dir"},
        {"action": "key", "keys": "shift+delete"},
        {"action": "open", "target": "C:/Descargas/instalador.exe"},
        {"action": "organize", "apply": True},
    ],
)
def test_risky_actions_deny_before_backend(control_server, desktop, action):
    controller, url = control_server
    controller.strict_permissions = True
    approved = []
    controller.approve = lambda request: approved.append(json.loads(request)) or False
    response = httpx.post(
        url + "/act", headers={"Authorization": "Bearer secreto"}, json=action
    )
    assert response.status_code == 423
    assert approved == [action] and not desktop.calls


@pytest.mark.parametrize(
    "action",
    [
        {"action": "click", "x": 1, "y": 1},
        {"action": "type", "text": "professional mail"},
        {"action": "key", "keys": "enter"},
        {"action": "open", "target": "https://example.invalid"},
    ],
)
def test_ordinary_moves_never_ask(control_server, action):
    # Owner, 29 Oct 2026: «pide demasiados permisos para hacer cualquier cosa».
    controller, url = control_server
    controller.strict_permissions = True
    asked = []
    controller.approve = lambda request: asked.append(request) or False
    response = httpx.post(
        url + "/act", headers={"Authorization": "Bearer secreto"}, json=action
    )
    assert response.status_code != 423 and not asked


def test_skill_cannot_bypass_permissions(control_server):
    controller, url = control_server
    controller.strict_permissions = True
    controller.approve = lambda request: False
    calls = []
    controller.skills["face_scan"] = lambda args: calls.append(args) or "done"
    response = httpx.post(
        url + "/skill",
        headers={"Authorization": "Bearer secreto"},
        json={"name": "face_scan", "args": {"name": "Ana"}},
    )
    assert response.status_code == 423 and not calls  # learning a face needs consent
    controller.skills["health_summary"] = lambda args: "ok"
    response = httpx.post(
        url + "/skill",
        headers={"Authorization": "Bearer secreto"},
        json={"name": "health_summary", "args": {}},
    )
    assert response.status_code == 200  # reading his own summary just runs


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


def test_clicks_and_typing_never_ask_but_code_and_closing_do():
    asked = []
    c = _ctl(lambda request: asked.append(request) or True, None)
    c.act({"action": "click", "x": 1, "y": 1})
    c.act({"action": "type", "text": "hola"})
    assert asked == []  # owner, 29 Oct 2026: «pide demasiados permisos»
    for action in (
        {"action": "terminal", "command": "dir"},
        {"action": "close_app", "target": "x"},
        {"action": "terminal", "command": "dir"},
    ):
        try:
            c.act(action)
        except Exception:  # noqa: BLE001 - the fake backend has no such action
            pass
    kinds = [json.loads(r)["action"] for r in asked]
    assert kinds == ["terminal", "close_app", "terminal"]  # code asks every time


def test_closing_apps_asks_once_per_task(monkeypatch):
    import sergio_escritorio.control as control

    now = [100.0]
    monkeypatch.setattr(control.time, "monotonic", lambda: now[0])
    asked = []
    c = _ctl(lambda request: asked.append(request) or True, None)
    for _ in range(2):
        try:
            c.act({"action": "close_app", "target": "x"})
        except Exception:  # noqa: BLE001
            pass
    assert len(asked) == 1
    now[0] += control.APPROVAL_WINDOW_S + 1
    try:
        c.act({"action": "close_app", "target": "x"})
    except Exception:  # noqa: BLE001
        pass
    assert len(asked) == 2


def test_pausing_the_control_takes_the_approval_back():
    asked = []
    c = _ctl(lambda request: asked.append(request) or True, None)
    for _ in range(2):
        try:
            c.act({"action": "close_app", "target": "x"})
        except Exception:  # noqa: BLE001
            pass
        c.enabled = False
        c.enabled = True
    assert len(asked) == 2

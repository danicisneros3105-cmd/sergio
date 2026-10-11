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

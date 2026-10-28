"""Sergio Escritorio's control server: token, reading the screen, acting."""

import base64

import httpx
import pytest

AUTH = {"Authorization": "Bearer secreto"}


def test_every_route_needs_the_token(control_server):
    _, url = control_server
    assert httpx.get(f"{url}/health").status_code == 401
    assert (
        httpx.get(f"{url}/ui", headers={"Authorization": "Bearer otro"}).status_code
        == 401
    )
    assert (
        httpx.post(f"{url}/act", json={"action": "click", "x": 1, "y": 1}).status_code
        == 401
    )
    assert httpx.get(f"{url}/health", headers=AUTH).json() == {
        "ok": True,
        "enabled": True,
    }


def test_ui_numbers_elements_and_click_by_number(control_server, desktop):
    _, url = control_server
    ui = httpx.get(f"{url}/ui", headers=AUTH).json()
    assert ui["window"] == "WhatsApp"
    assert ui["elements"][1] == {
        "id": 2,
        "name": "Enviar",
        "type": "Button",
        "x": 930,
        "y": 1020,
        "w": 60,  # its size, so the on-screen guide can circle it
        "h": 40,
    }
    r = httpx.post(f"{url}/act", headers=AUTH, json={"action": "click", "element": 2})
    assert r.json() == {"ok": True, "result": "click at (930, 1020)"}
    assert desktop.calls == [("click", 930, 1020, "left", 1)]


def test_screenshot_is_downscaled_with_scale(control_server):
    pytest.importorskip("PIL")
    _, url = control_server
    shot = httpx.get(f"{url}/screen", headers=AUTH).json()
    assert (shot["width"], shot["height"], shot["scale"]) == (2560, 1440, 2.0)
    assert base64.b64decode(shot["image_png_b64"])[:4] == b"\x89PNG"


@pytest.mark.parametrize(
    "action,expected",
    [
        (
            {"action": "type", "text": "Hola, ¿cómo estás? ñ"},
            ("type", "Hola, ¿cómo estás? ñ"),
        ),
        ({"action": "key", "keys": "Ctrl+S"}, ("hotkey", ["ctrl", "s"])),
        ({"action": "double_click", "x": 5, "y": 6}, ("click", 5, 6, "left", 2)),
        ({"action": "right_click", "x": 5, "y": 6}, ("click", 5, 6, "right", 1)),
        ({"action": "scroll", "amount": -3}, ("scroll", -3, None, None)),
        ({"action": "open_app", "target": "Spotify"}, ("open_app", "Spotify")),
        (
            {"action": "open", "target": "https://youtube.com"},
            ("open", "https://youtube.com"),
        ),
        ({"action": "focus", "target": "whats"}, ("focus", "whats")),
    ],
)
def test_actions_reach_the_desktop(control_server, desktop, action, expected):
    _, url = control_server
    r = httpx.post(f"{url}/act", headers=AUTH, json=action)
    assert r.status_code == 200, r.text
    assert desktop.calls[-1] == expected


@pytest.mark.parametrize(
    "action",
    [
        {"action": "format_disk"},
        {"action": "click"},
        {"action": "click", "element": 99},
        {"action": "type", "text": ""},
        {"action": "key", "keys": "ctrl+"},
        {"action": "focus", "target": "Excel"},
    ],
)
def test_bad_actions_are_refused_without_touching_anything(
    control_server, desktop, action
):
    _, url = control_server
    httpx.get(f"{url}/ui", headers=AUTH)
    r = httpx.post(f"{url}/act", headers=AUTH, json=action)
    assert r.status_code == 400 and r.json()["ok"] is False
    assert [c for c in desktop.calls if c[0] != "focus"] == []


def test_user_can_pause_control(control_server, desktop):
    controller, url = control_server
    controller.enabled = False
    r = httpx.post(f"{url}/act", headers=AUTH, json={"action": "key", "keys": "enter"})
    assert r.status_code == 423 and "paused" in r.json()["error"]
    assert desktop.calls == []
    # reading the screen still works while paused
    assert httpx.get(f"{url}/ui", headers=AUTH).status_code == 200


def test_listens_only_on_localhost(control_server):
    import inspect

    from sergio_escritorio.control import make_server

    assert inspect.signature(make_server).parameters["host"].default == "127.0.0.1"

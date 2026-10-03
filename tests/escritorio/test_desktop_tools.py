"""Sergio's screen_read / desktop_action tools against a real control server."""

import httpx

from openjarvis.tools.desktop_tools import DesktopActionTool, ScreenReadTool


def _env(monkeypatch, url, token="secreto"):
    monkeypatch.setenv("SERGIO_DESKTOP_URL", url)
    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", token)
    monkeypatch.delenv("SERGIO_VISION_MODEL", raising=False)


def test_read_then_click_send(control_server, desktop, monkeypatch):
    _, url = control_server
    _env(monkeypatch, url)
    seen = ScreenReadTool().execute()
    assert seen.success
    assert "Active window: WhatsApp" in seen.content
    assert "Other open windows: Spotify" in seen.content
    assert "2. Button 'Enviar' @930,1020" in seen.content
    done = DesktopActionTool().execute(action="click", element=2)
    assert done.success and done.content == "click at (930, 1020)"
    assert desktop.calls == [("click", 930, 1020, "left", 1)]


def test_typing_spanish_text(control_server, desktop, monkeypatch):
    _, url = control_server
    _env(monkeypatch, url)
    assert (
        DesktopActionTool()
        .execute(action="type", text="Llego en 10 min, ¡gracias!")
        .success
    )
    assert desktop.calls == [("type", "Llego en 10 min, ¡gracias!")]


def test_paused_and_refused_actions_are_reported(control_server, desktop, monkeypatch):
    controller, url = control_server
    _env(monkeypatch, url)
    bad = DesktopActionTool().execute(action="click", element=7)
    assert not bad.success and "screen_read" in bad.content
    controller.enabled = False
    paused = DesktopActionTool().execute(action="key", keys="enter")
    assert not paused.success and "paused" in paused.content
    assert desktop.calls == []


def test_wrong_token_and_not_installed(control_server, monkeypatch):
    _, url = control_server
    _env(monkeypatch, url, token="mal")
    assert "bad token" in ScreenReadTool().execute().content
    _env(monkeypatch, url, token="")
    result = ScreenReadTool().execute()
    assert not result.success and "sergio escritorio instalar" in result.content
    _env(monkeypatch, "http://127.0.0.1:1")
    assert "not reachable" in DesktopActionTool().execute(action="wait").content


def test_look_uses_the_vision_model(control_server, monkeypatch):
    _, url = control_server
    _env(monkeypatch, url)
    monkeypatch.setenv("SERGIO_VISION_MODEL", "qwen2.5vl:7b")
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama.test")
    real = httpx.Client()
    sent = {}

    def handler(request):
        if request.url.host == "ollama.test":
            import json

            sent.update(json.loads(request.content))
            return httpx.Response(
                200, json={"message": {"content": "Un chat de WhatsApp abierto."}}
            )
        forwarded = real.send(request)  # the real control server
        return httpx.Response(forwarded.status_code, content=forwarded.content)

    tool = ScreenReadTool(http=httpx.Client(transport=httpx.MockTransport(handler)))
    result = tool.execute(look=True)
    assert "Screen: Un chat de WhatsApp abierto." in result.content
    assert sent["model"] == "qwen2.5vl:7b"
    assert sent["messages"][0]["images"][0]


def test_tools_are_registered():
    import importlib

    import openjarvis.tools.desktop_tools as module
    from openjarvis.core.registry import ToolRegistry

    importlib.reload(module)  # the test suite clears registries between tests

    assert ToolRegistry.contains("screen_read") and ToolRegistry.contains(
        "desktop_action"
    )

"""Sergio's internal pages open in one application window."""

from unittest.mock import Mock

import pytest
from sergio_escritorio import launch


@pytest.fixture(autouse=True)
def _no_open_window(monkeypatch):
    # No Sergio window is open and the server answers, unless a test says so.
    monkeypatch.setattr(launch, "show_in_open_window", lambda url: False)
    monkeypatch.setattr(launch, "server_up", lambda timeout=0.8: True)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/chat",
        "http://127.0.0.1:8000/swarm",
        "http://localhost:4173/#globe",
    ],
)
def test_internal_pages_have_no_browser_chrome(monkeypatch, url):
    process, browser = Mock(), Mock()
    monkeypatch.setattr(launch.shutil, "which", lambda _: "edge.exe")
    monkeypatch.setattr(launch.subprocess, "Popen", process)
    monkeypatch.setattr(launch.webbrowser, "open", browser)
    launch.open_app_window(url, wait=True)
    process.assert_called_once_with(
        ["edge.exe", f"--app={url}", "--window-size=1280,800"]
    )
    browser.assert_not_called()


def test_the_open_window_shows_the_page_instead_of_a_new_one(monkeypatch):
    process = Mock()
    monkeypatch.setattr(launch.shutil, "which", lambda _: "edge.exe")
    monkeypatch.setattr(launch.subprocess, "Popen", process)
    monkeypatch.setattr(launch, "show_in_open_window", lambda url: True)
    launch.open_app_window("http://localhost:8000/nodes", wait=True)
    process.assert_not_called()


def test_the_server_is_asked_for_the_page_path(monkeypatch):
    sent = {}

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"shown": True}

    def post(url, json, headers, timeout):
        sent.update(url=url, json=json)
        return Resp()

    monkeypatch.undo()  # the real show_in_open_window
    monkeypatch.setattr(launch, "_api_key", lambda: "")
    monkeypatch.setattr(launch, "bring_to_front", lambda title: True)
    assert launch.show_in_open_window(
        "http://localhost:8000/salud?tab=mente", post=post
    )
    assert sent["url"].endswith("/v1/app/open")
    assert sent["json"] == {"path": "/salud?tab=mente"}
    assert not launch.show_in_open_window("http://localhost:4173/#globe", post=post)


def test_multitasking_splits_the_open_window(monkeypatch):
    sent = []

    class Resp:
        status_code = 200

        def json(self):
            return {"shown": True}

    def post(url, json, headers, timeout):
        sent.append(json["path"])
        return Resp()

    monkeypatch.undo()  # the real show_in_open_window
    monkeypatch.setattr(launch, "_api_key", lambda: "")
    monkeypatch.setattr(launch, "bring_to_front", lambda title: True)
    assert launch.split_window(True, post=post)
    assert launch.split_window(False, post=post)
    assert sent == ["/?dividir=1", "/?dividir=0"]


def test_while_sergio_starts_the_window_shows_the_loading_screen(monkeypatch):
    monkeypatch.setattr(launch, "server_up", lambda timeout=0.8: False)
    url = launch.window_url("http://localhost:8000/chat")
    assert (
        url.startswith("file:")
        and "cargando.html?to=http%3A%2F%2Flocalhost%3A8000%2Fchat" in url
    )
    assert launch.window_url("http://localhost:4173/") == "http://localhost:4173/"
    assert (
        launch.window_url("http://localhost:8000/chat", up=True)
        == "http://localhost:8000/chat"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost:bad/",
        "file:///localhost:8000",
        "http://user:secret@localhost:8000",
    ],
)
def test_external_or_malformed_urls_are_not_internal(url):
    assert not launch.is_app_page(url)


def test_missing_shell_does_not_open_browser(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    browser, warning = Mock(), Mock()
    monkeypatch.setattr(launch.shutil, "which", lambda _: None)
    monkeypatch.setattr(launch.os.path, "exists", lambda _: False)
    monkeypatch.setattr(launch.webbrowser, "open", browser)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    launch.open_app_window("http://localhost:8000/chat")
    warning.assert_called_once()
    browser.assert_not_called()


def test_failed_shell_launch_does_not_open_a_browser(monkeypatch):
    browser = Mock()
    monkeypatch.setattr(launch.shutil, "which", lambda _: "edge.exe")
    monkeypatch.setattr(
        launch.subprocess, "Popen", Mock(side_effect=OSError("blocked"))
    )
    monkeypatch.setattr(launch.webbrowser, "open", browser)
    launch.open_app_window("http://localhost:8000/chat", wait=True)
    browser.assert_not_called()

"""Sergio's internal pages open in an application window."""

from unittest.mock import Mock

import pytest
from sergio_escritorio import launch


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
    launch.open_app_window(url)
    process.assert_called_once_with(
        ["edge.exe", f"--app={url}", "--window-size=1280,800"]
    )
    browser.assert_not_called()


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


def test_failed_shell_launch_reports_problem_without_browser(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    browser, warning = Mock(), Mock()
    monkeypatch.setattr(launch.shutil, "which", lambda _: "edge.exe")
    monkeypatch.setattr(
        launch.subprocess, "Popen", Mock(side_effect=OSError("blocked"))
    )
    monkeypatch.setattr(launch.webbrowser, "open", browser)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    launch.open_app_window("http://localhost:8000/chat")
    warning.assert_called_once()
    browser.assert_not_called()

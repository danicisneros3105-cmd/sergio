"""Open Sergio in standalone application windows and external links in a browser."""

from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from urllib.parse import urlparse

APP_PORTS = {8000, 4173}


def is_app_page(url: str) -> bool:
    """Recognize internal app pages, never arbitrary external sites."""
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "http"
            and parsed.hostname in ("127.0.0.1", "localhost")
            and parsed.port in APP_PORTS
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def open_app_window(url: str) -> None:
    """Internal pages get a standalone app window; external links use the browser."""
    if not is_app_page(url):
        webbrowser.open(url)
        return
    edge = shutil.which("msedge") or next(
        (
            p
            for p in (
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    "Microsoft",
                    "Edge",
                    "Application",
                    "msedge.exe",
                ),
            )
            if os.path.exists(p)
        ),
        None,
    )
    if edge:
        try:
            subprocess.Popen([edge, f"--app={url}", "--window-size=1280,800"])
            return
        except OSError:
            pass
    from PySide6.QtWidgets import QMessageBox

    QMessageBox.warning(
        None,
        "Sergio",
        "No se pudo abrir la ventana de Sergio. "
        "Repare o instale Microsoft Edge y vuelva a intentarlo.",
    )


__all__ = ["is_app_page", "open_app_window"]

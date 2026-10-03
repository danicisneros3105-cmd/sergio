"""Open web pages that belong to Sergio (the 3D globe) as app windows."""

from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from urllib.parse import urlparse

GLOBE_PORTS = {4173}


def is_app_page(url: str) -> bool:
    """Sergio's own pages (the globe) open without browser bars."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.hostname in ("127.0.0.1", "localhost") and parsed.port in GLOBE_PORTS


def open_app_window(url: str) -> None:
    """Open a page (the 3D globe) as its own app window, without browser bars."""
    edge = shutil.which("msedge") or next(
        (
            p
            for p in (
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            )
            if os.path.exists(p)
        ),
        None,
    )
    if edge:
        subprocess.Popen([edge, f"--app={url}", "--window-size=1280,800"])
    else:
        webbrowser.open(url)


__all__ = ["is_app_page", "open_app_window"]

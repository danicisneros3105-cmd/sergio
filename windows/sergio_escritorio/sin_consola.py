"""No black console windows popping up (owner, 29 Oct 2026: «aparecen cosas
de Python de la nada»).

Sergio runs with ``pythonw`` (no console), but every helper program it
starts (ffmpeg, wsl, powershell, a Python script, git…) is a console program,
and Windows gives each one its own black window that flashes and vanishes.
:func:`install` makes every ``subprocess`` call hidden by default. A call
that sets its own ``creationflags`` (for example a terminal the owner asked
to see, with ``CREATE_NEW_CONSOLE``) keeps them.
"""

from __future__ import annotations

import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000
_done = [False]


def hidden_kwargs(kwargs: dict) -> dict:
    """*kwargs* for ``Popen`` with no console window unless asked otherwise."""
    if kwargs.get("creationflags"):
        return kwargs
    out = dict(kwargs)
    out["creationflags"] = CREATE_NO_WINDOW
    if sys.platform == "win32" and out.get("startupinfo") is None:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0  # SW_HIDE
        out["startupinfo"] = info
    return out


def install() -> None:
    """Hide the console of every program Sergio starts (Windows only)."""
    if sys.platform != "win32" or _done[0]:
        return
    _done[0] = True
    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):  # noqa: ANN001, N807
        original(self, *args, **hidden_kwargs(kwargs))

    subprocess.Popen.__init__ = __init__  # type: ignore[method-assign]


__all__ = ["CREATE_NO_WINDOW", "hidden_kwargs", "install"]

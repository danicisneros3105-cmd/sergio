"""Sergio on the Windows taskbar as an app of its own.

The Sergio window is an Edge app window, so by itself Windows groups it with
Edge and «Pin to taskbar» would pin Edge. Windows lets an app claim a window:
an *AppUserModelID* plus a relaunch command, icon and name in the window's
property store (``SHGetPropertyStoreForWindow``). With them the window gets
its own taskbar button with Sergio's mark, and pinning it pins Sergio — the
pinned button starts ``pythonw -m sergio_escritorio``, which opens the window.
The desktop process and the shortcuts carry the same ID, so they all group
together. Windows forbids apps from pinning themselves: the owner pins once
(right click → «Anclar a la barra de tareas»).
"""

from __future__ import annotations

import ctypes
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple

APP_ID = "Sergio.Asistente"
APP_NAME = "Sergio"
# PKEY_AppUserModel_* : {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, pid
_FMTID = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
PIDS = {"relaunch_command": 2, "relaunch_icon": 3, "relaunch_name": 4, "id": 5}
VT_LPWSTR = 31
_IID_IPROPERTYSTORE = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"


def relaunch_command() -> str:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else exe
    return f'"{runner}" -m sergio_escritorio'


def icon_path() -> str:
    ico = Path(__file__).resolve().parent.parent / "sergio.ico"
    if ico.is_file():
        return f"{ico},0"
    return str(Path(__file__).with_name("resources") / "sergio.png")


def properties() -> Dict[str, str]:
    """What the window says about itself (the relaunch keys go first: Windows
    reads them when the ID is set)."""
    return {
        "relaunch_command": relaunch_command(),
        "relaunch_icon": icon_path(),
        "relaunch_name": APP_NAME,
        "id": APP_ID,
    }


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def of(cls, text: str) -> "_GUID":
        u = uuid.UUID(text)
        g = cls()
        g.Data1, g.Data2, g.Data3 = u.fields[0], u.fields[1], u.fields[2]
        for i, b in enumerate(u.bytes[8:]):
            g.Data4[i] = b
        return g


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_uint32)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("r1", ctypes.c_ushort),
        ("r2", ctypes.c_ushort),
        ("r3", ctypes.c_ushort),
        ("pwszVal", ctypes.c_wchar_p),
        ("pad", ctypes.c_void_p),
    ]


def key(name: str) -> Tuple[_GUID, int]:
    return _GUID.of(_FMTID), PIDS[name]


def claim_process() -> bool:
    """The desktop process (tray, notch, control center) groups as Sergio."""
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)  # type: ignore[attr-defined]
        return True
    except Exception:  # noqa: BLE001
        return False


def claim_window(hwnd: int) -> bool:
    """Give an (Edge app) window Sergio's identity on the taskbar."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        store = ctypes.c_void_p()
        iid = _GUID.of(_IID_IPROPERTYSTORE)
        hr = ctypes.windll.shell32.SHGetPropertyStoreForWindow(  # type: ignore[attr-defined]
            ctypes.c_void_p(hwnd), ctypes.byref(iid), ctypes.byref(store)
        )
        if hr != 0 or not store.value:
            return False
        vtbl = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        set_value = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT)
        )(vtbl[6])
        commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtbl[7])
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
        ok = True
        for name, value in properties().items():
            fmtid, pid = key(name)
            pk = _PROPERTYKEY(fmtid, pid)
            pv = _PROPVARIANT(vt=VT_LPWSTR, pwszVal=value)
            ok = set_value(store, ctypes.byref(pk), ctypes.byref(pv)) == 0 and ok
        commit(store)
        release(store)
        return ok
    except Exception:  # noqa: BLE001 — the window still works, just grouped with Edge
        return False


def claim_sergio_windows(title: str = "Sergio") -> int:
    """Every visible Sergio window gets the identity; returns how many."""
    from sergio_escritorio.windows_backend import _visible_windows

    n = 0
    try:
        for hwnd, name in _visible_windows(minimized=True):
            if name == title or name.startswith(title + " "):
                n += int(claim_window(hwnd))
    except Exception:  # noqa: BLE001
        return n
    return n


def describe() -> Dict[str, Any]:
    return {"id": APP_ID, **properties()}


__all__ = ["APP_ID", "claim_process", "claim_sergio_windows", "claim_window", "describe", "properties"]

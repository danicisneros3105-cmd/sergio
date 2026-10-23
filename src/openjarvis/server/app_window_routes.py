"""One Sergio window: the desktop shows a page in the open window.

Every click in the notch, the tray or a voice order («abre Nodes») used to
open a new Edge window, and each new window opened its own conversation.
Now the app window keeps one request waiting here (``POST /v1/app/wait``, a
long poll: it is not throttled when the window is in the background). The
desktop asks ``POST /v1/app/open`` with the page: if a window is waiting, it
gets the page at once and the desktop only brings it to the front; if none
answers within 2 s, the desktop opens a new window (with the loading screen).
"""

from __future__ import annotations

import asyncio
import ipaddress
import time
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/app", tags=["app"])

WAIT_SECONDS = 25.0
ALIVE_SECONDS = 4.0  # a window between two waits still counts as open
ACK_SECONDS = 2.0


class _Window:
    def __init__(self) -> None:
        self.inbox: asyncio.Queue[str] = asyncio.Queue()
        self.calls = 0  # waits started: a window that got a page asks again
        self.waiting = 0
        self.seen = 0.0
        self.focused_at = 0.0


_windows: dict[str, _Window] = {}


class WaitRequest(BaseModel):
    id: str
    focused: bool = False


class OpenRequest(BaseModel):
    path: str = "/"


def _same_computer(host: str) -> bool:
    """Loopback, or Windows reaching the server in WSL (NAT 172.16.0.0/12)."""
    if host in ("localhost", "testclient"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip in ipaddress.ip_network("172.16.0.0/12")


def _alive(w: _Window, now: float) -> bool:
    return w.waiting > 0 or now - w.seen < ALIVE_SECONDS


@router.post("/wait")
async def wait(req: WaitRequest, request: Request) -> dict[str, Any]:
    """Held until the desktop asks to show a page here (or 25 s pass)."""
    if not _same_computer(request.client.host if request.client else ""):
        # a phone or another computer: the desktop's pages are not for it
        return {"navigate": None, "local": False}
    key = req.id[:64] or "?"
    w = _windows.setdefault(key, _Window())
    now = time.monotonic()
    w.seen = now
    w.calls += 1
    if req.focused:
        w.focused_at = now
    w.waiting += 1
    try:
        deadline = now + WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                path = await asyncio.wait_for(w.inbox.get(), timeout=1.0)
                return {"navigate": path}
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    break  # the window was closed
        return {"navigate": None}
    finally:
        w.waiting -= 1
        w.seen = time.monotonic()
        for name, other in list(_windows.items()):  # forget closed windows
            if not _alive(other, w.seen) and other.inbox.empty():
                _windows.pop(name, None)


@router.post("/open")
async def open_page(req: OpenRequest) -> dict[str, Any]:
    """Show *path* in the open window; ``shown: false`` = open a new one.

    A window counts only if it takes the page and asks again right after
    (its next wait): a closed window can leave a request hanging here that
    takes the page and answers nobody."""
    path = req.path if req.path.startswith("/") else "/" + req.path
    tried: set[int] = set()
    while True:
        now = time.monotonic()
        live = [
            (name, w)
            for name, w in _windows.items()
            if _alive(w, now) and id(w) not in tried
        ]
        if not live:
            return {"shown": False}
        name, best = max(live, key=lambda item: (item[1].focused_at, item[1].seen))
        tried.add(id(best))
        calls = best.calls
        best.inbox.put_nowait(path)
        deadline = now + ACK_SECONDS
        while time.monotonic() < deadline:
            if best.inbox.empty() and best.calls > calls:
                return {"shown": True, "title": "Sergio"}
            await asyncio.sleep(0.05)
        while not best.inbox.empty():  # nobody took it
            best.inbox.get_nowait()
        _windows.pop(name, None)  # that window is gone


def reset_for_tests() -> None:
    _windows.clear()


__all__ = ["router", "reset_for_tests"]

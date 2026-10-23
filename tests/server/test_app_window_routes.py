"""One Sergio window: the desktop shows pages in the window already open."""

from __future__ import annotations

import asyncio

from openjarvis.server import app_window_routes as aw


class _Client:
    host = "127.0.0.1"


class _Req:
    def __init__(self) -> None:
        self.gone = False
        self.client = _Client()

    async def is_disconnected(self) -> bool:
        return self.gone


def test_no_window_open_means_open_a_new_one():
    aw.reset_for_tests()
    assert asyncio.run(aw.open_page(aw.OpenRequest(path="/nodes"))) == {"shown": False}


def test_the_open_window_gets_the_page_and_the_focused_one_wins():
    aw.reset_for_tests()

    async def window(name, focused, got):
        # like lib/appWindow.ts: wait, take the page, wait again
        while True:
            answer = await aw.wait(aw.WaitRequest(id=name, focused=focused), _Req())
            if answer["navigate"]:
                got.append(answer["navigate"])

    async def scenario():
        back_got, front_got = [], []
        back = asyncio.create_task(window("a", False, back_got))
        front = asyncio.create_task(window("b", True, front_got))
        await asyncio.sleep(0.05)
        shown = await aw.open_page(aw.OpenRequest(path="salud"))
        back.cancel()
        front.cancel()
        return shown, front_got, back_got

    shown, front_got, back_got = asyncio.run(scenario())
    assert shown["shown"] is True
    assert front_got == ["/salud"] and back_got == []


def test_a_hanging_request_of_a_closed_window_does_not_count():
    """The window was closed but its request still hangs here: it takes the
    page and never asks again, so the desktop opens a new window."""
    aw.reset_for_tests()

    async def scenario():
        zombie = asyncio.create_task(aw.wait(aw.WaitRequest(id="z"), _Req()))
        await asyncio.sleep(0.05)
        shown = await aw.open_page(aw.OpenRequest(path="/nodes"))
        await zombie
        return shown

    assert asyncio.run(scenario()) == {"shown": False}


def test_a_closed_window_is_not_used(monkeypatch):
    aw.reset_for_tests()
    monkeypatch.setattr(aw, "ALIVE_SECONDS", 0.0)

    async def scenario():
        req = _Req()
        task = asyncio.create_task(aw.wait(aw.WaitRequest(id="a"), req))
        await asyncio.sleep(0.05)
        req.gone = True  # the window was closed
        await asyncio.wait_for(task, 3)
        return await aw.open_page(aw.OpenRequest(path="/chat"))

    assert asyncio.run(scenario()) == {"shown": False}


def test_a_phone_never_receives_the_desktop_pages():
    aw.reset_for_tests()
    phone = _Req()
    phone.client = type("C", (), {"host": "192.168.1.40"})()
    got = asyncio.run(aw.wait(aw.WaitRequest(id="p"), phone))
    assert got["navigate"] is None and not got["local"]
    assert asyncio.run(aw.open_page(aw.OpenRequest(path="/chat"))) == {"shown": False}

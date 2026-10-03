"""Hold Ctrl+Alt to talk, Clicky-style: speak while holding, release to send.

Only Ctrl+Alt *alone* counts: if another key joins (Ctrl+Alt+C, Ctrl+Alt+End,
or AltGr+2 to type "@") it was a shortcut, so nothing starts or the
recording is dropped.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

HOLD_DELAY = 0.45  # seconds both keys must be held before listening


def key_name(key: Any) -> str:
    """'ctrl', 'alt' or 'other' for a pynput key."""
    name = str(getattr(key, "name", "") or "")
    if name.startswith("ctrl"):
        return "ctrl"
    if name.startswith("alt"):  # alt, alt_l, alt_r, alt_gr
        return "alt"
    return "other"


class HoldDetector:
    def __init__(
        self,
        on_start: Callable[[], None],
        on_end: Callable[[], None],
        on_cancel: Callable[[], None],
        *,
        delay: float = HOLD_DELAY,
        timer: Callable[[float, Callable[[], None]], Any] = threading.Timer,
    ) -> None:
        self.on_start, self.on_end, self.on_cancel = on_start, on_end, on_cancel
        self.delay = delay
        self._timer_factory = timer
        self._down: set[str] = set()
        self._timer: Any = None
        self._active = False
        self._spoiled = False  # another key joined: wait for a clean release
        self._lock = threading.Lock()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
            if self._spoiled or self._down != {"ctrl", "alt"}:
                return
            self._active = True
        self.on_start()

    def press(self, key: Any) -> None:
        name = key_name(key)
        with self._lock:
            if name == "other":
                if self._down:
                    self._spoiled = True
                    self._cancel_timer()
                    if self._active:
                        self._active = False
                        cancel = True
                    else:
                        cancel = False
                else:
                    cancel = False
            else:
                cancel = False
                self._down.add(name)
                if (
                    self._down == {"ctrl", "alt"}
                    and not self._spoiled
                    and not self._active
                    and self._timer is None
                ):
                    self._timer = self._timer_factory(self.delay, self._fire)
                    self._timer.start()
        if cancel:
            self.on_cancel()

    def release(self, key: Any) -> None:
        name = key_name(key)
        with self._lock:
            if name == "other":
                return
            self._down.discard(name)
            self._cancel_timer()
            end = self._active
            self._active = False
            if not self._down:
                self._spoiled = False
        if end:
            self.on_end()


__all__ = ["HOLD_DELAY", "HoldDetector", "key_name"]

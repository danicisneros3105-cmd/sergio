"""«Deshacer lo último de Sergio»: what Sergio did that can be undone.

Every reversible thing Sergio does on the computer leaves one entry here —
what it was, in plain words, and how to undo it. The control center's
«Deshacer» button (and «Sergio, deshaz eso») takes the newest one back:
an app it opened is closed, text it typed is undone (Ctrl+Z in that window),
files it organised go back where they were. What cannot be undone (a sent
message, a deleted file) is never recorded as if it could.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

KEEP = 20
STALE_S = 30 * 60  # older than this: too late to undo safely


@dataclass
class Step:
    what: str  # «Abrí Spotify»
    undo: Callable[[], object]
    undo_text: str  # «Cerré Spotify»
    at: float


class Journal:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._steps: List[Step] = []
        self._lock = threading.Lock()
        self.clock = clock

    def add(self, what: str, undo: Callable[[], object], undo_text: str) -> None:
        with self._lock:
            self._steps.append(Step(what, undo, undo_text, self.clock()))
            del self._steps[:-KEEP]

    def last(self) -> Optional[Step]:
        with self._lock:
            fresh = [s for s in self._steps if self.clock() - s.at < STALE_S]
            return fresh[-1] if fresh else None

    def undo_last(self) -> str:
        """Undo the newest step; what was done, in words."""
        with self._lock:
            now = self.clock()
            while self._steps and now - self._steps[-1].at >= STALE_S:
                self._steps.pop()
            if not self._steps:
                return "No hay nada reciente que deshacer."
            step = self._steps.pop()
        try:
            step.undo()
        except Exception as exc:  # noqa: BLE001 — say it, never pretend
            return f"No pude deshacer «{step.what}»: {exc}"
        return step.undo_text


_JOURNAL = Journal()


def journal() -> Journal:
    return _JOURNAL


__all__ = ["Journal", "Step", "journal"]

"""What Sergio is doing, in pictures (owner, 1 Nov 2026: «debe darte
imágenes de lo que está haciendo, como Claude Code app»).

While the operator works on the real screen, every step leaves a small
picture of the screen and one line of what it did. The chat asks for the
strip (``GET /film`` on the control server, ``/v1/actividad`` on Sergio's
server) and shows it under the reply as the task moves. Kept in memory only,
the last task's pictures; nothing is written to disk.
"""

from __future__ import annotations

import base64
import io
import threading
import time
from typing import Any

THUMB_WIDTH = 480
MAX_FRAMES = 24  # one task; the oldest go first


def thumbnail(png: bytes, width: int = THUMB_WIDTH) -> str:
    """A small JPEG of the screen as base64 ('' when it cannot be read)."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(png)).convert("RGB")
        if img.width > width:
            img = img.resize((width, max(1, round(img.height * width / img.width))))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=70)
        return base64.b64encode(out.getvalue()).decode()
    except Exception:  # noqa: BLE001 — a picture never stops the task
        return ""


class Film:
    def __init__(self, clock: Any = time.time) -> None:
        self.clock = clock
        self._lock = threading.Lock()
        self.task_id = 0
        self.goal = ""
        self.state = "idle"  # working | done | failed | asking | idle
        self.result = ""
        self.frames: list[dict] = []

    def start(self, goal: str) -> None:
        with self._lock:
            self.task_id += 1
            self.goal = goal
            self.state = "working"
            self.result = ""
            self.frames = []

    def frame(self, png: bytes, caption: str) -> None:
        jpg = thumbnail(png)
        with self._lock:
            self.frames.append({"n": len(self.frames) + 1, "at": self.clock(),
                                "caption": caption[:140], "jpeg_b64": jpg})  # fmt: skip
            del self.frames[:-MAX_FRAMES]

    def end(self, state: str, result: str) -> None:
        with self._lock:
            self.state = state
            self.result = result[:300]

    def to_dict(self, since: int = 0) -> dict:
        """The strip; *since* leaves out frames the chat already has."""
        with self._lock:
            return {"ok": True, "task": self.task_id, "goal": self.goal,
                    "state": self.state, "result": self.result,
                    "frames": [f for f in self.frames if f["n"] > since]}  # fmt: skip


__all__ = ["Film", "MAX_FRAMES", "thumbnail"]

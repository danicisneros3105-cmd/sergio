"""The four ways to make a video, and the budget that keeps each one honest.

* **Test** — quick and basic, but well made: fast models, no review, 720p.
* **Basic** — normal: one review pass, 1080p, medium time.
* **Post quality** — very high quality and ready to post: the strongest
  director, two reviews, several candidate clips judged by eye, colour
  finishing and the posting package (title, description, credits, cover).
  Slow.
* **Absolut Cinema** — the best Sergio can do: four reviews, the best clip
  out of many, AI video and 3D shots where they lift the film, 4K and a
  10-bit master. The slowest. (No one can promise views; this is the mode
  that gives a video its best chance.)

Every job carries a :class:`Budget`: model calls, pictures, downloads,
seconds of AI video, 3D shots and wall-clock time. When something runs out
the job does not loop or keep paying: that part stops and the video is
finished with what it has (a shot without a new picture keeps its card).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict

ORDER = ("test", "basic", "post", "cinema")
NAMES = {
    "test": "Test",
    "basic": "Basic",
    "post": "Post quality",
    "cinema": "Absolut Cinema",
}
ALIASES = {
    "test": "test", "prueba": "test", "rapido": "test", "rápido": "test",
    "basic": "basic", "basico": "basic", "básico": "basic", "normal": "basic",
    "post": "post", "post quality": "post", "postquality": "post", "publicar": "post",
    "cinema": "cinema", "absolut cinema": "cinema", "absolute cinema": "cinema",
    "absolutcinema": "cinema", "cine": "cinema",
}  # fmt: skip


@dataclass(frozen=True)
class Mode:
    key: str
    passes: int  # review passes by the editor
    size: str  # "720", "1080" or "2160" (height for 16:9)
    preset: str  # x264 preset of the final render
    candidates: int  # clips found per shot, the best chosen by eye
    director_strong: bool  # the strongest model directs (else the fast one)
    finishing: bool  # colour chain from Creator's video_master
    master: str  # a 10-bit master next to the mp4 ("" none)
    package: bool  # title, description, credits and cover to post
    limits: Dict[str, float] = field(default_factory=dict)


MODES: Dict[str, Mode] = {
    "test": Mode("test", 0, "720", "veryfast", 1, False, False, "", False,
                 {"llm": 6, "images": 8, "downloads": 25, "ai_seconds": 0, "blender": 0, "minutes": 30}),
    "basic": Mode("basic", 1, "1080", "fast", 2, False, False, "", False,
                  {"llm": 14, "images": 25, "downloads": 60, "ai_seconds": 0, "blender": 1, "minutes": 75}),
    "post": Mode("post", 2, "1080", "medium", 3, True, True, "", True,
                 {"llm": 36, "images": 60, "downloads": 150, "ai_seconds": 40, "blender": 3, "minutes": 240}),
    "cinema": Mode("cinema", 4, "2160", "slow", 5, True, True, "hevc10", True,
                   {"llm": 80, "images": 140, "downloads": 320, "ai_seconds": 120, "blender": 8, "minutes": 720}),
}  # fmt: skip


def get(name: str) -> Mode:
    key = ALIASES.get(str(name or "").strip().lower(), "")
    return MODES[key or "basic"]


class OverBudget(RuntimeError):
    """A limit of the job was reached: stop that part, finish the video."""


@dataclass
class Budget:
    """What a job may still spend (kept in its state, so a resumed job does
    not get a fresh allowance)."""

    limits: Dict[str, float]
    spent: Dict[str, float] = field(default_factory=dict)
    started: float = field(default_factory=time.time)

    def left(self, kind: str) -> float:
        if kind == "minutes":
            return self.limits.get("minutes", 0) - (time.time() - self.started) / 60
        return self.limits.get(kind, 0) - self.spent.get(kind, 0)

    def can(self, kind: str, amount: float = 1) -> bool:
        return self.left(kind) >= amount and self.left("minutes") > 0

    def spend(self, kind: str, amount: float = 1) -> None:
        """Count *amount* of *kind*, or raise OverBudget without counting."""
        if self.left("minutes") <= 0:
            raise OverBudget("se acabó el tiempo de este modo")
        if self.left(kind) < amount:
            raise OverBudget(f"se acabó el presupuesto de {kind}")
        self.spent[kind] = self.spent.get(kind, 0) + amount

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], mode: Mode) -> "Budget":
        if not data:
            return cls(dict(mode.limits))
        return cls(
            dict(data.get("limits") or mode.limits),
            dict(data.get("spent") or {}),
            float(data.get("started") or time.time()),
        )


__all__ = ["ALIASES", "MODES", "NAMES", "ORDER", "Budget", "Mode", "OverBudget", "get"]

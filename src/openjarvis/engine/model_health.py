"""How each Gemini model has been answering lately, so the fast ones go first.

Measured on 2026-10-21 with a free key: the newest Flash (3.8, 3.7) took
40-60 s or timed out for a one-word answer while 3.6, 3.5 and 3-flash
answered in about 1 s. Trying the newest first on every message is the
«lag» the owner sees. Here every answer and failure is remembered (in
memory and in ``~/.openjarvis/model_health.json``, so a restart does not
forget it): a model that was slow or failing is moved behind the ones that
answer fast, and is tried again first once it recovers.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

# A model slower than this (seconds to the first token) is "slow".
SLOW_SECONDS = 6.0
# A failure (timeout, 503, 504) pushes a model back for this long.
FAIL_SECONDS = 180.0
# A measurement older than this is forgotten, so a model that was slow gets
# a new chance (Google's load changes during the day).
RECHECK_SECONDS = 1200.0
_ALPHA = 0.4  # weight of the newest measurement in the running average
_SAVE_EVERY = 10.0


def transient(exc: BaseException) -> bool:
    """A failure of the service or the network, not of the request: another
    model (or the same one later) will answer."""
    text = f"{type(exc).__name__} {exc}"
    low = text.lower()
    return any(
        marker in text
        for marker in (
            "503",
            "504",
            "502",
            "500 INTERNAL",
            "UNAVAILABLE",
            "DEADLINE_EXCEEDED",
        )
    ) or any(
        marker in low
        for marker in (
            "timed out",
            "timeout",
            "high demand",
            "overloaded",
            "connection reset",
            "connection aborted",
            "connecterror",
            "remoteprotocolerror",
            "server disconnected",
            "temporarily unavailable",
            "name resolution",
        )
    )


class ModelHealth:
    def __init__(
        self,
        path: Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = path
        self.clock = clock
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, float]] = {}
        self._saved = 0.0
        self._load()

    def _load(self) -> None:
        if self.path is None:
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            for name, entry in raw.items():
                if isinstance(entry, dict):
                    self._data[str(name)] = {
                        k: float(v)
                        for k, v in entry.items()
                        if isinstance(v, (int, float))
                    }

    def _save(self, force: bool = False) -> None:
        if self.path is None:
            return
        now = self.clock()
        if not force and now - self._saved < _SAVE_EVERY:
            return
        self._saved = now
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass  # a read-only home only loses the memory between restarts

    def ok(self, model: str, seconds: float) -> None:
        """*model* answered; *seconds* to its first token (or full answer)."""
        if not model:
            return
        with self._lock:
            entry = self._data.setdefault(model, {})
            old = entry.get("latency")
            seconds = max(0.0, float(seconds))
            entry["latency"] = (
                seconds if old is None else old + _ALPHA * (seconds - old)
            )
            entry["at"] = self.clock()
            entry.pop("failed_until", None)
            entry["fails"] = 0.0
            self._save()

    def failed(self, model: str, seconds: float | None = None) -> None:
        """*model* timed out or the service was busy."""
        if not model:
            return
        with self._lock:
            entry = self._data.setdefault(model, {})
            fails = entry.get("fails", 0.0) + 1
            entry["fails"] = fails
            # Repeated failures rest longer (up to ~12 min).
            entry["failed_until"] = self.clock() + FAIL_SECONDS * min(4.0, fails)
            entry["at"] = self.clock()
            if seconds is not None:
                entry["latency"] = max(entry.get("latency", 0.0), float(seconds))
            self._save(force=True)

    def latency(self, model: str) -> float | None:
        entry = self._data.get(model, {})
        if self.clock() - entry.get("at", 0.0) > RECHECK_SECONDS:
            return None
        return entry.get("latency")

    def resting(self, model: str) -> bool:
        return self._data.get(model, {}).get("failed_until", 0.0) > self.clock()

    def order(self, models: Iterable[str]) -> list[str]:
        """The same models, fastest healthy ones first. Unknown models keep
        their place among the healthy ones (the caller's order is the
        preference); slow ones go after them; resting ones go last."""
        models = list(dict.fromkeys(models))

        def rank(item: tuple[int, str]) -> tuple[int, int]:
            index, name = item
            if self.resting(name):
                return (2, index)
            lat = self.latency(name)
            if lat is not None and lat > SLOW_SECONDS:
                return (1, index)
            return (0, index)

        return [name for _, name in sorted(enumerate(models), key=rank)]

    def hedge_after(self, model: str, default: float, floor: float = 2.5) -> float:
        """Seconds to wait for *model* before a sibling starts too: about
        twice what it usually takes, never above *default*."""
        lat = self.latency(model)
        if lat is None:
            return default
        return max(floor, min(default, 2.0 * lat + 1.0))


_HEALTH: ModelHealth | None = None


def health() -> ModelHealth:
    global _HEALTH
    if _HEALTH is None:
        path = None
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                from openjarvis.core.paths import get_config_dir

                path = get_config_dir() / "model_health.json"
            except Exception:  # noqa: BLE001 — remember in memory only
                path = None
        _HEALTH = ModelHealth(path)
    return _HEALTH


def reset_for_tests() -> None:
    global _HEALTH
    _HEALTH = ModelHealth(None)


__all__ = [
    "FAIL_SECONDS",
    "ModelHealth",
    "RECHECK_SECONDS",
    "SLOW_SECONDS",
    "health",
    "reset_for_tests",
    "transient",
]

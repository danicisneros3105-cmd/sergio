"""Fast Gemini models go first; a hanging one is overtaken while streaming."""

from __future__ import annotations

import asyncio
import time

import pytest

from openjarvis.engine.hedge import HedgeError, first_stream
from openjarvis.engine.model_health import (
    FAIL_SECONDS,
    RECHECK_SECONDS,
    ModelHealth,
    transient,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_slow_and_failing_models_go_behind_the_fast_ones():
    clock = Clock()
    h = ModelHealth(None, clock)
    models = ["new", "mid", "old"]
    assert h.order(models) == models  # nothing known: the caller's preference
    h.ok("new", 40.0)  # answered, but after 40 s
    h.ok("mid", 1.2)
    h.failed("old")
    assert h.order(models) == ["mid", "new", "old"]
    assert h.hedge_after("mid", 5.0) == pytest.approx(3.4)
    assert h.hedge_after("unknown", 5.0) == 5.0


def test_a_slow_model_gets_a_new_chance_later():
    clock = Clock()
    h = ModelHealth(None, clock)
    h.failed("new", 30.0)
    assert h.order(["new", "mid"]) == ["mid", "new"]
    clock.now += FAIL_SECONDS + RECHECK_SECONDS + 1
    assert h.order(["new", "mid"]) == ["new", "mid"]
    h.ok("new", 0.8)  # recovered: first again, rest cleared
    assert not h.resting("new") and h.latency("new") is not None


def test_health_survives_a_restart(tmp_path):
    path = tmp_path / "model_health.json"
    h = ModelHealth(path)
    h.failed("new", 50.0)
    again = ModelHealth(path)
    assert again.order(["new", "mid"]) == ["mid", "new"]


def test_timeouts_and_busy_services_are_transient():
    assert transient(RuntimeError("504 DEADLINE_EXCEEDED. Deadline expired"))
    assert transient(TimeoutError("The read operation timed out"))
    assert transient(RuntimeError("503 UNAVAILABLE high demand"))
    assert not transient(ValueError("400 INVALID_ARGUMENT: bad schema"))


def _collect(gen):
    async def run():
        return [item async for item in gen]

    return asyncio.run(run())


def _hang(seconds: float, items: list[str]):
    def start():
        time.sleep(seconds)
        yield from items

    return start


def test_a_hanging_stream_is_overtaken_by_the_next():
    slow: list[int] = []
    t0 = time.monotonic()
    out = _collect(
        first_stream(
            [_hang(5, ["late"]), _hang(0, ["a", "b"])],
            hedge_after=0.2,
            on_slow=lambda i, s: slow.append(i),
        )
    )
    assert out == [(1, "a"), (1, "b")]
    assert time.monotonic() - t0 < 2
    assert slow == [0]


def test_a_busy_model_moves_on_at_once_but_a_bad_request_does_not():
    def busy():
        raise RuntimeError("503 UNAVAILABLE")
        yield  # pragma: no cover

    def bad():
        raise ValueError("400 INVALID_ARGUMENT")
        yield  # pragma: no cover

    out = _collect(
        first_stream(
            [busy, _hang(0, ["ok"])],
            hedge_after=10,
            retryable=lambda i, e: "503" in str(e),
        )
    )
    assert out == [(1, "ok")]
    with pytest.raises(ValueError):
        _collect(
            first_stream(
                [bad, _hang(0, ["never"])],
                hedge_after=10,
                retryable=lambda i, e: "503" in str(e),
            )
        )


def test_every_stream_failing_says_why():
    def busy():
        raise RuntimeError("503 UNAVAILABLE")
        yield  # pragma: no cover

    with pytest.raises(HedgeError, match="503"):
        _collect(first_stream([busy, busy], names=["x", "y"], hedge_after=10))

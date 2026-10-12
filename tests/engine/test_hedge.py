"""Hedged requests: the first valid answer wins, slow models never block."""

from __future__ import annotations

import threading
import time

import pytest

from openjarvis.engine.hedge import HedgeError, first_valid


def _slow(value, seconds, started=None, name=""):
    def run():
        if started is not None:
            started.append(name)
        time.sleep(seconds)
        return value

    return run


def _fail(message, started=None, name=""):
    def run():
        if started is not None:
            started.append(name)
        raise RuntimeError(message)

    return run


def test_fast_first_answer_never_starts_the_others():
    started: list[str] = []
    index, value = first_valid(
        [_slow("a", 0.01, started, "a"), _slow("b", 0.01, started, "b")],
        hedge_after=5,
    )
    assert (index, value) == (0, "a")
    assert started == ["a"]


def test_a_refusal_starts_the_next_model_at_once():
    started: list[str] = []
    t0 = time.monotonic()
    index, value = first_valid(
        [_fail("503 busy", started, "a"), _slow("b", 0.01, started, "b")],
        hedge_after=30,
    )
    assert (index, value) == (1, "b")
    assert time.monotonic() - t0 < 2  # no 30 s wait after the refusal


def test_a_slow_model_gets_company_and_the_faster_one_wins():
    t0 = time.monotonic()
    index, value = first_valid(
        [_slow("slow", 3.0), _slow("quick", 0.05)],
        hedge_after=0.2,
    )
    assert (index, value) == (1, "quick")
    assert time.monotonic() - t0 < 1.5


def test_an_answer_that_fails_the_check_is_not_returned():
    def check(text):
        if text == "broken":
            raise ValueError("JSON roto")

    index, value = first_valid(
        [_slow("broken", 0.01), _slow("good", 0.01)], check=check, hedge_after=10
    )
    assert value == "good"
    assert index == 1


def test_all_fail_says_why_each_failed():
    with pytest.raises(HedgeError) as err:
        first_valid([_fail("cuota"), _fail("503")], names=["m1", "m2"])
    assert err.value.errors == ["m1: cuota", "m2: 503"]
    assert not err.value.timed_out


def test_deadline_ends_the_wait_honestly():
    t0 = time.monotonic()
    with pytest.raises(HedgeError) as err:
        first_valid([_slow("x", 2.0)], timeout=0.2)
    assert err.value.timed_out
    assert time.monotonic() - t0 < 1.0


def test_tasks_run_in_parallel_threads():
    seen = set()
    lock = threading.Lock()

    def run():
        with lock:
            seen.add(threading.current_thread().name)
        time.sleep(0.3)
        raise RuntimeError("no")

    with pytest.raises(HedgeError):
        first_valid([run, run, run], hedge_after=0.05)
    assert len(seen) == 3


def test_nothing_to_try():
    with pytest.raises(HedgeError):
        first_valid([])

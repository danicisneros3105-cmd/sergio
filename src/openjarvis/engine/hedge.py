"""Hedged requests: the first valid answer wins, a slow model never blocks.

When Google is busy a model can answer «503 high demand» at once (fine: the
next model is tried) or, worse, accept the request and take minutes. Waiting
for it in order means the owner waits too. Here the best model starts
first; if it has not given a valid answer after ``hedge_after`` seconds the
next one starts *as well*, and so on; a failure starts the next one at once.
The first answer that passes ``check`` wins and the rest are left to finish
in the background (their results are ignored).
"""

from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, Callable, Sequence


class HedgeError(RuntimeError):
    """Every attempt failed (or the deadline passed); ``errors`` says why."""

    def __init__(self, errors: list[str], timed_out: bool = False):
        self.errors = errors
        self.timed_out = timed_out
        head = "Tiempo agotado. " if timed_out else ""
        super().__init__(head + " | ".join(errors[-5:]) if errors else head.strip())


def first_valid(
    tasks: Sequence[Callable[[], Any]],
    *,
    check: Callable[[Any], Any] | None = None,
    names: Sequence[str] | None = None,
    hedge_after: float = 15.0,
    timeout: float = 240.0,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[int, Any]:
    """Run *tasks* hedged; return (index, value) of the first valid result."""
    if not tasks:
        raise HedgeError(["nada que intentar"])
    label = list(names or [str(i) for i in range(len(tasks))])
    pool = ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="hedge")
    running: dict[Future[Any], int] = {}
    errors: list[str] = []
    started = 0
    start = clock()
    last = start

    def launch() -> bool:
        nonlocal started, last
        if started >= len(tasks):
            return False
        running[pool.submit(tasks[started])] = started
        started += 1
        last = clock()
        return True

    try:
        launch()
        while running:
            left = timeout - (clock() - start)
            if left <= 0:
                raise HedgeError(errors, timed_out=True)
            wait_for = left
            if started < len(tasks):
                wait_for = min(left, max(0.01, hedge_after - (clock() - last)))
            done, _ = wait(list(running), timeout=wait_for, return_when=FIRST_COMPLETED)
            for future in done:
                index = running.pop(future)
                try:
                    value = future.result()
                    if check is not None:
                        check(value)
                    return index, value
                except Exception as exc:  # noqa: BLE001 — the next one starts now
                    errors.append(f"{label[index]}: {str(exc)[:140]}")
                    launch()
            if (
                not done
                and started < len(tasks)
                and clock() - last >= hedge_after - 0.005
            ):
                launch()  # the current ones are slow: one more in parallel
        raise HedgeError(errors)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


__all__ = ["HedgeError", "first_valid"]

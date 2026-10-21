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

import asyncio
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, AsyncIterator, Callable, Iterable, Sequence


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


async def first_stream(
    starts: Sequence[Callable[[], Iterable[Any]]],
    *,
    names: Sequence[str] | None = None,
    hedge_after: float | Callable[[int], float] = 6.0,
    first_timeout: float = 150.0,
    retryable: Callable[[int, BaseException], bool] = lambda i, e: True,
    on_first: Callable[[int, float], None] | None = None,
    on_error: Callable[[int, BaseException, float], None] | None = None,
    on_slow: Callable[[int, float], None] | None = None,
) -> AsyncIterator[tuple[int, Any]]:
    """Hedged streaming: yields ``(index, item)`` from the first stream that
    produces an item; the others are dropped.

    Each start runs in its own thread (a blocking SDK stream never freezes
    the server's event loop). If the running stream has given nothing after
    ``hedge_after`` seconds the next one starts as well; a failure starts the
    next one at once, unless ``retryable`` says no sibling can fix it. Once a
    stream has won, its errors are raised as they are. ``on_slow`` hears of
    every stream that started before the winner and was overtaken.
    """
    if not starts:
        raise HedgeError(["nada que intentar"])
    label = list(names or [str(i) for i in range(len(starts))])
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[int, str, Any, float]] = asyncio.Queue()
    stop = threading.Event()
    winner: list[int] = []
    errors: list[str] = []
    running: set[int] = set()
    started_at: dict[int, float] = {}
    started = 0
    last_start = 0.0

    def put(item: tuple[int, str, Any, float]) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:
            pass  # the loop is gone (the client left)

    def worker(index: int) -> None:
        t0 = time.monotonic()
        try:
            for item in starts[index]():
                if stop.is_set() or (winner and winner[0] != index):
                    return
                put((index, "item", item, time.monotonic() - t0))
            put((index, "done", None, time.monotonic() - t0))
        except BaseException as exc:  # noqa: BLE001 — reported to the consumer
            put((index, "error", exc, time.monotonic() - t0))

    def launch() -> bool:
        nonlocal started, last_start
        if started >= len(starts):
            return False
        index = started
        started += 1
        running.add(index)
        last_start = started_at[index] = time.monotonic()
        threading.Thread(
            target=worker, args=(index,), name=f"hedge-stream-{index}", daemon=True
        ).start()
        return True

    def delay(index: int) -> float:
        return hedge_after(index) if callable(hedge_after) else hedge_after

    begin = time.monotonic()
    launch()
    try:
        while True:
            timeout = None
            if not winner:
                left = first_timeout - (time.monotonic() - begin)
                if left <= 0:
                    raise HedgeError(errors, timed_out=True)
                timeout = left
                if started < len(starts):
                    hedge = delay(started - 1) - (time.monotonic() - last_start)
                    timeout = max(0.01, min(timeout, hedge))
            try:
                index, kind, value, seconds = await asyncio.wait_for(
                    queue.get(), timeout
                )
            except asyncio.TimeoutError:
                if not winner and not launch() and not running:
                    raise HedgeError(errors, timed_out=True) from None
                continue
            if winner and index != winner[0]:
                continue
            if kind == "item":
                if not winner:
                    winner.append(index)
                    if on_first is not None:
                        on_first(index, seconds)
                    if on_slow is not None:
                        now = time.monotonic()
                        for other in sorted(running - {index}):
                            if started_at[other] < started_at[index]:
                                on_slow(other, now - started_at[other])
                yield index, value
                continue
            running.discard(index)
            if kind == "done":
                if not winner and on_first is not None:
                    on_first(index, seconds)  # an empty but valid answer
                return
            # kind == "error"
            if winner:
                raise value
            if on_error is not None:
                on_error(index, value, seconds)
            errors.append(f"{label[index]}: {str(value)[:140]}")
            if not retryable(index, value):
                raise value
            if not launch() and not running:
                if len(errors) == 1:
                    raise value
                raise HedgeError(errors)
    finally:
        stop.set()


__all__ = ["HedgeError", "first_stream", "first_valid"]

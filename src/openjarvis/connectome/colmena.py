"""The hive: every part of Sergio does one job, with no orchestrator, and a
supervisor that is always watching.

Like a body or a hive, no organ tells the others what to do. Each organ
declares what it needs and what it gives; when a request arrives, every
organ whose needs are met runs at the same time (a thread each) and leaves
its result on a shared board, so the organs complement each other without a
central plan. The supervisor never does the work: it watches each exchange
and releases dopamine into the fly brain — reward when something worked or
the owner was pleased, punishment when a tool failed, the answer was empty
or broken, or the owner corrected Sergio. That is what makes the brain learn
(:mod:`mushroom`).

The organs of one turn (who they are in the fly):

* ``memoria``      (mushroom body calyx)  — memories that come back;
* ``habilidades``  (lateral horn)          — the prompt library's know-how;
* ``decision``     (mushroom body lobes)   — tools and neurons for this turn;
* ``instinto``     (Nodes' own brains)     — a Node's learned moves.

:func:`status` is what the Cerebro page shows: each organ, how often it
worked, how long it took, and what the supervisor did.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

ORGAN_TIMEOUT_S = 4.0

PRAISE = re.compile(
    r"^\s*(gracias|perfecto|excelente|genial|buen[ií]simo|me encanta|así está bien|asi esta bien|"
    r"eso es|exacto|great|perfect|thanks|love it|nice)\b",
    re.I,
)
CORRECTION = re.compile(
    r"^\s*(no[,.!]|no\s+(es|era|eso|asi|así)|eso no|mal\b|incorrect|te equivoc|al rev[eé]s|"
    r"that'?s wrong|wrong|otra vez no|no entendiste)",
    re.I,
)
BROKEN = re.compile(
    r"(Sorry, an error occurred|No pude responder ahora|Todav[ií]a no hay una IA conectada|"
    r"Traceback \(most recent|Error interno|no pude completar)",
    re.I,
)


@dataclass
class Organ:
    name: str
    fly: str
    job: str
    needs: Tuple[str, ...]
    gives: str
    fn: Callable[[Dict[str, Any]], Any]
    runs: int = 0
    fails: int = 0
    last_ms: float = 0.0
    last: float = 0.0


@dataclass
class Supervisor:
    """Watches every exchange and teaches the brain (dopamine)."""

    rewards: int = 0
    punishments: int = 0
    flagged: List[Dict[str, Any]] = field(default_factory=list)

    def judge(
        self, user_text: str, answer: str, tools: List[Tuple[str, bool]]
    ) -> Dict[str, float]:
        """Dopamine per kind of signal for this exchange (positive: reward)."""
        out: Dict[str, float] = {}
        if not (answer or "").strip() or BROKEN.search(answer or ""):
            out["respuesta"] = -1.0
            self._flag("respuesta vacía o rota", user_text)
        failed = [n for n, ok in tools if not ok]
        if failed:
            out["herramientas"] = -0.6
            self._flag("fallaron: " + ", ".join(sorted(set(failed))[:4]), user_text)
        if not out:
            out["respuesta"] = 0.4  # it answered and nothing broke: a small reward
        return out

    def feedback(self, user_text: str) -> float:
        """What the owner's next words say about the previous answer."""
        if CORRECTION.match(user_text or ""):
            return -1.0
        if PRAISE.match(user_text or ""):
            return 1.0
        return 0.0

    def _flag(self, what: str, text: str) -> None:
        self.flagged.append(
            {"t": round(time.time()), "que": what, "pedido": (text or "")[:80]}
        )
        self.flagged = self.flagged[-30:]


class Colmena:
    def __init__(self) -> None:
        self.organs: Dict[str, Organ] = {}
        self.supervisor = Supervisor()
        self._pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="organo")
        self._lock = threading.Lock()

    def add(self, organ: Organ) -> None:
        self.organs[organ.name] = organ

    def run(
        self, board: Dict[str, Any], timeout: float = ORGAN_TIMEOUT_S
    ) -> Dict[str, Any]:
        """Let every organ whose needs are on the board act, in parallel,
        until nothing new can run. Returns the board."""
        done: set = set()
        deadline = time.time() + timeout
        while True:
            ready = [
                o
                for o in self.organs.values()
                if o.name not in done and all(n in board for n in o.needs)
            ]
            if not ready:
                return board
            futures = {self._pool.submit(self._act, o, dict(board)): o for o in ready}
            wait(futures, timeout=max(0.05, deadline - time.time()))
            for f, o in futures.items():
                done.add(o.name)
                if f.done() and f.exception() is None and f.result() is not None:
                    board[o.gives] = f.result()
            if time.time() >= deadline:
                return board

    def _act(self, organ: Organ, board: Dict[str, Any]) -> Any:
        t = time.perf_counter()
        try:
            return organ.fn(board)
        except Exception:
            with self._lock:
                organ.fails += 1
            raise
        finally:
            with self._lock:
                organ.runs += 1
                organ.last_ms = round((time.perf_counter() - t) * 1000, 1)
                organ.last = time.time()

    def status(self) -> Dict[str, Any]:
        return {
            "organos": [
                {
                    "nombre": o.name,
                    "mosca": o.fly,
                    "trabajo": o.job,
                    "necesita": list(o.needs),
                    "da": o.gives,
                    "veces": o.runs,
                    "fallos": o.fails,
                    "ms": o.last_ms,
                }
                for o in self.organs.values()
            ],
            "supervisor": {
                "recompensas": self.supervisor.rewards,
                "castigos": self.supervisor.punishments,
                "avisos": self.supervisor.flagged[-8:],
            },
        }


_HIVE: Optional[Colmena] = None
_HIVE_LOCK = threading.Lock()


def hive() -> Colmena:
    global _HIVE
    with _HIVE_LOCK:
        if _HIVE is None:
            _HIVE = Colmena()
        return _HIVE


def status() -> Dict[str, Any]:
    return hive().status()


__all__ = ["Colmena", "Organ", "Supervisor", "hive", "status"]

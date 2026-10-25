"""The core: one fly brain wiring that every part of Sergio plugs into.

Think of it as the motherboard. The wiring (:mod:`flywire`) and the
receptors (:mod:`receptors`) are loaded once; every part that has to learn
gets its own mushroom body on that same wiring:

* ``sergio`` — the main brain: which tools, neurons and helpers a request
  needs (and whether Terry should rewrite it);
* ``node:<key>`` — each Node's own brain, born with its temperament and
  trained by its own work (so the four really diverge);
* ``especialista:<key>`` — the film and creator specialists, trained on
  their technique cards.

:meth:`Core.sleep` is the night: every brain replays its day into its slow
memory (``consolidate``) and is saved. It runs by itself at most every 12 h
(:meth:`maybe_sleep`, called after each exchange) or with ``sergio cerebro
dormir``.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openjarvis.connectome import flywire
from openjarvis.connectome.mushroom import SPARSITY, MushroomBody
from openjarvis.connectome.receptors import Receptors

SLEEP_EVERY_S = 12 * 3600
SAVE_EVERY_S = 60
RETRY_BIRTH_S = 3600  # born with half its senses (no internet): try again in an hour
# a stronger APL inhibition for brains that tell many fine choices apart
# (measured: the specialists generalise better at 2 % than at 5 %)
SPARSITY_BY_PREFIX = {"especialista:": 0.02}


class Core:
    def __init__(
        self,
        folder: Path,
        *,
        embedder: Any = None,
        wiring: Optional[flywire.Wiring] = None,
    ) -> None:
        self.folder = Path(folder)
        self.wiring = wiring or flywire.load(self.folder / "flywire")
        self.receptors = Receptors(self.folder, self.wiring.n_pn, embedder=embedder)
        self.brains: Dict[str, MushroomBody] = {}
        self._lock = threading.RLock()
        self._saved = 0.0
        self._sleeping = False
        self.human_night: Dict[str, Any] = {}

    def brain(self, name: str = "sergio") -> MushroomBody:
        with self._lock:
            if name not in self.brains:
                self.brains[name] = MushroomBody(
                    self.wiring,
                    self.folder / "cerebros",
                    name.replace(":", "_"),
                    receptors=self.receptors,
                    adapts=name == "sergio",
                    sparsity=next(
                        (
                            v
                            for p, v in SPARSITY_BY_PREFIX.items()
                            if name.startswith(p)
                        ),
                        SPARSITY,
                    ),
                )
                self.brains[name].name = name
            return self.brains[name]

    def born(
        self,
        name: str,
        key: str,
        texts: List[str],
        train: Callable[[MushroomBody], Optional[Dict[str, Any]]],
    ) -> MushroomBody:
        """A brain that is born trained (a Node's temperament, a specialist's
        craft). Trained once for the senses it has, and again from zero when
        they change (words alone -> meaning): old codes would mean nothing."""
        with self._lock:
            mb = self.brain(name)
            birth = mb.meta.get(key) or {}
            space = self.receptors.space
            if birth and birth.get("space", "") == space:
                if not birth.get("partial") or time.time() < birth.get("retry", 0):
                    return mb
            if birth:
                mb.reset()
            missing = self.receptors.warm(texts) if space else 0
            info = train(mb) or {}
            mb.meta[key] = {
                **info,
                "space": space,
                "partial": bool(missing),
                "retry": round(time.time() + RETRY_BIRTH_S),
            }
            mb.save()
            return mb

    def save(self, force: bool = False) -> None:
        if not force and time.time() - self._saved < SAVE_EVERY_S:
            return
        with self._lock:
            for b in self.brains.values():
                b.save()
            self.receptors.save()
            self._saved = time.time()

    def sleep(self, epochs: int = 3) -> Dict[str, Any]:
        """Consolidate every brain that has episodes (the night)."""
        report: Dict[str, Any] = {}
        with self._lock:
            names = list(self.brains)
            names += [n for n in self._saved_names() if n not in names]
        for name in names:
            b = self.brain(name)
            b.decay()
            if b.replay:
                report[name] = b.consolidate(epochs)
        meta = self.folder / "cerebros" / "dormir.txt"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(str(time.time()), "utf-8")
        self.save(force=True)
        self.human_night = self._human_sleep()
        return report

    def _human_sleep(self) -> Dict[str, Any]:
        """The same night for the human brain (connectome/cortex.py): replay
        into concepts and synaptic homeostasis."""
        if self.folder.name != "connectome":
            return {}
        try:
            from openjarvis.connectome import cortex

            if not cortex.enabled():
                return {}
            return cortex.get_human(self.folder.parent).sleep()
        except Exception:  # noqa: BLE001 — a bad night never breaks the day
            return {}

    def _saved_names(self) -> List[str]:
        return [
            p.stem.replace("_", ":", 1)
            for p in (self.folder / "cerebros").glob("*.npz")
            if not p.name.endswith(".tmp.npz")
        ]

    def last_sleep(self) -> float:
        try:
            return float((self.folder / "cerebros" / "dormir.txt").read_text("utf-8"))
        except (OSError, ValueError):
            return 0.0

    def maybe_sleep(self) -> None:
        """Sleep in the background when the last night was long ago."""
        if self._sleeping or time.time() - self.last_sleep() < SLEEP_EVERY_S:
            return
        self._sleeping = True

        def night() -> None:
            try:
                self.sleep()
            finally:
                self._sleeping = False

        threading.Thread(target=night, name="cerebro-duerme", daemon=True).start()

    def info(self) -> Dict[str, Any]:
        w = self.wiring
        return {
            **{k: v for k, v in w.info.items() if k != "sha256"},
            "verified": bool(w.info.get("sha256")),
            "receptors": self.receptors.space or "palabras",
            "brains": sorted(
                set(self.brains)
                | {
                    p.stem.replace("_", ":", 1)
                    for p in (self.folder / "cerebros").glob("*.npz")
                    if not p.name.endswith(".tmp.npz")
                }
            ),
            "last_sleep": self.last_sleep(),
        }


_CORES: Dict[str, Core] = {}
_LOCK = threading.Lock()


def get_core(home: Optional[Path] = None) -> Core:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    return core_at(Path(home) / "connectome")


def core_at(folder: Path) -> Core:
    """The core that lives in *folder* (one per folder, loaded once)."""
    folder = Path(folder)
    with _LOCK:
        if str(folder) not in _CORES:
            _CORES[str(folder)] = Core(folder)
        return _CORES[str(folder)]


def reset_cores() -> None:
    """Forget the loaded cores (tests and after downloading the real wiring)."""
    with _LOCK:
        _CORES.clear()


__all__ = ["Core", "core_at", "get_core", "reset_cores"]

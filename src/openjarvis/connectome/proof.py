"""The proof that the fly core really learns, measured, not described.

:func:`proof` gathers what the Cerebro page draws:

* **wiring** — which connectome is plugged in (the measured FlyWire one once
  downloaded, with its SHA-256 checked, or the stand-in with the published
  counts) and how many neurons and synapses it has;
* **live** — a newborn brain on that same wiring learns, in front of you,
  three things it never knew, and is tested on sentences it never saw:
  how many measured synapses changed, how many new ones grew, and how its
  choice moved from chance to right (then a night of sleep moves it into
  the slow memory);
* **specialists** — the film and creator brains' learning curves on
  held-out requests, against chance;
* **nodes** — the four Node brains: what each one's instinct says to the
  same request, and how far apart their learning drifted;
* **brains** — every brain in use: synapses changed, grown and pruned,
  fast and slow memory, nights slept and each night's accuracy before and
  after;
* **hive** — the organs, how often each worked and the supervisor's
  rewards and punishments;
* **humano** — the human brain that decides every turn (connectome/cortex.py):
  a newborn one learns an owner's taste from what he says next and is tested
  on requests it never saw; **humano_vivo** is the owner's own, as it is now.

Curves and the live run cost about a second; they are cached for ten minutes.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

CACHE_S = 600
SAME_REQUEST = "quiero lanzar una marca de café"

LIVE_LESSONS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("musica", "pon música para concentrarme", ("ponme música tranquila", "quiero escuchar música")),
    ("clima", "va a llover hoy en Cuenca", ("lloverá mañana en Quito", "va a llover esta tarde")),
    ("agenda", "agenda la cita con el dentista", ("agenda una reunión el jueves", "pon una cita con el médico")),
)  # fmt: skip

_cache: Dict[str, Any] = {}
_lock = threading.Lock()


def _core(core: Any = None) -> Any:
    if core is not None:
        return core
    from openjarvis.connectome.core import get_core

    return get_core()


def live(core: Any = None, rounds: int = 3) -> Dict[str, Any]:
    """A newborn brain learns three lessons; each round is measured."""
    from openjarvis.connectome.mushroom import MushroomBody

    c = _core(core)
    mb = MushroomBody(c.wiring, None, "prueba-en-vivo", receptors=c.receptors)
    actions = [a for a, _t, _h in LIVE_LESSONS]

    def test() -> Dict[str, Any]:
        rows, hits = [], 0
        for action, _teach, held in LIVE_LESSONS:
            for text in held:
                s = mb.scores(text, actions)
                pick = max(actions, key=lambda a: s[a])
                tied = len({round(v, 6) for v in s.values()}) == 1
                ok = pick == action and not tied
                hits += ok
                rows.append(
                    {
                        "texto": text,
                        "quiere": action,
                        "elige": None if tied else pick,
                        "ok": ok,
                    }
                )
        st = mb.stats()["synapses"]
        return {"acierto": round(hits / len(rows), 3), "cambiadas": st["cambiadas"],
                "nuevas": st["nuevas"], "pruebas": rows}  # fmt: skip

    steps = [{"ronda": 0, **test()}]
    for r in range(1, rounds + 1):
        for action, teach, _held in LIVE_LESSONS:
            mb.learn(teach, action, 1.0)
        steps.append({"ronda": r, **test()})
    slow_before = float(abs(mb.slow).sum())
    night = mb.consolidate(epochs=2)
    return {
        "lecciones": [{"accion": a, "enseña": t} for a, t, _h in LIVE_LESSONS],
        "rondas": steps,
        "dormir": {
            **night,
            "memoria_lenta_antes": round(slow_before, 2),
            "memoria_lenta_despues": round(float(abs(mb.slow).sum()), 2),
        },
        "azar": round(1 / len(actions), 3),
    }


def nodes(core: Any = None, request: str = SAME_REQUEST) -> Dict[str, Any]:
    from openjarvis.nodes import temperament as T

    c = _core(core)
    instincts = {
        k: [{"movida": m, "como": how, "fuerza": v} for m, how, v in T.instinct(k, request, c)]
        for k in T.TEMPERAMENTS
    }  # fmt: skip
    return {"pedido": request, "instintos": instincts, "divergencia": T.divergence(c)}


def specialists(core: Any = None, epochs: int = 4) -> Dict[str, Any]:
    from openjarvis.video_essay import specialists as S

    c = _core(core)
    out: Dict[str, Any] = {}
    for kind, sample in (
        ("cine", "un corto de ciencia ficción donde se acaba el tiempo"),
        ("creadores", "un video para YouTube sobre mi viaje"),
    ):
        mb = S.brain_for(kind, c)
        out[kind] = {
            "curva": S.learning_curve(kind, c, epochs=epochs),
            "tecnicas": len(S.SPECIALISTS[kind]),
            "ejemplo": {
                "pedido": sample,
                "consejo": [
                    {"tecnica": k, "escuela": s, "fuerza": v}
                    for k, s, _h, v in S.advise(kind, sample, c)
                ],
            },  # fmt: skip
            "aprendido_de_videos": int(mb.meta.get("rewards", 0))
            + int(mb.meta.get("punishments", 0)),
        }
    return out


def brains(core: Any = None) -> List[Dict[str, Any]]:
    c = _core(core)
    rows = []
    for name in c.info()["brains"]:
        st = c.brain(name).stats()
        rows.append(
            {
                "nombre": name,
                "sinapsis": st["synapses"],
                "memoria": st["memory"],
                "episodios": st["episodes"],
                "recompensas": st["rewards"],
                "castigos": st["punishments"],
                "noches": st["sleeps"],
                "historia": st["history"][-10:],
            }
        )
    return rows


def proof(core: Any = None, *, fresh: bool = False) -> Dict[str, Any]:
    from openjarvis.connectome.colmena import status as hive_status

    c = _core(core)
    key = str(getattr(c, "folder", ""))
    with _lock:
        hit = _cache.get(key)
        if hit and not fresh and time.time() - hit["t"] < CACHE_S:
            heavy = hit["heavy"]
        else:
            heavy = {"live": live(c), "specialists": specialists(c), "humano": human()}
            _cache[key] = {"t": time.time(), "heavy": heavy}
    info = c.info()
    w = c.wiring
    return {
        "wiring": {
            "real": bool(w.info.get("real")),
            "fuente": w.info.get("source"),
            "licencia": w.info.get("license", ""),
            "verificado": info.get("verified", False),
            "neuronas": {
                "proyeccion": w.n_pn,
                "kenyon": w.n_kc,
                "salida": w.n_mbon,
                "dopamina": int(w.info.get("n_dan") or 0),
            },
            "sinapsis_medidas": int(w.mask0.sum()) + int((w.claws >= 0).sum()),
            "total_conectoma": {
                "neuronas": w.info.get("neurons_total"),
                "conexiones": w.info.get("edges_total"),
            },
        },  # fmt: skip
        "sentidos": info.get("receptors") or "palabras",
        "ultima_noche": info.get("last_sleep") or 0,
        **heavy,
        "nodes": nodes(c),
        "brains": brains(c),
        "hive": hive_status(),
        "humano_vivo": human_now(),
    }


def human() -> Dict[str, Any]:
    """A newborn human brain learns one owner's taste (connectome/cortex.py)."""
    from openjarvis.connectome.cortex import prove

    return prove()


def human_now() -> Dict[str, Any]:
    """The owner's human brain as it is now: choices, dopamine, concepts."""
    try:
        from openjarvis.connectome import cortex

        return cortex.get_human().stats() if cortex.enabled() else {}
    except Exception:  # noqa: BLE001
        return {}


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def download(progress: Optional[Any] = None) -> Dict[str, Any]:
    """The measured connectome and the on-device meaning model, verified."""
    from openjarvis.connectome import flywire, receptors
    from openjarvis.connectome.core import get_core, reset_cores

    say = progress or (lambda _m: None)
    folder = get_core().folder
    out: Dict[str, Any] = {}
    try:
        w = flywire.download(folder / "flywire", progress=say)
        out["flywire"] = {"ok": True, "kenyon": w.n_kc, "salida": w.n_mbon}
    except Exception as exc:  # noqa: BLE001 — the stand-in keeps working
        out["flywire"] = {"ok": False, "error": str(exc)[:200]}
    try:
        say("descargando el modelo de significado (118 MB)")
        receptors.download_local()
        out["significado"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001 — Gemini or words alone
        out["significado"] = {"ok": False, "error": str(exc)[:200]}
    reset_cores()
    clear_cache()
    return out


__all__ = [
    "brains",
    "clear_cache",
    "download",
    "human",
    "human_now",
    "live",
    "nodes",
    "proof",
    "specialists",
]

"""Stability: Sergio checks itself, repairs what it can and restarts when stuck.

The owner (27 Oct 2026): «software para estabilizar todo, que no haya fallos
y funcione en cualquier dispositivo». Three layers:

* **Vigía** (:func:`start_watchdog`): a thread outside the server's event
  loop asks the server's own ``/health`` every 30 s. Three failures in a row
  mean the loop is stuck (a hang no exception can catch): the process exits
  and the system service (``Restart=always``) starts it clean in seconds.
* **Chequeo** (:func:`checks`): disk, memory, ffmpeg, the folder Sergio
  writes in, which AI companies have a key, and the video jobs — each
  «ok», «aviso» or «falla» with what to do, in plain words
  (``GET /v1/estabilidad``, ``sergio estabilidad``).
* **Reparación** (:func:`repair`): every day, and on demand, it frees disk
  (large intermediates of finished video jobs, old temporary clips, logs
  over 50 MB) and puts secret files back to owner-only.

Any device: the web app is a PWA with compatibility shims
(``frontend/src/lib/compat.ts``) and reloads itself when an update changes
its files; that part lives in the frontend.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROVIDERS = (
    ("Google (Gemini)", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
    ("OpenAI", ("OPENAI_API_KEY",)),
    ("Anthropic", ("ANTHROPIC_API_KEY",)),
    ("DeepSeek", ("DEEPSEEK_API_KEY",)),
    ("OpenRouter (todos los demás)", ("OPENROUTER_API_KEY",)),
    ("ElevenLabs (voz)", ("ELEVENLABS_API_KEY",)),
)


def _home() -> Path:
    from openjarvis.core.config import get_config_dir

    return Path(get_config_dir())


def _check(name: str, state: str, detail: str, fix: str = "") -> Dict[str, str]:
    return {"nombre": name, "estado": state, "detalle": detail, "arreglo": fix}


def checks(home: Optional[Path] = None) -> List[Dict[str, str]]:
    home = home or _home()
    out: List[Dict[str, str]] = []
    free = shutil.disk_usage(home if home.exists() else Path.home()).free / 2**30
    out.append(_check("Disco", "ok" if free > 10 else "aviso" if free > 3 else "falla", f"{free:.1f} GB libres",
                      "" if free > 10 else "Reparar libera los archivos grandes de videos terminados."))  # fmt: skip
    try:
        import psutil

        mem = psutil.virtual_memory()
        avail = mem.available / 2**30
        out.append(_check("Memoria", "ok" if avail > 2 else "aviso", f"{avail:.1f} GB disponibles",
                          "" if avail > 2 else "Cierre programas pesados mientras Sergio hace videos."))  # fmt: skip
    except Exception:  # noqa: BLE001
        pass
    try:
        from openjarvis.tools.video_create import ffmpeg_exe

        ff = ffmpeg_exe()
    except Exception:  # noqa: BLE001
        ff = None
    out.append(_check("ffmpeg (video)", "ok" if ff else "falla", ff or "no encontrado",
                      "" if ff else "Ejecute la actualización: instala ffmpeg."))  # fmt: skip
    probe = home / ".escritura"
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok")
        probe.unlink()
        out.append(_check("Carpeta de Sergio", "ok", str(home)))
    except OSError as exc:
        out.append(
            _check(
                "Carpeta de Sergio",
                "falla",
                f"no se puede escribir: {exc}",
                "Revise permisos del disco.",
            )
        )
    have = [
        name
        for name, envs in PROVIDERS
        if any(os.environ.get(e, "").strip() for e in envs)
    ]
    ai = [n for n in have if "voz" not in n]
    out.append(_check("Modelos de IA", "ok" if len(ai) >= 2 else "aviso" if ai else "falla",
                      ", ".join(have) or "ninguna clave",
                      "" if len(ai) >= 2 else "Con dos empresas, si una falla, la otra responde."))  # fmt: skip
    try:
        from openjarvis.video_essay import job as jobs

        stuck = [j.id for j in jobs.all_jobs() if j.state().get("status") == "en curso"
                 and time.time() - float(j.state().get("updated") or time.time()) > 3600]  # fmt: skip
        out.append(_check("Videos", "ok" if not stuck else "aviso",
                          f"{len(stuck)} parados más de 1 h" if stuck else "sin trabajos parados",
                          "Se retoman solos (4 intentos)." if stuck else ""))  # fmt: skip
    except Exception:  # noqa: BLE001
        pass
    return out


def summary(items: List[Dict[str, str]]) -> str:
    bad = [c for c in items if c["estado"] == "falla"]
    warn = [c for c in items if c["estado"] == "aviso"]
    if bad:
        return "Hay que arreglar: " + ", ".join(c["nombre"] for c in bad) + "."
    if warn:
        return "Funciona; para mejorar: " + ", ".join(c["nombre"] for c in warn) + "."
    return "Todo en orden."


BIG = 200 * 2**20  # intermediates over this size, once the job is done


def repair(home: Optional[Path] = None, now: Optional[float] = None) -> Dict[str, Any]:
    """Free disk and tighten permissions; never touches a video still running
    or the finished videos themselves."""
    home = home or _home()
    now = time.time() if now is None else now
    freed = 0
    removed: List[str] = []
    jobs_root = home / "video_jobs"
    if jobs_root.exists():
        import json

        for st in jobs_root.glob("*/state.json"):
            try:
                status = json.loads(st.read_text()).get("status")
            except Exception:  # noqa: BLE001
                continue
            if status not in ("listo", "error", "cancelado"):
                continue
            folder = st.parent
            for f in list(folder.glob("final*.mp4")) + list(folder.glob("*.wav")):
                if f.stat().st_size > BIG or (
                    f.suffix == ".wav" and now - f.stat().st_mtime > 7 * 86400
                ):
                    freed += f.stat().st_size
                    removed.append(str(f))
                    f.unlink()
            clips = folder / "imagenes" / "clips"
            if clips.exists() and now - clips.stat().st_mtime > 7 * 86400:
                size = sum(p.stat().st_size for p in clips.rglob("*") if p.is_file())
                shutil.rmtree(clips, ignore_errors=True)
                freed += size
                removed.append(str(clips))
    for log in list(home.glob("*.log")) + list((home / "logs").glob("*.log")):
        if log.stat().st_size > 50 * 2**20:
            keep = log.read_bytes()[-5 * 2**20 :]
            freed += log.stat().st_size - len(keep)
            log.write_bytes(keep)
            removed.append(f"{log} (recortado)")
    try:
        from openjarvis.security.permisos import tighten

        tighten()
    except Exception:  # noqa: BLE001
        pass
    return {"liberado_mb": round(freed / 2**20, 1), "quitado": removed[:50]}


def start_watchdog(
    url: str,
    *,
    every: float = 30.0,
    strikes: int = 3,
    get: Optional[Callable[[str], bool]] = None,
    exit: Callable[[int], None] = os._exit,
) -> threading.Thread:
    """Exit the process when its own /health stops answering (the service
    starts it again clean)."""

    def healthy(u: str) -> bool:
        import httpx

        try:
            return httpx.get(u, timeout=10).status_code < 500
        except Exception:  # noqa: BLE001
            return False

    probe = get or healthy

    def run() -> None:
        import logging

        log = logging.getLogger(__name__)
        time.sleep(every * 2)  # let the server finish starting
        bad = 0
        while True:
            bad = 0 if probe(url) else bad + 1
            if bad >= strikes:
                log.error(
                    "Sergio no responde a su propio /health %d veces: se reinicia",
                    strikes,
                )
                exit(1)
                return
            time.sleep(every)

    t = threading.Thread(target=run, name="sergio-vigia", daemon=True)
    t.start()
    return t


__all__ = ["PROVIDERS", "checks", "repair", "start_watchdog", "summary"]

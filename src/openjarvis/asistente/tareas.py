"""Work that keeps going in the background (owner, 4 Nov 2026: «mejora la
ejecución en segundo plano»).

Before, ``en_segundo_plano`` read a site while the chat waited. Now a check can
be **left running**: the chat answers at once («lo reviso y le aviso»), the work
goes on in its own thread, survives a restart, shows in «En marcha» with its
stop button, and when it finishes, or when a watched page changes, Sergio puts
a notice on the computer's screen (``desktop_action system notify``) if the
desktop app is running.

Two kinds, both built on the background browser (``navegador.check``):

* ``revisar`` — read a site once, later.
* ``vigilar`` — read it every N minutes and say when it changes (or when a
  word appears). Stops by itself after ``veces`` checks (default a day's worth).

A failure from the site is retried once after a short wait; a second failure
is told plainly. Nothing here sends, pays, books, publishes or deletes: the
browser stops before those steps, as always.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

KINDS = ("revisar", "vigilar")
ACTIVE = ("en_cola", "en_curso", "vigilando")
MIN_EVERY_MIN = 5
MAX_EVERY_MIN = 24 * 60
RETRY_WAIT_S = 20.0
KEEP = 60  # finished tasks kept on disk
_LOCK = threading.RLock()
_STOP: Dict[str, threading.Event] = {}
_loop_started = False


def _dir(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = Path(get_config_dir())
    path = Path(home) / "segundo_plano"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(home: Optional[Path]) -> Path:
    return _dir(home) / "tareas.json"


def load(home: Optional[Path] = None) -> List[Dict[str, Any]]:
    try:
        data = json.loads(_path(home).read_text("utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(items: List[Dict[str, Any]], home: Optional[Path]) -> None:
    done = [t for t in items if t.get("estado") not in ACTIVE]
    keep = [t for t in items if t.get("estado") in ACTIVE] + done[-KEEP:]
    path = _path(home)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def get(task_id: str, home: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    return next((t for t in load(home) if t.get("id") == task_id), None)


def _update(
    task_id: str, home: Optional[Path], **changes: Any
) -> Optional[Dict[str, Any]]:
    with _LOCK:
        items = load(home)
        for t in items:
            if t.get("id") == task_id:
                t.update(changes)
                _save(items, home)
                return t
    return None


def fingerprint(text: str) -> str:
    """The page's text without what changes on every visit (times, counters
    of seconds), so a change means something changed."""
    clean = re.sub(r"\b\d{1,2}:\d{2}(:\d{2})?\b", "", text or "")
    clean = re.sub(r"\s+", " ", clean).strip().lower()
    return hashlib.sha256(clean.encode()).hexdigest()[:24]


def what_changed(old: str, new: str, limit: int = 6) -> List[str]:
    """Lines that are new on the page (in order), for the notice."""
    seen = {line.strip() for line in (old or "").splitlines() if line.strip()}
    out = []
    for line in (new or "").splitlines():
        line = line.strip()
        if line and line not in seen and len(line) > 2:
            out.append(line[:160])
            if len(out) >= limit:
                break
    return out


def notice(text: str) -> bool:
    """A notice on the computer's screen through the desktop app (no error
    when it is not running: the result is still in «En marcha» and the chat)."""
    try:
        import httpx

        from openjarvis.tools.desktop_tools import _endpoint

        url, headers = _endpoint()
        if not headers["Authorization"].removeprefix("Bearer "):
            return False
        r = httpx.post(
            url + "/act",
            headers=headers,
            json={"action": "system", "target": "notify", "value": text[:240]},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:  # noqa: BLE001 — a notice is a courtesy
        return False


def start(
    kind: str,
    sitio: str,
    *,
    pasos: Optional[List[Dict[str, Any]]] = None,
    cada_min: float = 30,
    buscar: str = "",
    veces: int = 0,
    home: Optional[Path] = None,
    check: Optional[Callable[..., Dict[str, Any]]] = None,
    tell: Optional[Callable[[str], Any]] = None,
    sleep: Callable[[float], None] = time.sleep,
    thread: bool = True,
) -> Dict[str, Any]:
    """Leave a check running; returns the task at once."""
    if kind not in KINDS:
        raise ValueError(f"Tipo desconocido: {kind}. Use revisar o vigilar.")
    sitio = str(sitio or "").strip()
    if not sitio:
        raise ValueError("Diga qué sitio (un nombre guardado o una dirección https).")
    every = max(MIN_EVERY_MIN, min(MAX_EVERY_MIN, float(cada_min or 30)))
    task = {
        "id": secrets.token_hex(5),
        "tipo": kind,
        "sitio": sitio,
        "pasos": pasos if isinstance(pasos, list) else [],
        "cada_min": every if kind == "vigilar" else 0,
        "buscar": str(buscar or "").strip()[:80],
        "veces": int(veces or (round(24 * 60 / every) if kind == "vigilar" else 1)),
        "hechas": 0,
        "estado": "en_cola",
        "creada": time.time(),
        "proxima": time.time(),
        "resultado": "",
        "cambios": [],
        "huella": "",
        "texto": "",
        "error": "",
    }
    with _LOCK:
        items = load(home)
        items.append(task)
        _save(items, home)
    if thread:
        threading.Thread(
            target=run_once, args=(task["id"],),
            kwargs={"home": home, "check": check, "tell": tell, "sleep": sleep},
            name=f"sergio-tarea-{task['id']}", daemon=True,
        ).start()  # fmt: skip
    return task


def run_once(
    task_id: str,
    *,
    home: Optional[Path] = None,
    check: Optional[Callable[..., Dict[str, Any]]] = None,
    tell: Optional[Callable[[str], Any]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Optional[Dict[str, Any]]:
    """One turn of a task: read the site (one retry), record, tell."""
    task = get(task_id, home)
    if not task or task.get("estado") not in ACTIVE:
        return task
    stop = _STOP.setdefault(task_id, threading.Event())
    if stop.is_set():
        return _update(task_id, home, estado="cancelado")
    if check is None:
        from openjarvis.asistente.navegador import check as browser_check

        check = browser_check
    tell = tell or notice
    _update(task_id, home, estado="en_curso")
    data: Dict[str, Any] = {}
    error = ""
    for attempt in (0, 1):
        try:
            data = check(task["sitio"], task.get("pasos") or [])
            error = ""
            break
        except Exception as exc:  # noqa: BLE001 — the site, not Sergio
            error = str(exc)[:200] or exc.__class__.__name__
            if attempt == 0 and not stop.is_set():
                sleep(RETRY_WAIT_S)
    if stop.is_set():
        return _update(task_id, home, estado="cancelado")
    done = int(task.get("hechas") or 0) + 1
    if error:
        task = _update(task_id, home, estado="error", error=error, hechas=done)
        tell(f"No pude revisar {task['sitio'] if task else ''}: {error}")
        return task
    state = str(data.get("estado") or "")
    text = str(data.get("texto") or "")
    if state == "necesita_sesion":
        task = _update(
            task_id, home, estado="error", hechas=done,
            error="Hace falta iniciar sesión una vez en ese sitio (iniciar_sesion).",
        )  # fmt: skip
        tell(f"{task['sitio'] if task else 'El sitio'} pide iniciar sesión una vez.")
        return task
    if task["tipo"] == "revisar":
        task = _update(
            task_id, home, estado="listo", hechas=done, texto=text[:6000],
            resultado=f"Revisado {task['sitio']}: {len(text)} caracteres leídos.",
        )  # fmt: skip
        tell(f"Listo: revisé {task['sitio'] if task else ''}. Pregúnteme qué encontré.")
        return task
    # vigilar
    mark = fingerprint(text)
    found_word = bool(task.get("buscar")) and task["buscar"].lower() in text.lower()
    changes = list(task.get("cambios") or [])
    first = not task.get("huella")
    changed = not first and mark != task.get("huella")
    note = ""
    if changed or (found_word and not any(c.get("palabra") for c in changes)):
        lines = what_changed(task.get("texto") or "", text)
        changes.append({
            "cuando": time.time(), "lineas": lines,
            "palabra": task["buscar"] if found_word else "",
        })  # fmt: skip
        note = (
            f"Apareció «{task['buscar']}» en {task['sitio']}."
            if found_word
            else f"Cambió {task['sitio']}: "
            + ("; ".join(lines[:2]) or "algo en la página")
        )
        tell(note)
    finished = done >= int(task.get("veces") or 1)
    return _update(
        task_id, home,
        estado="listo" if finished else "vigilando",
        hechas=done, huella=mark, texto=text[:6000], cambios=changes[-20:],
        proxima=time.time() + float(task.get("cada_min") or 30) * 60,
        resultado=note or (task.get("resultado") or "Sin cambios por ahora."),
    )  # fmt: skip


def cancel(task_id: str, home: Optional[Path] = None) -> bool:
    _STOP.setdefault(task_id, threading.Event()).set()
    task = get(task_id, home)
    if not task or task.get("estado") not in ACTIVE:
        return False
    _update(task_id, home, estado="cancelado")
    return True


def tick(
    home: Optional[Path] = None,
    now: Optional[float] = None,
    run: Optional[Callable[[str], Any]] = None,
) -> List[str]:
    """Run the watches that are due (and any task a restart left in the
    queue); returns their ids."""
    now = time.time() if now is None else now
    run = run or (lambda tid: run_once(tid, home=home))
    due = []
    for t in load(home):
        late = (
            t.get("estado") in ("en_cola", "en_curso")
            and now - float(t.get("creada") or 0) > 120
        )
        watching = (
            t.get("estado") == "vigilando" and float(t.get("proxima") or 0) <= now
        )
        if late or watching:
            due.append(t["id"])
    for tid in due:
        try:
            run(tid)
        except Exception:  # noqa: BLE001 — one task never stops the others
            logger.debug("background task %s failed", tid, exc_info=True)
    return due


def start_loop(interval: float = 60.0) -> None:
    """Check the watches once a minute (idempotent)."""
    global _loop_started
    if _loop_started:
        return
    _loop_started = True

    def loop() -> None:
        while True:
            time.sleep(interval)
            try:
                if any(t.get("estado") in ACTIVE for t in load()):
                    tick()
            except Exception:  # noqa: BLE001
                logger.debug("background loop", exc_info=True)

    threading.Thread(target=loop, name="sergio-segundo-plano", daemon=True).start()


def plain(task: Dict[str, Any]) -> Dict[str, Any]:
    """What the chat and «En marcha» show (no page text unless finished)."""
    out = {k: task.get(k) for k in ("id", "tipo", "sitio", "estado", "hechas", "veces",
                                    "cada_min", "buscar", "resultado", "error")}  # fmt: skip
    out["cambios"] = (task.get("cambios") or [])[-3:]
    if task.get("estado") == "listo" and task.get("tipo") == "revisar":
        out["texto"] = (task.get("texto") or "")[:4000]
    return out


__all__ = [
    "KINDS",
    "cancel",
    "fingerprint",
    "get",
    "load",
    "notice",
    "plain",
    "run_once",
    "start",
    "start_loop",
    "tick",
    "what_changed",
]

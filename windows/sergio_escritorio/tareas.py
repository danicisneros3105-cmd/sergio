"""Multitasking: complex tasks in the foreground and the background at once.

«En segundo plano, busca los 3 mejores portátiles para Blender y hazme una
tabla» starts a task that does not take the screen: the user keeps working
and Sergio keeps talking. Several tasks run at the same time, each one a
Live Activity in the notch (the «dúo» shows two at a glance).

How a task runs:

1. The server plans it (tasks_routes): short steps, each marked ``fondo``
   (no screen: web, files, Python, the Ubuntu terminal) or ``pantalla``.
   Tools the planner invents are removed before anything runs.
2. Background steps of different tasks run in parallel; a ``pantalla`` step
   waits for the screen (one task at a time drives the mouse and keyboard,
   like a person would).
3. Each step must end with ``TERMINADO:``, ``FALTA:`` or ``NO POSIBLE:``; a
   step that is not done gets one more try with what is missing.
4. Steps that send, pay, publish, install or delete wait for the owner's
   face (the checkpoint), and the end of a task is checked once more
   against the request before Sergio says it is done.
"""

from __future__ import annotations

import itertools
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from sergio_escritorio.activities import Activities

STEP_RULES = {
    "fondo": (
        "Este paso va EN SEGUNDO PLANO: el usuario está usando la pantalla. NO uses "
        "desktop_action ni screen_read. Usa solo herramientas sin pantalla: web_search, "
        "http_request, python_run, terminal_run, archivos, video_edit, blender_create, globe_view."
    ),
    "pantalla": (
        "Este paso usa la pantalla del usuario: hazlo visible y verifica cada acción con screen_read."
    ),
}
END_RULE = (
    "No inventes datos: si algo no lo verificaste con una herramienta, dilo. Termina con "
    "exactamente una línea: 'TERMINADO: <qué hiciste y dónde quedó>', 'FALTA: <qué falta>' "
    "o 'NO POSIBLE: <por qué>'."
)
BACKGROUND = re.compile(
    r"^\s*(?:sergio,?\s*)?(?:en segundo plano|de fondo|en el fondo|mientras tanto|sin usar (?:la|mi) pantalla|"
    r"in the background|em segundo plano|en arri[eè]re-plan|im hintergrund|in background)\s*[,:]?\s*(?P<task>.+)$",
    re.I,
)
TOGETHER = re.compile(r"^\s*(?:haz|has|realiza)\s+(?:a la vez|al mismo tiempo|en paralelo)\s*[,:]?\s*(?P<tasks>.+)$", re.I)
WHAT_DOING = re.compile(
    r"\b(qu[eé] (est[aá]s|estas) haciendo|qu[eé] tareas (tienes|hay)|c[oó]mo van (las|mis) tareas|"
    r"qu[eé] tienes en marcha|what are you doing)\b",
    re.I,
)
CANCEL = re.compile(r"\b(cancela|det[eé]n|para|aborta)\b.*\b(tarea|tareas)\b", re.I)


def parse_background(text: str) -> str | None:
    found = BACKGROUND.match(text)
    return found.group("task").strip(" .") if found else None


def parse_together(text: str) -> list[str]:
    """«haz a la vez X y Y» -> ['X', 'Y'] (split at « y »/«;» between tasks)."""
    found = TOGETHER.match(text)
    if not found:
        return []
    parts = re.split(r";|\s+y también\s+|\s+y luego no\s+|\s+y además\s+|\s+y\s+(?=(?:busca|haz|crea|ordena|abre|descarga|"
                     r"resume|calcula|escribe|edita|prepara|revisa|organiza|investiga)\b)", found.group("tasks"))
    return [p.strip(" .,") for p in parts if p and p.strip(" .,")]


def step_status(answer: str) -> tuple[str, str]:
    for line in reversed([x.strip() for x in answer.strip().splitlines() if x.strip()]):
        upper = line.upper()
        for mark, status in (("TERMINADO:", "done"), ("FALTA:", "more"), ("NO POSIBLE:", "impossible")):
            if upper.startswith(mark):
                return status, line[len(mark):].strip()
    return "more", ""


@dataclass
class Step:
    text: str
    where: str = "fondo"
    platform: str = "web"
    check: str = ""
    important: bool = False
    status: str = "pending"  # pending | running | done | failed | skipped
    result: str = ""


@dataclass
class Task:
    id: int
    request: str
    title: str = ""
    steps: list[Step] = field(default_factory=list)
    status: str = "planning"  # planning | running | done | failed | cancelled
    result: str = ""
    activity: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)
    agent: dict[str, Any] | None = None  # a specialist agent (agentes.py) doing it
    replanned: bool = False

    def progress(self) -> float:
        if not self.steps:
            return 0.0
        return sum(s.status in ("done", "skipped") for s in self.steps) / len(self.steps)


Plan = Callable[[str], dict[str, Any]]
Ask = Callable[[str], str]  # one agent turn (its own conversation per task)


class Orchestrator:
    def __init__(
        self,
        plan: Plan,
        new_asker: Callable[[], Ask],
        activities: Activities,
        *,
        approve: Callable[[str], bool] = lambda _what: False,
        told: Callable[[str], None] = lambda _text: None,
        max_parallel: int = 3,
    ) -> None:
        self.plan, self.new_asker, self.activities = plan, new_asker, activities
        self.approve, self.told = approve, told
        self.screen = threading.Lock()  # one task at a time on the screen
        self.slots = threading.Semaphore(max_parallel)
        self.tasks: list[Task] = []
        self._ids = itertools.count(1)

    # -- API ------------------------------------------------------------------
    def submit(self, request: str, agent: dict[str, Any] | None = None) -> Task:
        task = Task(next(self._ids), request.strip(), agent=agent)
        label = f"{agent['nombre']}: {task.request}" if agent else task.request
        task.activity = self.activities.start(_short(label), "search" if agent else "task", "planificando…")
        self.tasks.append(task)
        threading.Thread(target=self._run, args=(task,), daemon=True).start()
        return task

    def running(self) -> list[Task]:
        return [t for t in self.tasks if t.status in ("planning", "running")]

    def cancel_last(self) -> str:
        live = self.running()
        if not live:
            return "No hay tareas en marcha."
        task = live[-1]
        task.cancel.set()
        return f"Cancelo «{task.title or _short(task.request)}»."

    # -- work -----------------------------------------------------------------
    def _run(self, task: Task) -> None:
        with self.slots:
            try:
                self._plan(task)
                task.status = "running"
                i = 0
                while i < len(task.steps):
                    step = task.steps[i]
                    if task.cancel.is_set():
                        task.status = "cancelled"
                        break
                    self._do(task, step)
                    self.activities.update(task.activity, progress=task.progress())
                    if step.status == "failed":
                        if step.result.startswith("Lo dejé sin hacer") or not self._replan(task, step):
                            break
                    i += 1
                if task.status == "running":
                    ok = all(s.status in ("done", "skipped") for s in task.steps)
                    task.status = "done" if ok else "failed"
            except Exception as exc:  # noqa: BLE001 — told, never a crash
                task.status, task.result = "failed", f"Falló: {exc}"
        self._finish(task)

    def _ask_plan(self, task: Task, request: str) -> dict[str, Any]:
        return self.plan(request) if task.agent is None else self.plan(request, task.agent)  # type: ignore[call-arg]

    def _replan(self, task: Task, failed: Step) -> bool:
        """One new plan for what is left, with a different approach."""
        if task.replanned:
            return False
        task.replanned = True
        done = "; ".join(s.text for s in task.steps if s.status == "done") or "nada"
        request = (
            f"{task.request}\nYa hecho: {done}.\nFalló «{failed.text}»: {failed.result}.\n"
            "Planifica SOLO lo que falta, con un enfoque distinto."
        )
        try:
            plan = self._ask_plan(task, request)
        except Exception:  # noqa: BLE001 — no new plan: stop where it failed
            return False
        fresh = self._steps(plan)
        if not fresh:
            return False
        failed.status = "skipped"
        keep = [s for s in task.steps if s.status in ("done", "skipped")]
        task.steps = keep + fresh
        task.result = ""
        self.activities.update(task.activity, detail="nuevo enfoque")
        return True

    @staticmethod
    def _steps(plan: dict[str, Any]) -> list[Step]:
        return [
            Step(
                text=str(s.get("paso") or ""),
                where="pantalla" if s.get("donde") == "pantalla" else "fondo",
                platform=str(s.get("plataforma") or "web"),
                check=str(s.get("comprobar") or ""),
                important=bool(s.get("importante")),
            )
            for s in plan.get("pasos") or []
            if str(s.get("paso") or "").strip()
        ]

    def _plan(self, task: Task) -> None:
        try:
            plan = self._ask_plan(task, task.request)
        except Exception:  # noqa: BLE001 — no planner: the request is one step
            plan = {"titulo": _short(task.request), "pasos": [{"paso": task.request, "donde": "pantalla"}]}
        task.title = str(plan.get("titulo") or _short(task.request))
        task.steps = self._steps(plan) or [Step(task.request, "pantalla")]
        kind = "screen" if any(s.where == "pantalla" for s in task.steps) else "task"
        self.activities.update(task.activity, title=task.title, detail=f"{len(task.steps)} pasos")
        if kind == "screen":
            self.activities.update(task.activity, detail=f"{len(task.steps)} pasos · usa la pantalla")

    def _do(self, task: Task, step: Step) -> None:
        if step.important and not self.approve(f"{task.title}: {step.text}"):
            step.status, step.result = "failed", "Lo dejé sin hacer: necesita su aprobación (su cara)."
            task.result = step.result
            return
        step.status = "running"
        n = task.steps.index(step) + 1
        self.activities.update(task.activity, detail=f"paso {n}/{len(task.steps)}: {_short(step.text, 40)}")
        ask = self._asker(task)
        prompt = self._prompt(task, step)
        if step.where == "pantalla":
            self.activities.update(task.activity, detail=f"esperando la pantalla · paso {n}")
            with self.screen:
                self.activities.update(task.activity, detail=f"en pantalla · paso {n}/{len(task.steps)}")
                answer = ask(prompt)
                status, detail = step_status(answer)
                if status == "more":  # one more try with what is missing
                    answer = ask(f"{prompt}\nFalta: {detail or 'verificar'}. Compruébalo y termina.")
        else:
            answer = ask(prompt)
            status, detail = step_status(answer)
            if status == "more":
                answer = ask(f"{prompt}\nFalta: {detail or 'verificar'}. Compruébalo y termina.")
        status, detail = step_status(answer)
        step.result = detail or answer[-300:]
        step.status = "done" if status == "done" else "failed"
        if step.status == "failed":
            task.result = f"Me quedé en el paso {n}: {step.result}"

    def _asker(self, task: Task) -> Ask:
        if not hasattr(task, "_ask"):
            task._ask = self.new_asker()  # type: ignore[attr-defined]
        return task._ask  # type: ignore[attr-defined]

    def _prompt(self, task: Task, step: Step) -> str:
        done = [f"- {s.text} → {s.result}" for s in task.steps if s.status == "done"]
        role = task.agent or {}
        return "\n".join(
            [
                f"Eres el agente «{role['nombre']}»: {role.get('instrucciones', '')}" if role else "",
                f"Tarea completa del usuario: «{task.request}»",
                ("Ya hecho:\n" + "\n".join(done)) if done else "",
                f"Paso actual ({step.platform}): {step.text}",
                f"Cómo comprobarlo: {step.check}" if step.check else "",
                STEP_RULES[step.where],
                END_RULE,
            ]
        ).strip()

    def _finish(self, task: Task) -> None:
        ok = task.status == "done"
        if ok:
            results = [s.result for s in task.steps if s.result and s.status == "done"]
            task.result = results[-1] if results else "Hecho."
        elif task.status == "cancelled":
            task.result = "Cancelada."
        self.activities.finish(task.activity, ok, _short(task.result, 80))
        head = f"«{task.title or _short(task.request)}»"
        self.told(f"Tarea {head} terminada: {task.result}" if ok else f"Tarea {head}: {task.result}")


def _short(text: str, n: int = 32) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


__all__ = ["CANCEL", "Orchestrator", "Step", "Task", "WHAT_DOING", "parse_background", "parse_together", "step_status"]


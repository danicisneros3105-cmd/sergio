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
   Steps form a graph: each says which earlier steps it needs
   (``depende_de``), so independent steps of the same task run at the same
   time (three searches at once, then the table that needs all three).
3. Each step must end with ``TERMINADO:``, ``FALTA:`` or ``NO POSIBLE:``; a
   step that is not done gets one more try with what is missing.
4. Steps that send, pay, publish, install or delete wait for the owner's
   face (the checkpoint), and the end of a task is checked once more
   against the request before Sergio says it is done: a Revisor (a fresh
   agent that did not do the work) compares the results with the request,
   and what it finds missing gets one fix step.
"""

from __future__ import annotations

import itertools
import re
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
TOGETHER = re.compile(
    r"^\s*(?:haz|has|realiza)\s+(?:a la vez|al mismo tiempo|en paralelo)\s*[,:]?\s*(?P<tasks>.+)$",
    re.I,
)
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
    parts = re.split(
        r";|\s+y también\s+|\s+y luego no\s+|\s+y además\s+|\s+y\s+(?=(?:busca|haz|crea|ordena|abre|descarga|"
        r"resume|calcula|escribe|edita|prepara|revisa|organiza|investiga)\b)",
        found.group("tasks"),
    )
    return [p.strip(" .,") for p in parts if p and p.strip(" .,")]


def step_status(answer: str) -> tuple[str, str]:
    for line in reversed([x.strip() for x in answer.strip().splitlines() if x.strip()]):
        upper = line.upper()
        for mark, status in (
            ("TERMINADO:", "done"),
            ("FALTA:", "more"),
            ("NO POSIBLE:", "impossible"),
        ):
            if upper.startswith(mark):
                return status, line[len(mark) :].strip()
    return "more", ""


MAX_FANOUT = 300  # sub-agents one step may become (one per element)


def _env_int(name: str, default: int, top: int) -> int:
    import os

    try:
        return max(1, min(top, int(os.environ.get(name, default))))
    except ValueError:
        return default


@dataclass
class Step:
    text: str
    where: str = "fondo"
    platform: str = "web"
    check: str = ""
    important: bool = False
    status: str = "pending"  # pending | running | done | failed | skipped
    result: str = ""
    after: list[int] | None = (
        None  # indexes of the steps it needs; None = the previous one
    )


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
    rules: str = ""  # permanent skills that matched (server), in every step
    calls: int = 0  # agent turns used (each one may call several tools)

    def progress(self) -> float:
        if not self.steps:
            return 0.0
        return sum(s.status in ("done", "skipped") for s in self.steps) / len(
            self.steps
        )


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
        max_parallel: int = 0,
        swarm: int = 0,
        on_plan: Callable[[Task], None] = lambda _task: None,
        on_done: Callable[[Task], None] = lambda _task: None,
        plan_grace: float = 0.0,
        exists: Callable[[str], bool | None] | None = None,
        review: bool = False,
    ) -> None:
        self.review = review  # a Revisor checks multi-step results against the request
        # Anti-hallucination: a step that says it saved a file is only done
        # if the file is really there (None = that path cannot be checked).
        self.exists = exists
        # Seconds to object after the plan is shown (a plan you can't veto is
        # theatre): tasks that use the screen or touch something important wait.
        self.plan_grace = plan_grace
        self.on_plan, self.on_done = (
            on_plan,
            on_done,
        )  # show the plan first; remember results
        self.plan, self.new_asker, self.activities = plan, new_asker, activities
        self.approve, self.told = approve, told
        self.screen = threading.Lock()  # one task at a time on the screen
        # Tasks at once, and agent turns at once across all of them (the
        # swarm). Defaults fit a free Gemini key; sergio.env can raise them:
        # SERGIO_TAREAS (up to 50) and SERGIO_ENJAMBRE (up to 300).
        self.slots = threading.Semaphore(
            max_parallel or _env_int("SERGIO_TAREAS", 6, 50)
        )
        self.swarm = threading.BoundedSemaphore(
            swarm or _env_int("SERGIO_ENJAMBRE", 8, MAX_FANOUT)
        )
        self.worker_limit = min(
            300, max(1, swarm or _env_int("SERGIO_ENJAMBRE", 8, MAX_FANOUT))
        )
        self._pool = ThreadPoolExecutor(
            max_workers=self.worker_limit, thread_name_prefix="sergio-swarm"
        )
        self._calls_lock = threading.Lock()
        self.tasks: list[Task] = []
        self._task_lock = threading.Lock()
        self._closed = False
        self._ids = itertools.count(1)

    # -- API ------------------------------------------------------------------
    def submit(self, request: str, agent: dict[str, Any] | None = None) -> Task:
        with self._task_lock:
            if self._closed or len(self.running()) >= 64:
                raise RuntimeError(
                    "Swarm cerrado o 64 tareas pendientes; espera a que termine un lote"
                )
            self.tasks = [t for t in self.tasks if t in self.running()] + [
                t for t in self.tasks if t not in self.running()
            ][-136:]
            task = Task(next(self._ids), request.strip(), agent=agent)
            self.tasks.append(task)
        label = f"{agent['nombre']}: {task.request}" if agent else task.request
        task.activity = self.activities.start(
            _short(label), "search" if agent else "task", "planificando…"
        )
        threading.Thread(target=self._run, args=(task,), daemon=True).start()
        return task

    def running(self) -> list[Task]:
        return [t for t in self.tasks if t.status in ("planning", "running")]

    def snapshot(self) -> list[dict[str, Any]]:
        """Bounded copies for the UI; never expose mutable tasks or fake progress."""
        with self._task_lock:
            return [
                {
                    "id": task.id,
                    "title": task.title or task.request[:120],
                    "state": task.status,
                    "progress": task.progress(),
                    "detail": f"{len(task.steps)} pasos · {task.calls} turnos de agente",
                }
                for task in self.tasks[-200:]
            ]

    def task_details(self, task_id: int) -> dict[str, Any]:
        """Copy detail for the selected task only, within a fixed UI budget."""
        with self._task_lock:
            task = next((task for task in self.tasks if task.id == task_id), None)
            if task is None:
                return {}
            return {
                "total_steps": len(task.steps),
                "steps": [
                    {
                        "text": step.text[:500],
                        "status": step.status,
                        "where": step.where,
                        "result": step.result[:800],
                    }
                    for step in list(task.steps[:80])
                ],
                "result": task.result[:4000],
            }

    def cancel_task(self, task_id: int) -> bool:
        with self._task_lock:
            for task in self.tasks:
                if task.id == task_id and task.status in ("planning", "running"):
                    task.cancel.set()
                    return True
        return False

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
                needs_eyes = any(
                    st.where == "pantalla" or st.important for st in task.steps
                )
                if self.plan_grace and needs_eyes and task.cancel.wait(self.plan_grace):
                    task.status = "cancelled"
                    task.steps = []
                task.status = "running" if task.status != "cancelled" else "cancelled"
                while task.status == "running":
                    if task.cancel.is_set():
                        task.status = "cancelled"
                        break
                    ready = self._ready(task)
                    if not ready:
                        break
                    self._wave(task, ready)
                    self.activities.update(task.activity, progress=task.progress())
                    failed = next((st for st in ready if st.status == "failed"), None)
                    if failed is not None:
                        if failed.result.startswith(
                            "Lo dejé sin hacer"
                        ) or not self._replan(task, failed):
                            break
                if task.status == "running":
                    ok = any(s.status == "done" for s in task.steps) and all(
                        s.status in ("done", "skipped") for s in task.steps
                    )
                    if (
                        ok
                        and self.review
                        and len(task.steps) > 1
                        and not task.cancel.is_set()
                    ):
                        ok = self._review(task)
                    task.status = "done" if ok else "failed"
            except Exception as exc:  # noqa: BLE001 — told, never a crash
                task.status, task.result = "failed", f"Falló: {exc}"
        self._finish(task)

    @staticmethod
    def _ready(task: Task) -> list[Step]:
        """Pending steps whose needed steps are all done (the graph's front)."""
        finished = {
            i for i, st in enumerate(task.steps) if st.status in ("done", "skipped")
        }
        ready = []
        for i, st in enumerate(task.steps):
            needs = st.after if st.after is not None else ([i - 1] if i else [])
            if st.status == "pending" and all(n in finished for n in needs):
                ready.append(st)
        return ready

    def _wave(self, task: Task, ready: list[Step]) -> None:
        """Independent steps at the same time, each with its own agent turn
        (screen steps still queue for the screen inside _do)."""
        if len(ready) == 1:
            self._do(task, ready[0])
            return
        self.activities.update(
            task.activity, detail=f"enjambre: {len(ready)} subagentes a la vez"
        )
        pending = iter(ready)
        active = {}

        def submit_one() -> bool:
            if task.cancel.is_set():
                return False
            step = next(pending, None)
            if step is None:
                return False
            future = self._pool.submit(
                self._do, task, step, self._limited(task, self.new_asker())
            )
            active[future] = step
            return True

        for _ in range(min(len(ready), self.worker_limit)):
            submit_one()
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                step = active.pop(future)
                try:
                    future.result()
                except Exception as exc:
                    step.status, step.result = (
                        "failed",
                        f"Subagente falló: {type(exc).__name__}",
                    )
                submit_one()

    def close(self) -> None:
        for task in self.running():
            task.cancel.set()
        self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _review(self, task: Task) -> bool:
        """The Revisor: a fresh agent checks the results against the request;
        what it finds missing gets one fix step."""
        results = "\n".join(
            f"- {st.text[:250]} → {st.result[:1500]}"
            for st in task.steps
            if st.status == "done"
        )
        results = results[:32000]
        verdict = self._limited(task, self.new_asker())(
            f"Eres el Revisor de Sergio: no hiciste el trabajo, lo compruebas.\nPedido del usuario: "
            f"«{task.request}»\nResultados de los pasos:\n{results}\n"
            "Comprueba con herramientas (lee los archivos, verifica cifras) que se cumplió TODO lo pedido. "
            + END_RULE
        )
        status, detail = step_status(verdict)
        if status == "done":
            return True
        if status != "more" or not detail:
            task.result = "El revisor no pudo verificar el resultado."
            return False
        self.activities.update(task.activity, detail="el revisor pidió un ajuste")
        fix = Step(f"Corrige lo que falta: {detail}", "fondo", after=[])
        task.steps.append(fix)
        self._do(task, fix)
        return fix.status == "done"

    def _ask_plan(self, task: Task, request: str) -> dict[str, Any]:
        return (
            self.plan(request) if task.agent is None else self.plan(request, task.agent)
        )  # type: ignore[call-arg]

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
        for k, st in enumerate(fresh):  # the new plan's graph, after what is kept
            st.after = (
                [len(keep) + n for n in st.after]
                if st.after is not None
                else ([len(keep) + k - 1] if k else [])
            )
        task.steps = keep + fresh
        task.result = ""
        self.activities.update(task.activity, detail="nuevo enfoque")
        return True

    @staticmethod
    def _steps(plan: dict[str, Any]) -> list[Step]:
        """The plan's steps as a graph. A step with «para_cada» becomes one
        sub-agent per element, all at once (the swarm); what needed that step
        then waits for all of them."""
        raw = plan.get("pasos") or []
        if not isinstance(raw, list) or len(raw) > 4000:
            raise ValueError("El plan debe contener una lista de hasta 4000 pasos")
        if any(
            not isinstance(s, dict) or not str(s.get("paso") or "").strip() for s in raw
        ):
            raise ValueError("El plan contiene pasos vacíos o inválidos")
        steps: list[Step] = []
        made: list[list[int]] = []  # plan step -> the steps it became
        for i, s in enumerate(raw):
            if s.get("bloqueado") or s.get("inventadas"):
                raise ValueError(
                    "El plan usa herramientas no autorizadas o inexistentes"
                )
            needs = s.get("depende_de")
            if needs is not None:
                if not isinstance(needs, list) or any(
                    not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= i
                    for n in needs
                ):
                    raise ValueError(
                        f"Dependencias inválidas en el paso {i + 1}; deben referir a pasos anteriores"
                    )
                wanted = {n - 1 for n in needs}
            else:  # not said: after the previous step (safe, in order)
                wanted = {i - 1} if i else set()
            after = sorted({k for w in wanted for k in made[w]})
            fanout = s.get("para_cada") or []
            if not isinstance(fanout, list) or len(fanout) > MAX_FANOUT:
                raise ValueError(
                    f"para_cada debe ser una lista de hasta {MAX_FANOUT} elementos"
                )
            items = [str(x) for x in fanout] if s.get("donde") != "pantalla" else []
            if len(steps) + max(1, len(items)) > 4000:
                raise ValueError(
                    "El plan supera 4000 pasos; divide el trabajo en lotes"
                )
            text = str(s.get("paso") or "")
            base = dict(
                where="pantalla" if s.get("donde") == "pantalla" else "fondo",
                platform=str(s.get("plataforma") or "web"),
                check=str(s.get("comprobar") or ""),
                important=bool(s.get("importante")),
            )
            start = len(steps)
            if items:
                steps += [
                    Step(text=f"{text} — solo para: {item}", after=list(after), **base)
                    for item in items
                ]
            else:
                steps.append(
                    Step(
                        text=text,
                        after=after if (needs is not None or i) else None,
                        **base,
                    )
                )
            made.append(list(range(start, len(steps))))
        if len(steps) > 4000:
            raise ValueError("El plan supera 4000 pasos; divide el trabajo en lotes")
        return steps

    def _plan(self, task: Task) -> None:
        try:
            plan = self._ask_plan(task, task.request)
        except Exception:  # noqa: BLE001 — no planner: the request is one step
            plan = {
                "titulo": _short(task.request),
                "pasos": [{"paso": task.request, "donde": "pantalla"}],
            }
        task.title = str(plan.get("titulo") or _short(task.request))
        task.rules = str(plan.get("reglas") or "")
        task.steps = self._steps(plan) or [Step(task.request, "pantalla")]
        self.on_plan(task)
        kind = "screen" if any(s.where == "pantalla" for s in task.steps) else "task"
        self.activities.update(
            task.activity, title=task.title, detail=f"{len(task.steps)} pasos"
        )
        if kind == "screen":
            self.activities.update(
                task.activity, detail=f"{len(task.steps)} pasos · usa la pantalla"
            )

    def _do(self, task: Task, step: Step, ask: Ask | None = None) -> None:
        if step.important and not self.approve(f"{task.title}: {step.text}"):
            step.status, step.result = (
                "failed",
                "Lo dejé sin hacer: necesita su aprobación (su cara).",
            )
            task.result = step.result
            return
        step.status = "running"
        n = task.steps.index(step) + 1
        self.activities.update(
            task.activity, detail=f"paso {n}/{len(task.steps)}: {_short(step.text, 40)}"
        )
        ask = ask or self._asker(task)
        prompt = self._prompt(task, step)
        if step.where == "pantalla":
            self.activities.update(
                task.activity, detail=f"esperando la pantalla · paso {n}"
            )
            with self.screen:
                self.activities.update(
                    task.activity, detail=f"en pantalla · paso {n}/{len(task.steps)}"
                )
                answer = ask(prompt)
                status, detail = step_status(answer)
                if status == "more":  # one more try with what is missing
                    answer = ask(
                        f"{prompt}\nFalta: {detail or 'verificar'}. Compruébalo y termina."
                    )
        else:
            answer = ask(prompt)
            status, detail = step_status(answer)
            if status == "more":
                answer = ask(
                    f"{prompt}\nFalta: {detail or 'verificar'}. Compruébalo y termina."
                )
        status, detail = step_status(answer)
        missing = (
            self._missing_files(f"{step.check}\n{detail}") if status == "done" else []
        )
        if missing:  # it says it saved something that is not there: one more try
            answer = ask(
                f"{prompt}\nDijiste que guardaste {', '.join(missing)}, pero no existe. "
                "Créalo de verdad y comprueba que está."
            )
            status, detail = step_status(answer)
            missing = (
                self._missing_files(f"{step.check}\n{detail}") if status == "done" else []
            )
            if missing:
                status, detail = (
                    "more",
                    f"no pude verificar {', '.join(missing)}",
                )
        step.result = detail or answer[-300:]
        step.status = "done" if status == "done" else "failed"
        if step.status == "failed":
            task.result = f"Me quedé en el paso {n}: {step.result}"

    def _missing_files(self, text: str) -> list[str]:
        paths = list(dict.fromkeys(claimed_paths(text)))
        if self.exists is None:
            return paths
        missing = []
        for path in paths:
            try:
                if self.exists(path) is not True:
                    missing.append(path)
            except Exception:  # noqa: BLE001 — an unavailable check is not proof
                missing.append(path)
        return missing

    def _asker(self, task: Task) -> Ask:
        if not hasattr(task, "_ask"):
            task._ask = self._limited(task, self.new_asker())  # type: ignore[attr-defined]
        return task._ask  # type: ignore[attr-defined]

    def _limited(self, task: Task, ask: Ask) -> Ask:
        """An agent turn that waits for a place in the swarm and is counted."""

        def turn(prompt: str) -> str:
            while not self.swarm.acquire(timeout=0.1):
                if task.cancel.is_set():
                    raise RuntimeError("Tarea cancelada")
            try:
                if task.cancel.is_set():
                    raise RuntimeError("Tarea cancelada")
                with self._calls_lock:
                    if task.calls >= 4000:
                        raise RuntimeError("Presupuesto de 4000 llamadas agotado")
                    task.calls += 1
                return ask(prompt)
            finally:
                self.swarm.release()

        return turn

    def _prompt(self, task: Task, step: Step) -> str:
        dependencies = (
            step.after
            if step.after is not None
            else list(range(task.steps.index(step)))
        )
        done = [
            f"- {task.steps[i].text[:250]} → {task.steps[i].result[:1000]}"
            for i in dependencies
            if task.steps[i].status == "done"
        ]
        if len("\n".join(done)) > 32000:
            raise ValueError(
                "Contexto de dependencias demasiado grande; divide el trabajo en fases"
            )
        role = task.agent or {}
        return "\n".join(
            [
                f"Eres el agente «{role['nombre']}»: {role.get('instrucciones', '')}"
                if role
                else "",
                f"Tarea completa del usuario: «{task.request}»",
                f"Reglas de tus skills (obligatorias):\n{task.rules}"
                if task.rules
                else "",
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
        try:
            self.on_done(task)
        except Exception:  # noqa: BLE001 — memory is a bonus
            pass
        head = f"«{task.title or _short(task.request)}»"
        self.told(
            f"Tarea {head} terminada: {task.result}"
            if ok
            else f"Tarea {head}: {task.result}"
        )


def _short(text: str, n: int = 32) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


PATH = re.compile(r"(?:[A-Za-z]:\\|~[\\/]|/home/|/mnt/)[^\s\"'«»,;]+\.[A-Za-z0-9]{1,5}")


def claimed_paths(text: str) -> list[str]:
    """File paths a step says it wrote («guardado en C:\\Users\\…\\tabla.xlsx»)."""
    return [m.rstrip(".)") for m in PATH.findall(text or "")]


def plan_line(task: Task) -> str:
    """«Plan: 1) buscar… 2) tabla… 3) abrir (pantalla)» — the plan, seen first."""
    parts, n, i = [], 0, 0
    while i < len(task.steps):
        s = task.steps[i]
        head = s.text.split(" — solo para: ")[0]
        same = 1
        while i + same < len(task.steps) and task.steps[i + same].text.startswith(
            head + " — solo para: "
        ):
            same += 1
        n += 1
        if same > 1:  # a swarm step: one line, not 300
            parts.append(f"{n}) {_short(head, 38)} ×{same} subagentes a la vez")
        else:
            parts.append(
                f"{n}) {_short(s.text, 38)}"
                + (" (pantalla)" if s.where == "pantalla" else "")
                + (" (a la vez)" if s.after == [] and i > 0 else "")
            )
        i += same
    line = f"Plan de «{task.title or _short(task.request)}»: " + " ".join(parts)
    if any(st.where == "pantalla" or st.important for st in task.steps):
        line += " · di «cancela la tarea» para pararla"
    return line


__all__ = [
    "claimed_paths",
    "plan_line",
    "CANCEL",
    "Orchestrator",
    "Step",
    "Task",
    "WHAT_DOING",
    "parse_background",
    "parse_together",
    "step_status",
]

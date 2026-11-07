"""Cowork runs: describe the outcome, step away, Sergio does the rest.

A run plans the outcome into steps (the same planner as ``/v1/tasks/plan``),
then works through them in dependency order. Before each step,
:class:`~openjarvis.cowork.scrutiny.AdaptiveScrutiny` decides whether it runs
on its own, waits for the owner or is not done. Every tool call counts
against a hard cap (``max_actions``, 50 by default): when it is reached the
run stops, whatever is left. Progress goes to whoever watches (the web app,
the phone, ``sergio cowork``) and, when configured, to the owner's own
channel. Everything is written to a hash-chained audit trail.

Steps that need the screen (mouse and keyboard) are not done here: the run
says so and leaves them for Sergio Escritorio.
"""

from __future__ import annotations

import contextvars
import json
import os
import queue
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openjarvis.cli.friendly import plain
from openjarvis.cowork.audit import AuditTrail
from openjarvis.cowork.scrutiny import AdaptiveScrutiny, TrustStore, normalize_autonomy

DEFAULT_MAX_ACTIONS = 50
HARD_MAX_ACTIONS = 500
FINAL_STATES = ("done", "partial", "failed", "capped", "cancelled", "interrupted")
END_RULE = (
    "No inventes datos. Si la comprobación es URL | texto exacto, llama a en_segundo_plano con "
    "acción revisar, la URL y buscar igual al texto exacto. Si es ARCHIVO | ruta absoluta "
    "| texto exacto, usa file_write y después file_read en esa misma ruta. Termina con "
    "exactamente una línea: 'TERMINADO: <qué hiciste y dónde quedó>', 'FALTA: <qué falta>' "
    "o 'NO POSIBLE: <por qué>'."
)
_STATUS = re.compile(r"^\s*(TERMINADO|FALTA|NO POSIBLE)\s*:\s*(.*)$", re.I | re.M)

Planner = Callable[[str], Dict[str, Any]]
# (prompt, tools, max_actions) -> (answer text, tool calls used)
StepRunner = Callable[[str, List[str], int], "tuple[str, int]"]
OwnerSender = Callable[[str], bool]


class BudgetExhausted(RuntimeError):
    """The run used every action it was allowed."""


class ActionBudget:
    """A hard cap on tool calls for one run (thread-safe)."""

    def __init__(self, limit: int = DEFAULT_MAX_ACTIONS) -> None:
        self.limit = max(1, min(int(limit), HARD_MAX_ACTIONS))
        self.used = 0
        self._lock = threading.Lock()

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def spend(self, n: int) -> int:
        """Count *n* actions; raises :class:`BudgetExhausted` once over the cap."""
        with self._lock:
            self.used += max(0, int(n))
            if self.used >= self.limit:
                raise BudgetExhausted(f"{self.used}/{self.limit} acciones")
            return self.remaining


def step_status(answer: str) -> tuple[str, str]:
    """('done' | 'more' | 'impossible' | 'unknown', detail) from a step answer."""
    found = _STATUS.findall(answer or "")
    if not found:
        return "unknown", (answer or "").strip()[-300:]
    word, detail = found[-1]
    word = word.upper()
    kind = {"TERMINADO": "done", "FALTA": "more", "NO POSIBLE": "impossible"}[word]
    return kind, detail.strip()


@dataclass
class CoworkStep:
    index: int
    text: str
    where: str = "fondo"
    tools: List[str] = field(default_factory=list)
    check: str = ""
    needs: Optional[List[int]] = None  # 0-based indexes; None = the previous step
    invented: List[str] = field(default_factory=list)
    status: str = (
        "pending"  # pending running done failed skipped waiting_approval blocked
    )
    verdict: Dict[str, Any] = field(default_factory=dict)
    result: str = ""
    actions: int = 0
    for_each: List[str] = field(default_factory=list)


@dataclass
class CoworkRun:
    id: str
    goal: str
    autonomy: str = "normal"
    max_actions: int = DEFAULT_MAX_ACTIONS
    status: str = "planning"
    title: str = ""
    steps: List[CoworkStep] = field(default_factory=list)
    actions_used: int = 0
    summary: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    dropped: List[str] = field(default_factory=list)
    # What the owner says while the run works (read before every step), and
    # the earlier task this one continues, with its outcome.
    notes: List[Dict[str, Any]] = field(default_factory=list)
    follows: str = ""
    context: str = ""
    plan_first: bool = False  # «modo plan»: the owner approves the plan first

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        done = sum(s.status == "done" for s in self.steps)
        data["progress"] = round(done / len(self.steps), 3) if self.steps else 0.0
        data["waiting"] = [
            s.index for s in self.steps if s.status == "waiting_approval"
        ]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CoworkRun":
        steps = [CoworkStep(**s) for s in data.get("steps", [])]
        fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        fields["steps"] = steps
        return cls(**fields)


def _home() -> Path:
    return (
        Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")
        / "cowork"
    )


def steps_from_plan(plan: Dict[str, Any]) -> List[CoworkStep]:
    steps: List[CoworkStep] = []
    for i, raw in enumerate(plan.get("pasos") or []):
        if not isinstance(raw, dict):
            continue
        needs = raw.get("depende_de")
        steps.append(
            CoworkStep(
                index=i,
                text=str(raw.get("paso") or "").strip(),
                where=str(raw.get("donde") or "fondo"),
                tools=[str(t) for t in raw.get("herramientas") or []],
                check=str(raw.get("comprobar") or ""),
                needs=[int(n) - 1 for n in needs] if isinstance(needs, list) else None,
                invented=[str(t) for t in raw.get("inventadas") or []],
                for_each=[str(x) for x in raw.get("para_cada") or []],
            )
        )
    return [s for s in steps if s.text]


class CoworkEngine:
    """Starts, tracks and steers Cowork runs (one thread per run)."""

    def __init__(
        self,
        *,
        planner: Optional[Planner] = None,
        runner: Optional[StepRunner] = None,
        send_owner: Optional[OwnerSender] = None,
        root: Optional[Path] = None,
        trust: Optional[TrustStore] = None,
        approval_timeout: float = 2 * 3600,
        notify_every: float = 20.0,
    ) -> None:
        self.planner = planner
        self.runner = runner
        self.send_owner = send_owner
        self.root = root or _home()
        self.trust = (
            trust if trust is not None else TrustStore(self.root / "trust.json")
        )
        self.approval_timeout = approval_timeout
        self.notify_every = notify_every
        self.runs: Dict[str, CoworkRun] = {}
        self._decisions: Dict[tuple[str, int], "queue.Queue[bool]"] = {}
        self._cancel: Dict[str, threading.Event] = {}
        self._listeners: Dict[str, List["queue.Queue[Dict[str, Any]]"]] = {}
        self._last_notice: Dict[str, float] = {}
        self._trails: Dict[str, AuditTrail] = {}
        self._lock = threading.RLock()
        self._load_previous()

    # -- public API -----------------------------------------------------------
    def start(
        self,
        goal: str,
        *,
        autonomy: str = "normal",
        max_actions: int = DEFAULT_MAX_ACTIONS,
        wait: bool = False,
        listener: Optional["queue.Queue[Dict[str, Any]]"] = None,
        follows: str = "",
        plan_first: bool = False,
    ) -> CoworkRun:
        """Start a run. Pass *listener* to receive every event from the very
        first one (``listen()`` after ``start()`` may miss the plan)."""
        goal = " ".join(goal.split())
        if not goal:
            raise ValueError("Describa el resultado que quiere.")
        run = CoworkRun(
            id=time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
            goal=goal[:8000],  # room for the attached files
            autonomy=normalize_autonomy(autonomy),
            max_actions=ActionBudget(max_actions).limit,
            plan_first=bool(plan_first),
        )
        parent = self.get(follows) if follows else None
        if parent is not None:
            run.follows = parent.id
            run.context = (
                f"Esto continúa la tarea «{parent.title or parent.goal[:60]}» "
                f"(objetivo: «{parent.goal[:600]}»; resultado: "
                f"{(parent.summary or 'sin resumen')[:600]})."
            )
        with self._lock:
            self.runs[run.id] = run
            self._cancel[run.id] = threading.Event()
            if listener is not None:
                self._listeners.setdefault(run.id, []).append(listener)
        self._audit(run).record(
            "started", goal=run.goal, autonomy=run.autonomy, max_actions=run.max_actions
        )
        self._save(run)
        # The task keeps who asked (a customer's own AI key and plan).
        ctx = contextvars.copy_context()
        thread = threading.Thread(target=ctx.run, args=(self._work, run), daemon=True)
        thread.start()
        if wait:
            thread.join()
        return run

    def get(self, run_id: str) -> Optional[CoworkRun]:
        with self._lock:
            return self.runs.get(run_id)

    def list(self) -> List[CoworkRun]:
        with self._lock:
            return sorted(self.runs.values(), key=lambda r: r.created, reverse=True)

    def decide(self, run_id: str, step: int, approve: bool) -> bool:
        """The owner's answer for a step waiting for approval."""
        with self._lock:
            box = self._decisions.get((run_id, step))
        if box is None:
            return False
        box.put(bool(approve))
        return True

    def note(self, run_id: str, text: str) -> bool:
        """An instruction from the owner while the run works; every later
        step reads it. False when the run is unknown or already finished."""
        text = " ".join(str(text).split())[:1000]
        run = self.get(run_id)
        if run is None or not text or run.status in FINAL_STATES:
            return False
        with self._lock:
            run.notes.append({"text": text, "at": round(time.time(), 3)})
        self._audit(run).record("owner_note", text=text)
        self._save(run)
        self._event(run, "note", text=text)
        return True

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            event = self._cancel.get(run_id)
            waiting = [k for k in self._decisions if k[0] == run_id]
        if event is None:
            return False
        event.set()
        for key in waiting:  # wake a run blocked on an approval
            self.decide(*key, approve=False)
        return True

    def audit(self, run_id: str) -> AuditTrail:
        """The run's trail (one instance per run, so the hash chain stays whole)."""
        with self._lock:
            trail = self._trails.get(run_id)
            if trail is None:
                trail = AuditTrail(self.root / run_id / "audit.jsonl")
                self._trails[run_id] = trail
            return trail

    def listen(self, run_id: str) -> "queue.Queue[Dict[str, Any]]":
        box: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        with self._lock:
            self._listeners.setdefault(run_id, []).append(box)
        return box

    def unlisten(self, run_id: str, box: "queue.Queue[Dict[str, Any]]") -> None:
        with self._lock:
            boxes = self._listeners.get(run_id, [])
            if box in boxes:
                boxes.remove(box)

    # -- the run --------------------------------------------------------------
    def _work(self, run: CoworkRun) -> None:
        audit = self._audit(run)
        cancel = self._cancel[run.id]
        scrutiny = AdaptiveScrutiny(run.autonomy, self.trust)
        budget = ActionBudget(run.max_actions)
        try:
            plan = self._plan(f"{run.goal}\n{run.context}" if run.context else run.goal)
            run.title = str(plan.get("titulo") or run.goal[:50])
            run.steps = steps_from_plan(plan) or [CoworkStep(0, run.goal, "fondo")]
            run.dropped = [str(d) for d in plan.get("descartados") or []]
            run.status = "running"
            audit.record(
                "planned",
                title=run.title,
                steps=[s.text for s in run.steps],
                dropped=run.dropped,
            )
            self._event(run, "planned", text=f"Plan: {len(run.steps)} pasos.")
            self._notify(
                run,
                f"Cowork «{run.title}»: empiezo, {len(run.steps)} pasos.",
                force=True,
            )
            if run.plan_first and not self._approve_plan(run, cancel):
                run.status = "cancelled"
                run.summary = "Usted no aprobó el plan; no hice nada."
            while run.status == "running":
                if cancel.is_set():
                    run.status = "cancelled"
                    break
                step = self._next(run)
                if step is None:
                    break
                self._do(run, step, scrutiny, budget, audit, cancel)
                run.actions_used = budget.used
                if budget.remaining == 0:
                    run.status = "capped"
            self._finish(run, audit)
        except BudgetExhausted:
            run.actions_used = budget.used
            run.status = "capped"
            self._finish(run, audit)
        except Exception as exc:  # noqa: BLE001 - a run never takes the server down
            run.status = "failed"
            run.summary = f"No pudo terminar. {plain(exc)}"[:500]
            audit.record("error", error=run.summary)
            self._finish(run, audit)

    def _plan(self, goal: str) -> Dict[str, Any]:
        planner = self.planner
        if planner is None:
            from openjarvis.server.tasks_routes import plan_task

            planner = plan_task
        plan = planner(goal)
        return plan if isinstance(plan, dict) else {}

    @staticmethod
    def _next(run: CoworkRun) -> Optional[CoworkStep]:
        """The first pending step whose needed steps are settled. A step whose
        needed step did not get done is skipped (and so are its dependents)."""
        settled = ("done", "failed", "skipped", "blocked")
        progress = True
        while progress:
            progress = False
            for step in run.steps:
                if step.status != "pending":
                    continue
                needs = step.needs
                if needs is None:
                    needs = [step.index - 1] if step.index else []
                parents = [run.steps[n] for n in needs if 0 <= n < len(run.steps)]
                if any(p.status not in settled for p in parents):
                    continue
                if any(p.status != "done" for p in parents):
                    step.status = "skipped"
                    step.result = "No lo hice: depende de un paso que no se completó."
                    progress = True
                    continue
                return step
        return None

    def _do(
        self,
        run: CoworkRun,
        step: CoworkStep,
        scrutiny: AdaptiveScrutiny,
        budget: ActionBudget,
        audit: AuditTrail,
        cancel: threading.Event,
    ) -> None:
        verdict = scrutiny.review(
            step.text,
            goal=run.goal,
            tools=step.tools,
            where=step.where,
            check=step.check,
            invented=step.invented,
        )
        step.verdict = verdict.to_dict()
        audit.record("scrutiny", step=step.index, text=step.text, **step.verdict)
        if verdict.decision == "block":
            step.status, step.result = "blocked", " ".join(verdict.reasons)
            self._event(run, "blocked", step=step.index, text=step.result)
            return
        if verdict.decision == "ask":
            approved = self._ask_owner(run, step, verdict.reasons, cancel)
            self.trust.record(verdict.signature, approved)
            audit.record("owner_decision", step=step.index, approved=approved)
            if not approved:
                step.status = "skipped"
                step.result = "Usted no lo aprobó (o no respondió a tiempo)."
                self._event(run, "skipped", step=step.index, text=step.result)
                return
        if step.where == "pantalla":
            step.status = "skipped"
            step.result = (
                "Este paso usa la pantalla (ratón y teclado): hágalo desde Sergio "
                "Escritorio con «en segundo plano»."
            )
            audit.record("needs_screen", step=step.index)
            self._event(run, "skipped", step=step.index, text=step.result)
            return
        step.status = "running"
        self._event(
            run, "step", step=step.index, text=f"Paso {step.index + 1}: {step.text}"
        )
        audit.record("step_started", step=step.index, tools=step.tools)
        prompt = self._prompt(run, step)
        if self.runner is None:
            from functools import partial

            runner = partial(_default_runner(), expected_check=step.check)
        else:
            runner = self.runner
        answer, used = runner(prompt, step.tools, budget.remaining)
        status, detail = step_status(answer)
        step.actions += used
        try:
            budget.spend(used)
            if (
                status in ("more", "unknown")
                and budget.remaining > 0
                and not cancel.is_set()
            ):
                again, used2 = runner(
                    f"{prompt}\nFalta: {detail or 'verificar'}. Compruébalo y termina.",
                    step.tools,
                    budget.remaining,
                )
                step.actions += used2
                answer = again
                status, detail = step_status(answer)
                budget.spend(used2)
        finally:
            run.actions_used = budget.used
            step.result = (detail or answer or "")[-600:]
            step.status = "done" if status == "done" and answer else "failed"
            scrutiny.note_outcome(step.status == "done")
            audit.record(
                "step_finished",
                step=step.index,
                status=step.status,
                actions=step.actions,
                result=step.result,
            )
            self._event(
                run,
                step.status,
                step=step.index,
                text=f"Paso {step.index + 1} {'listo' if step.status == 'done' else 'falló'}: "
                f"{step.result[:160]}",
            )
            self._save(run)

    def _approve_plan(self, run: CoworkRun, cancel: threading.Event) -> bool:
        """«Modo plan»: show the plan and wait for the owner's yes (decision
        on step 0 over HTTP, -1 here) before doing anything."""
        box: "queue.Queue[bool]" = queue.Queue()
        with self._lock:
            self._decisions[(run.id, -1)] = box
        run.status = "waiting_plan"
        self._save(run)
        self._event(
            run, "plan_approval", text=f"¿Sigo este plan? {len(run.steps)} pasos."
        )
        self._notify(
            run, f"Cowork «{run.title}»: el plan espera su visto bueno.", force=True
        )
        try:
            approved = box.get(timeout=self.approval_timeout)
        except queue.Empty:
            approved = False
        finally:
            with self._lock:
                self._decisions.pop((run.id, -1), None)
        approved = approved and not cancel.is_set()
        self._audit(run).record("plan_decision", approved=approved)
        run.status = "running" if approved else "cancelled"
        return approved

    def _ask_owner(
        self,
        run: CoworkRun,
        step: CoworkStep,
        reasons: List[str],
        cancel: threading.Event,
    ) -> bool:
        box: "queue.Queue[bool]" = queue.Queue()
        with self._lock:
            self._decisions[(run.id, step.index)] = box
        why = " ".join(reasons)
        self._notify(
            run,
            f"Cowork «{run.title}» espera su visto bueno: {step.text}. {why} "
            f"Responda en la app o con: sergio cowork aprobar {run.id} {step.index + 1}",
            force=True,
        )
        step.status = "waiting_approval"
        run.status = "waiting_approval"
        self._save(run)
        self._event(
            run, "approval", step=step.index, text=f"¿Hago esto? {step.text} — {why}"
        )
        try:
            approved = box.get(timeout=self.approval_timeout)
        except queue.Empty:
            approved = False
        finally:
            with self._lock:
                self._decisions.pop((run.id, step.index), None)
        if cancel.is_set():
            approved = False
        step.status = "pending"
        run.status = "running" if not cancel.is_set() else "cancelled"
        return approved

    @staticmethod
    def _prompt(run: CoworkRun, step: CoworkStep) -> str:
        done = [f"- {s.text} → {s.result}" for s in run.steps if s.status == "done"]
        each = (
            "Hazlo para cada uno de: " + "; ".join(step.for_each)
            if step.for_each
            else ""
        )
        parts = [
            "Trabajas en modo Cowork: el usuario no está mirando. Haz el paso con las "
            "herramientas, sin pedir confirmación, y sin enviar mensajes a nadie.",
            f"Objetivo del usuario: «{run.goal}»",
            run.context,
            (
                "Indicaciones del usuario mientras trabajas (síguelas; la más "
                "reciente manda):\n" + "\n".join(f"- {n['text']}" for n in run.notes)
            )
            if run.notes
            else "",
            ("Ya hecho:\n" + "\n".join(done)) if done else "",
            f"Paso actual: {step.text}",
            each,
            f"Cómo comprobarlo: {step.check}" if step.check else "",
            END_RULE,
        ]
        return "\n".join(p for p in parts if p)

    def _finish(self, run: CoworkRun, audit: AuditTrail) -> None:
        if run.status in ("running", "waiting_approval"):
            ok = [s.status == "done" for s in run.steps]
            run.status = (
                "done" if ok and all(ok) else ("partial" if any(ok) else "failed")
            )
        results = [s.result for s in run.steps if s.status == "done" and s.result]
        if not run.summary:
            run.summary = {
                "done": results[-1] if results else "Hecho.",
                "partial": "Hice una parte: " + (results[-1] if results else ""),
                "failed": "No pude completarlo.",
                "capped": f"Me detuve al llegar al tope de {run.max_actions} acciones.",
                "cancelled": "Cancelado.",
            }.get(run.status, run.status)
        audit.record(
            "finished", status=run.status, summary=run.summary, actions=run.actions_used
        )
        if run.status in ("done", "partial"):
            from openjarvis.connectome.brain import remember_exchange

            remember_exchange(run.goal, run.summary, channel="cowork")
        self._save(run)
        self._event(run, "finished", text=run.summary, status=run.status)
        self._notify(
            run, f"Cowork «{run.title or run.goal[:40]}»: {run.summary}", force=True
        )

    # -- plumbing -------------------------------------------------------------
    def _audit(self, run: CoworkRun) -> AuditTrail:
        return self.audit(run.id)

    def _save(self, run: CoworkRun) -> None:
        run.updated = time.time()
        path = self.root / run.id / "run.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(run.to_dict(), ensure_ascii=False, indent=1), "utf-8"
            )
            tmp.replace(path)
        except OSError:
            pass

    def _load_previous(self) -> None:
        """Runs from before a restart: shown, and marked interrupted if unfinished."""
        try:
            folders = sorted(
                p for p in self.root.iterdir() if (p / "run.json").is_file()
            )
        except OSError:
            return
        for folder in folders[-100:]:
            try:
                data = json.loads((folder / "run.json").read_text("utf-8"))
                data.pop("progress", None)
                data.pop("waiting", None)
                run = CoworkRun.from_dict(data)
            except (OSError, ValueError, TypeError):
                continue
            if run.status not in FINAL_STATES:
                run.status = "interrupted"
                run.summary = run.summary or "Se interrumpió (Sergio se reinició)."
            self.runs[run.id] = run

    def _event(self, run: CoworkRun, kind: str, **data: Any) -> None:
        event = {"type": kind, "run": run.id, "ts": round(time.time(), 3), **data}
        event["status"] = data.get("status", run.status)
        event["actions_used"] = run.actions_used
        with self._lock:
            boxes = list(self._listeners.get(run.id, []))
        for box in boxes:
            box.put(event)

    def _notify(self, run: CoworkRun, text: str, *, force: bool = False) -> None:
        if self.send_owner is None:
            return
        now = time.time()
        if not force and now - self._last_notice.get(run.id, 0) < self.notify_every:
            return
        self._last_notice[run.id] = now
        try:
            sent = self.send_owner(text)
        except Exception:  # noqa: BLE001 - a notice never stops the work
            sent = False
        self._audit(run).record("notified", sent=bool(sent), text=text[:300])


def _default_runner() -> StepRunner:
    from openjarvis.cowork.runner import sdk_step_runner

    return sdk_step_runner


__all__ = [
    "ActionBudget",
    "BudgetExhausted",
    "CoworkEngine",
    "CoworkRun",
    "CoworkStep",
    "DEFAULT_MAX_ACTIONS",
    "step_status",
    "steps_from_plan",
]

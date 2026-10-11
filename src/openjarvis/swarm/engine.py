"""Agent Swarm: a burst of parallel sub-agents for one huge task.

Modelled on Kimi's Agent Swarm. An *orchestrator* reads the task, invents
the specialist roles it needs and splits the work into independent
sub-tasks; a pool of *sub-agents* runs them at the same time, each with its
own tools and its own budget; a *supervisor* reads every result, checks
that they do not contradict each other and writes one report. Then the
swarm dissolves: nothing keeps running and nothing watches your files the
next day (that is what Nodes are for).

Documents handed in (50 contracts, a folder of invoices…) each get their own
reading sub-agent, so nothing is skipped.

The swarm never reaches other people: messaging, calls, shells, commits and
spawning more agents are withheld from every sub-agent (the same list as
Cowork), and each sub-agent has a hard cap on tool calls.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_SUBTASKS = 100
DEFAULT_PARALLEL = 8
MAX_PARALLEL = 32
SUBAGENT_BUDGET = 12  # tool calls per sub-agent
RESULT_CHARS = 6000  # each result as the supervisor reads it
REPORT_INPUT_CHARS = 160_000
# Tools a sub-agent may be given (the rest of the toolbox stays home).
SWARM_TOOLS = (
    "web_search",
    "http_request",
    "browser_navigate",
    "browser_extract",
    "pdf_extract",
    "file_read",
    "python_run",
    "code_interpreter",
    "calculator",
    "knowledge_search",
    "think",
)
DEFAULT_TOOLS = ("web_search", "think")
FINAL = ("done", "failed", "cancelled")

Ask = Callable[..., Any]  # (prompt, **kw) -> parsed JSON
Runner = Callable[
    [str, List[str], int], Tuple[str, int]
]  # (prompt, tools, budget) -> (answer, calls)

PLAN_PROMPT = """Eres el orquestador de un enjambre de agentes (como Kimi Agent Swarm).
Tarea del usuario: «{task}»
{documents}
Divide la tarea en subtareas INDEPENDIENTES que puedan hacer a la vez varios \
subagentes especializados (máximo {max_subtasks}; usa tantas como de verdad \
acelere el trabajo, p. ej. una por producto, ciudad, fuente o sección). Inventa \
los roles especialistas que hagan falta (p. ej. «Investigador de precios», \
«Auditor de seguridad», «Extractor de cláusulas»). Herramientas posibles: {tools}.
{per_document}
Devuelve SOLO JSON:
{{"titulo": "nombre corto", "roles": [{{"nombre": "...", "especialidad": "una frase"}}],
 "subtareas": [{{"titulo": "...", "rol": "nombre de un rol", "instruccion": "qué hacer exactamente",
   "herramientas": ["..."], "entrega": "formato exacto del resultado"}}],
 "por_documento": "qué extraer de CADA documento (solo si hay documentos)",
 "sintesis": "cómo debe unir el supervisor los resultados"}}
Nunca planifiques enviar mensajes, llamar, publicar, comprar ni borrar nada."""

SUB_PROMPT = """Eres «{role}», un subagente de un enjambre ({index} de {total}).
Tarea global del enjambre: «{task}»
Tu parte: {instruction}
{document}Entrega: {deliver}
Trabaja solo en tu parte, rápido y con precisión. Cita la URL de lo que \
busques. Si algo no se puede averiguar, dilo; no inventes datos. No envíes \
mensajes ni compres ni borres nada."""

SUPERVISOR_PROMPT = """Eres el supervisor del enjambre. Tarea: «{task}»
Cómo unir: {synthesis}
Estos son los resultados de {n} subagentes (algunos pueden haber fallado):
{results}
Une todo en UN informe final completo en Markdown (en el idioma de la tarea), \
con tablas cuando ayuden. Comprueba que no haya contradicciones entre \
subagentes: si las hay, resuélvelas con la evidencia o márcalas. No inventes \
nada que no esté en los resultados.
Devuelve SOLO JSON: {{"informe": "markdown", "contradicciones": ["..."], "huecos": ["lo que faltó"]}}"""


@dataclass
class Document:
    name: str
    path: str


@dataclass
class SubTask:
    id: int
    title: str
    role: str
    instruction: str
    deliver: str = ""
    tools: List[str] = field(default_factory=list)
    document: str = ""  # a document's name, when it reads one
    status: str = "queued"  # queued · running · done · failed · cancelled
    result: str = ""
    tool_calls: int = 0
    sources: List[str] = field(default_factory=list)
    started: float = 0.0
    ended: float = 0.0


@dataclass
class SwarmRun:
    id: str
    task: str
    parallel: int = DEFAULT_PARALLEL
    title: str = ""
    status: str = (
        "planning"  # planning · running · synthesizing · done · failed · cancelled
    )
    roles: List[Dict[str, str]] = field(default_factory=list)
    subtasks: List[SubTask] = field(default_factory=list)
    synthesis: str = ""
    report: str = ""
    contradictions: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    documents: List[Document] = field(default_factory=list)
    error: str = ""
    created: float = field(default_factory=time.time)
    ended: float = 0.0

    def counts(self) -> Dict[str, int]:
        out = {"queued": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
        for s in self.subtasks:
            out[s.status] = out.get(s.status, 0) + 1
        return out

    def to_dict(self, results: bool = True) -> Dict[str, Any]:
        data = asdict(self)
        data["counts"] = self.counts()
        data["tool_calls"] = sum(s.tool_calls for s in self.subtasks)
        data["sources"] = sorted({u for s in self.subtasks for u in s.sources})[:200]
        data["elapsed"] = round((self.ended or time.time()) - self.created, 1)
        if not results:
            for s in data["subtasks"]:
                s["result"] = s["result"][:240]
        return data


def _home() -> Path:
    return (
        Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis") / "swarm"
    )


def _clean(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


URL = re.compile(r"https?://[^\s)\]>»\"']+")


def sources_in(text: str) -> List[str]:
    found: List[str] = []
    for url in URL.findall(text or ""):
        url = url.rstrip(".,;:")
        if url not in found:
            found.append(url)
    return found[:20]


def allowed_tools(names: Any) -> List[str]:
    tools = [t for t in names or [] if isinstance(t, str) and t in SWARM_TOOLS]
    return list(dict.fromkeys(tools)) or list(DEFAULT_TOOLS)


def plan_subtasks(
    task: str, data: Any, documents: List[Document]
) -> Tuple[str, List[Dict[str, str]], List[SubTask], str]:
    """The orchestrator's JSON, checked: real tools, bounded size, one reader
    per document (whatever the plan said)."""
    data = data if isinstance(data, dict) else {}
    roles = []
    for r in data.get("roles") or []:
        if isinstance(r, dict) and _clean(r.get("nombre"), 60):
            roles.append(
                {
                    "nombre": _clean(r.get("nombre"), 60),
                    "especialidad": _clean(r.get("especialidad"), 160),
                }
            )
    subtasks: List[SubTask] = []
    if documents:
        what = (
            _clean(data.get("por_documento"), 600)
            or "Lee el documento entero y extrae lo que pide la tarea."
        )
        tools = ["pdf_extract", "file_read", "think"]
        for doc in documents[:MAX_SUBTASKS]:
            subtasks.append(
                SubTask(
                    id=len(subtasks) + 1,
                    title=f"Leer «{doc.name}»",
                    role="Lector de documentos",
                    instruction=what,
                    deliver="Los datos pedidos, con la página o sección de donde salen.",
                    tools=tools,
                    document=doc.name,
                )
            )
        if not any(r["nombre"] == "Lector de documentos" for r in roles):
            roles.insert(
                0,
                {
                    "nombre": "Lector de documentos",
                    "especialidad": "Lee un documento y extrae lo pedido",
                },
            )
    for raw in data.get("subtareas") or data.get("subtasks") or []:
        if len(subtasks) >= MAX_SUBTASKS:
            break
        if not isinstance(raw, dict):
            continue
        instruction = _clean(raw.get("instruccion") or raw.get("instruction"), 1200)
        if not instruction:
            continue
        subtasks.append(
            SubTask(
                id=len(subtasks) + 1,
                title=_clean(raw.get("titulo") or raw.get("title") or instruction, 90),
                role=_clean(raw.get("rol") or raw.get("role"), 60) or "Especialista",
                instruction=instruction,
                deliver=_clean(raw.get("entrega") or raw.get("deliver"), 300),
                tools=allowed_tools(raw.get("herramientas") or raw.get("tools")),
            )
        )
    if not subtasks:  # the orchestrator failed: one generalist does it all
        subtasks.append(
            SubTask(
                id=1,
                title=_clean(task, 90),
                role="Generalista",
                instruction=task,
                tools=list(DEFAULT_TOOLS),
            )
        )
    title = _clean(data.get("titulo") or data.get("title"), 80) or _clean(task, 80)
    synthesis = (
        _clean(data.get("sintesis"), 600) or "Une los resultados en un informe claro."
    )
    return title, roles, subtasks, synthesis


def _ask_default(prompt: str, **kw: Any) -> Any:
    from openjarvis.coach.brain import ask

    return ask(prompt, **kw)


def _runner_default(prompt: str, tools: List[str], budget: int) -> Tuple[str, int]:
    from openjarvis.cowork.runner import sdk_step_runner

    return sdk_step_runner(prompt, tools, budget)


class SwarmEngine:
    """Starts swarms, runs them in threads, streams their events."""

    def __init__(
        self,
        ask: Optional[Ask] = None,
        runner: Optional[Runner] = None,
        home: Optional[Path] = None,
    ) -> None:
        self.ask = ask or _ask_default
        self.runner = runner or _runner_default
        self.home = home or _home()
        self._runs: Dict[str, SwarmRun] = {}
        self._cancel: Dict[str, threading.Event] = {}
        self._boxes: Dict[str, List["queue.Queue[Dict[str, Any]]"]] = {}
        self._lock = threading.Lock()
        self._load_previous()

    # -- public -------------------------------------------------------------------
    def start(
        self,
        task: str,
        parallel: int = DEFAULT_PARALLEL,
        documents: Optional[List[Document]] = None,
        background: bool = True,
    ) -> SwarmRun:
        task = " ".join((task or "").split())
        if not task:
            raise ValueError("Diga qué debe hacer el enjambre.")
        run = SwarmRun(
            id=f"sw_{uuid.uuid4().hex[:10]}",
            task=task[:4000],
            parallel=max(1, min(int(parallel or DEFAULT_PARALLEL), MAX_PARALLEL)),
            documents=list(documents or [])[:MAX_SUBTASKS],
        )
        with self._lock:
            self._runs[run.id] = run
            self._cancel[run.id] = threading.Event()
        if background:
            threading.Thread(
                target=self._work, args=(run,), daemon=True, name=f"swarm-{run.id}"
            ).start()
        else:
            self._work(run)
        return run

    def get(self, run_id: str) -> Optional[SwarmRun]:
        return self._runs.get(run_id)

    def list(self) -> List[SwarmRun]:
        return sorted(self._runs.values(), key=lambda r: r.created, reverse=True)

    def cancel(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        stop = self._cancel.get(run_id)
        if run is None or run.status in FINAL or stop is None:
            return False
        stop.set()
        return True

    def listen(self, run_id: str) -> "queue.Queue[Dict[str, Any]]":
        box: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        with self._lock:
            self._boxes.setdefault(run_id, []).append(box)
        return box

    def unlisten(self, run_id: str, box: "queue.Queue[Dict[str, Any]]") -> None:
        with self._lock:
            boxes = self._boxes.get(run_id, [])
            if box in boxes:
                boxes.remove(box)

    # -- the work -----------------------------------------------------------------
    def _event(self, run: SwarmRun, kind: str, **data: Any) -> None:
        event = {"type": kind, "run": run.id, "at": time.time(), **data}
        with self._lock:
            boxes = list(self._boxes.get(run.id, []))
        for box in boxes:
            box.put(event)

    def _work(self, run: SwarmRun) -> None:
        stop = self._cancel[run.id]
        try:
            docs = "\n".join(f"- {d.name}" for d in run.documents)
            prompt = PLAN_PROMPT.format(
                task=run.task,
                documents=f"Documentos entregados ({len(run.documents)}):\n{docs}"
                if docs
                else "",
                max_subtasks=MAX_SUBTASKS,
                tools=", ".join(SWARM_TOOLS),
                per_document="Habrá un subagente lector por documento: di en «por_documento» "
                "qué debe extraer cada uno; añade solo las subtareas extra que hagan falta (comparar, buscar fuera…)."
                if docs
                else "",
            )
            try:
                data = self.ask(prompt, effort="medium", deep=True)
            except Exception as exc:  # noqa: BLE001 - a failed plan still runs as one generalist
                logger.warning("swarm plan failed: %s", exc)
                data = {}
            run.title, run.roles, run.subtasks, run.synthesis = plan_subtasks(
                run.task, data, run.documents
            )
            run.status = "running"
            self._event(
                run,
                "planned",
                title=run.title,
                roles=run.roles,
                subtasks=[asdict(s) for s in run.subtasks],
            )
            with ThreadPoolExecutor(
                max_workers=run.parallel, thread_name_prefix=f"{run.id}-agent"
            ) as pool:
                for sub in run.subtasks:
                    pool.submit(self._sub, run, sub, stop)
            if stop.is_set():
                run.status = "cancelled"
                for s in run.subtasks:
                    if s.status in ("queued", "running"):
                        s.status = "cancelled"
                return
            run.status = "synthesizing"
            self._event(run, "synthesizing")
            self._synthesize(run)
            run.status = "done"
        except Exception as exc:  # noqa: BLE001
            logger.exception("swarm %s failed", run.id)
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"[:400]
        finally:
            run.ended = time.time()
            self._save(run)
            self._event(run, "finished", status=run.status)
            # Dissolved: nothing of the swarm keeps running.
            with self._lock:
                self._cancel.pop(run.id, None)

    def _sub(self, run: SwarmRun, sub: SubTask, stop: threading.Event) -> None:
        if stop.is_set():
            sub.status = "cancelled"
            return
        sub.status, sub.started = "running", time.time()
        self._event(
            run, "agent", id=sub.id, status="running", title=sub.title, role=sub.role
        )
        doc = next((d for d in run.documents if d.name == sub.document), None)
        prompt = SUB_PROMPT.format(
            role=sub.role,
            index=sub.id,
            total=len(run.subtasks),
            task=run.task,
            instruction=sub.instruction,
            document=f"Documento: «{doc.name}» en la ruta {doc.path}\n" if doc else "",
            deliver=sub.deliver or "un resultado concreto y verificable",
        )
        try:
            answer, calls = self.runner(prompt, sub.tools, SUBAGENT_BUDGET)
            sub.result, sub.tool_calls = str(answer or "").strip(), int(calls or 0)
            sub.status = "done" if sub.result else "failed"
            if not sub.result:
                sub.result = "No devolvió nada."
        except Exception as exc:  # noqa: BLE001 - one sub-agent failing never sinks the swarm
            sub.status, sub.result = (
                "failed",
                f"Falló: {type(exc).__name__}: {exc}"[:400],
            )
        sub.sources = sources_in(sub.result)
        sub.ended = time.time()
        self._event(
            run,
            "agent",
            id=sub.id,
            status=sub.status,
            tool_calls=sub.tool_calls,
            sources=sub.sources,
            preview=sub.result[:240],
            counts=run.counts(),
        )

    def _synthesize(self, run: SwarmRun) -> None:
        parts: List[str] = []
        room = REPORT_INPUT_CHARS
        for s in run.subtasks:
            block = f"### {s.id}. {s.title} ({s.role}) — {s.status}\n{s.result[:RESULT_CHARS]}"
            if len(block) > room:
                block = block[:room]
            parts.append(block)
            room -= len(block)
            if room <= 0:
                break
        try:
            data = self.ask(
                SUPERVISOR_PROMPT.format(
                    task=run.task,
                    synthesis=run.synthesis,
                    n=len(run.subtasks),
                    results="\n\n".join(parts),
                ),
                effort="medium",
                deep=True,
                max_tokens=24000,
            )
        except Exception as exc:  # noqa: BLE001 - the raw results are still a report
            logger.warning("swarm synthesis failed: %s", exc)
            data = {}
        data = data if isinstance(data, dict) else {}
        report = str(data.get("informe") or "").strip()
        if not report:
            report = f"# {run.title}\n\n" + "\n\n".join(parts)
        run.report = report
        run.contradictions = [
            _clean(c, 300) for c in data.get("contradicciones") or [] if _clean(c, 300)
        ][:20]
        run.gaps = [_clean(c, 300) for c in data.get("huecos") or [] if _clean(c, 300)][
            :20
        ]

    # -- history ------------------------------------------------------------------
    def _save(self, run: SwarmRun) -> None:
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            path = self.home / f"{run.id}.json"
            path.write_text(
                json.dumps(run.to_dict(), ensure_ascii=False), encoding="utf-8"
            )
            old = sorted(self.home.glob("sw_*.json"), key=lambda p: p.stat().st_mtime)
            for stale in old[:-50]:  # the last 50 reports stay
                stale.unlink(missing_ok=True)
        except OSError:
            logger.debug("swarm save failed", exc_info=True)

    def _load_previous(self) -> None:
        if not self.home.is_dir():
            return
        for path in sorted(self.home.glob("sw_*.json"))[-50:]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                subs = [
                    SubTask(
                        **{
                            k: v
                            for k, v in s.items()
                            if k in SubTask.__dataclass_fields__
                        }
                    )
                    for s in data.get("subtasks") or []
                ]
                docs = [
                    Document(**d)
                    for d in data.get("documents") or []
                    if isinstance(d, dict)
                ]
                fields = {
                    k: v
                    for k, v in data.items()
                    if k in SwarmRun.__dataclass_fields__
                    and k not in ("subtasks", "documents")
                }
                run = SwarmRun(**fields, subtasks=subs, documents=docs)
                if run.status not in FINAL:
                    run.status, run.error = "failed", "Se interrumpió al cerrar Sergio."
                self._runs[run.id] = run
            except (OSError, ValueError, TypeError):
                continue


__all__ = [
    "DEFAULT_PARALLEL",
    "Document",
    "MAX_PARALLEL",
    "MAX_SUBTASKS",
    "SWARM_TOOLS",
    "SubTask",
    "SwarmEngine",
    "SwarmRun",
    "allowed_tools",
    "plan_subtasks",
    "sources_in",
]

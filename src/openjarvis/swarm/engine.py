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

It supports 300 planned subtasks, at most 64 concurrent workers, and a shared
budget of 4,000 sub-agent tool calls per run. These limits do not establish
parity with Kimi K3's model, PARL training or runtime. A *scout* maps the ground first (what items
exist, where the good sources are) so the orchestrator splits real work.
You see each sub-agent's current tool live; a sub-agent that fails is
retried with backoff; and before you read the report, code checks it
(swarm/report.py): links must come from a sub-agent, figures must appear in
their results, every document must have been read. What does not check out
goes back to the supervisor once, and whatever still fails is listed at the
end of the report. Export it as Markdown, CSV or a Workspace page.

The swarm never reaches other people: messaging, calls, shells, commits and
spawning more agents are withheld from every sub-agent (the same list as
Cowork), and each sub-agent has a hard cap on tool calls.
"""

from __future__ import annotations

import inspect
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

MAX_SUBTASKS = 300
DEFAULT_PARALLEL = 8
MAX_PARALLEL = 64
SUBAGENT_BUDGET = 12  # tool calls per sub-agent
RUN_BUDGET = 4000  # tool calls for the whole swarm (scout included)
SCOUT_BUDGET = 6
RETRY_DELAYS = (2.0, 6.0)  # a failed sub-agent tries twice more
RESULT_CHARS = 6000  # each result as the supervisor reads it
REPORT_INPUT_CHARS = 160_000
ACTIVITY_KEEP = 80  # lines of the live feed kept per swarm
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
    "verified_math",
    "scene_reason",
    "knowledge_search",
    "think",
)
DEFAULT_TOOLS = ("web_search", "think")
FINAL = ("done", "failed", "cancelled")
NO_BUDGET = "Sin presupuesto: el enjambre llegó a su tope de llamadas a herramientas."

Ask = Callable[..., Any]  # (prompt, **kw) -> parsed JSON
Runner = Callable[
    ..., Tuple[str, int]
]  # (prompt, tools, budget[, on_tool]) -> (answer, calls)
OnTool = Callable[[str, Any], None]

SCOUT_PROMPT = """Eres el explorador de un enjambre de agentes. Antes de que el \
orquestador reparta el trabajo, mira el terreno con pocas búsquedas.
Tarea: «{task}»
No hagas la tarea. Devuelve solo el mapa, breve:
1. La lista COMPLETA de elementos que habrá que cubrir (productos, empresas, \
ciudades, fuentes, secciones…), uno por línea.
2. Las mejores fuentes, con su URL.
3. Las dificultades que verás venir (datos de pago, páginas que bloquean…)."""

PLAN_PROMPT = """Eres el orquestador de un enjambre de agentes (como Kimi Agent Swarm).
Tarea del usuario: «{task}»
{documents}{scout}
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

REVISE_PROMPT = """Eres el supervisor del enjambre. Tarea: «{task}»
Una comprobación por código de tu informe encontró cosas que NO salen de los \
resultados de los subagentes:
- Enlaces que ningún subagente citó: {links}
- Cifras que no aparecen en ningún resultado: {figures}
Corrige el informe: quita o sustituye cada enlace y cada cifra por lo que de \
verdad dicen los resultados; si no hay dato, dilo («no consta»). No añadas \
nada nuevo.
Informe:
{report}

Resultados de los subagentes:
{results}
Devuelve SOLO JSON: {{"informe": "markdown corregido"}}"""


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
    attempts: int = 0
    current: str = ""  # the tool it is using right now
    sources: List[str] = field(default_factory=list)
    started: float = 0.0
    ended: float = 0.0


@dataclass
class SwarmRun:
    id: str
    task: str
    parallel: int = DEFAULT_PARALLEL
    title: str = ""
    status: str = "planning"  # scouting · planning · running · synthesizing · checking · done · failed · cancelled
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
    budget: int = RUN_BUDGET
    explore: bool = False
    scout: str = ""  # the scout's map of the ground
    scout_calls: int = 0
    checks: Dict[str, Any] = field(default_factory=dict)
    revised: bool = False  # the supervisor corrected its report once
    # What is happening, in words, as it happens: {t, who, text}.
    activity: List[Dict[str, Any]] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        out = {"queued": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
        for s in self.subtasks:
            out[s.status] = out.get(s.status, 0) + 1
        return out

    def used(self) -> int:
        return self.scout_calls + sum(s.tool_calls for s in self.subtasks)

    def to_dict(self, results: bool = True) -> Dict[str, Any]:
        data = asdict(self)
        data["counts"] = self.counts()
        data["tool_calls"] = self.used()
        found = {u for s in self.subtasks for u in s.sources} | set(
            sources_in(self.scout)
        )
        data["sources"] = sorted(found)[:300]
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


_LIST_SPLIT = re.compile(r"\s*(?:,|;|/|\by\b|\be\b|\bo\b|\band\b)\s*", re.I)


def listed_items(text: str, limit: int = 60) -> List[str]:
    """The elements a task or a scout map lists: «(Python, Go, Rust)», «: a, b
    y c», or one per line (bullets / numbers). Short names only."""
    text = text or ""
    found: List[str] = []

    def add(raw: str) -> None:
        item = raw.strip(" .:*-•\t\"'«»")
        item = re.sub(r"^\d+[.)]\s*", "", item).strip()
        if 1 < len(item) <= 60 and item.lower() not in {f.lower() for f in found}:
            found.append(item)

    groups = [(g, False) for g in re.findall(r"\(([^()]{3,500})\)", text)]
    groups += [(g, True) for g in re.findall(r":\s*([^.:\n]{3,500})", text)]
    for group, names_only in groups:
        parts = [p.strip() for p in _LIST_SPLIT.split(group) if p and p.strip()]
        if len(parts) < 3 or any(len(p) > 60 for p in parts):
            continue
        # After a colon, only a list of names (Rust, Go, iPhone 17…), not of
        # attributes («ventajas, desventajas y precio»).
        if (
            names_only
            and sum(p[:1].isupper() or p[:1].isdigit() for p in parts)
            < len(parts) * 0.7
        ):
            continue
        for p in parts:
            add(p)
        if found:
            return found[:limit]
    for line in text.splitlines():
        if re.match(r"^\s*(?:[-*•]|\d+[.)])\s+\S", line) and len(line.strip()) <= 70:
            if "http" in line or line.rstrip().endswith(":"):  # links, headings
                continue
            add(line)
    return found[:limit] if len(found) >= 3 else []


def plan_subtasks(
    task: str, data: Any, documents: List[Document], scout: str = ""
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
    seen = set()
    for raw in data.get("subtareas") or data.get("subtasks") or []:
        if len(subtasks) >= MAX_SUBTASKS:
            break
        if not isinstance(raw, dict):
            continue
        instruction = _clean(raw.get("instruccion") or raw.get("instruction"), 1200)
        key = instruction.lower().strip(" .")
        if not instruction or key in seen:  # the same job twice is waste
            continue
        seen.add(key)
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
    items = [] if subtasks else listed_items(task) or listed_items(scout)
    if items:  # no plan, but the work lists its elements: one agent each
        roles = [
            {
                "nombre": "Investigador",
                "especialidad": "Cubre un elemento de la lista a fondo",
            }
        ]
        for item in items[:MAX_SUBTASKS]:
            subtasks.append(
                SubTask(
                    id=len(subtasks) + 1,
                    title=_clean(item, 90),
                    role="Investigador",
                    instruction=f"Haz la tarea solo para «{item}»: {task}",
                    deliver="Los datos pedidos sobre este elemento, con sus fuentes.",
                    tools=["web_search", "http_request", "think"],
                )
            )
    if not subtasks:  # nothing to split by: one generalist does it all
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


def _runner_default(
    prompt: str, tools: List[str], budget: int, on_tool: Optional[OnTool] = None
) -> Tuple[str, int]:
    """Sergio's agent with only these tools; each tool call is reported to
    *on_tool* as it starts (that is the live view of each sub-agent)."""
    import copy

    from openjarvis.core.config import load_config
    from openjarvis.core.events import EventType
    from openjarvis.cowork.runner import usable_tools
    from openjarvis.sdk import Jarvis

    if budget <= 0:
        return "", 0
    config = copy.deepcopy(load_config())
    config.agent.max_turns = max(1, min(int(config.agent.max_turns or 10), budget))
    jarvis = Jarvis(config=config)
    calls = {"n": 0}

    def started(event: Any) -> None:
        calls["n"] += 1
        if on_tool is not None:
            data = getattr(event, "data", {}) or {}
            on_tool(
                str(data.get("tool") or "?"), data.get("arguments", data.get("args"))
            )

    jarvis._bus.subscribe(EventType.TOOL_CALL_START, started)
    try:
        result = jarvis.ask_full(
            prompt, agent="native_react", tools=usable_tools(tools)
        )
    finally:
        try:
            jarvis.close()
        except Exception:  # noqa: BLE001
            logger.debug("Jarvis close failed", exc_info=True)
    used = max(calls["n"], len(result.get("tool_results") or []))
    return str(result.get("content") or ""), used


def _takes_on_tool(runner: Runner) -> bool:
    try:
        params = inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return False
    return "on_tool" in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


def describe(tool: str, args: Any) -> str:
    from openjarvis.nodes.worker import describe_tool

    return describe_tool(tool, args)


class SwarmEngine:
    """Starts swarms, runs them in threads, streams their events."""

    def __init__(
        self,
        ask: Optional[Ask] = None,
        runner: Optional[Runner] = None,
        home: Optional[Path] = None,
        retry_delays: Tuple[float, ...] = RETRY_DELAYS,
    ) -> None:
        self.ask = ask or _ask_default
        self.runner = runner or _runner_default
        self._live = _takes_on_tool(self.runner)
        self.retry_delays = tuple(retry_delays)
        self.home = home or _home()
        self._reserved: Dict[str, int] = {}
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
        scout: Optional[bool] = None,
        budget: int = RUN_BUDGET,
    ) -> SwarmRun:
        """*scout*: map the ground first (default: when no documents are given)."""
        task = " ".join((task or "").split())
        if not task:
            raise ValueError("Diga qué debe hacer el enjambre.")
        run = SwarmRun(
            id=f"sw_{uuid.uuid4().hex[:10]}",
            task=task[:4000],
            parallel=max(1, min(int(parallel or DEFAULT_PARALLEL), MAX_PARALLEL)),
            documents=list(documents or [])[:MAX_SUBTASKS],
            budget=max(1, min(int(budget or RUN_BUDGET), RUN_BUDGET)),
        )
        run.explore = (not run.documents) if scout is None else bool(scout)
        run.status = "scouting" if run.explore else "planning"
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

    def _say(self, run: SwarmRun, who: str, text: str) -> None:
        """One line of the live feed: who does what, right now."""
        line = {
            "t": round(time.time() - run.created, 1),
            "who": _clean(who, 60),
            "text": _clean(text, 220),
        }
        with self._lock:
            run.activity.append(line)
            del run.activity[:-ACTIVITY_KEEP]
        self._event(run, "say", **line)

    def _work(self, run: SwarmRun) -> None:
        stop = self._cancel[run.id]
        self._reserved[run.id] = 0
        try:
            if run.explore:
                self._scout(run)
                if stop.is_set():
                    run.status = "cancelled"
                    return
            run.status = "planning"
            self._event(run, "planning")
            self._say(run, "Orquestador", "Lee la tarea y decide cómo repartirla")
            docs = "\n".join(f"- {d.name}" for d in run.documents)
            prompt = PLAN_PROMPT.format(
                task=run.task,
                documents=f"Documentos entregados ({len(run.documents)}):\n{docs}"
                if docs
                else "",
                scout=f"\nExploración previa (un explorador ya miró el terreno; úsala para "
                f"repartir, p. ej. una subtarea por elemento):\n{run.scout[:6000]}\n"
                if run.scout
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
                run.task, data, run.documents, run.scout
            )
            names = ", ".join(r["nombre"] for r in run.roles[:4])
            self._say(
                run,
                "Orquestador",
                f"Repartió el trabajo en {len(run.subtasks)} "
                f"{'subtarea' if len(run.subtasks) == 1 else 'subtareas'}"
                + (f" para: {names}" if names else ""),
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
            done = run.counts()["done"]
            self._say(
                run, "Supervisor", f"Une {done} de {len(run.subtasks)} resultados"
            )
            self._synthesize(run)
            run.status = "checking"
            self._event(run, "checking")
            self._say(run, "Comprobación", "Coteja enlaces y cifras con las fuentes")
            self._check(run)
            c = run.checks or {}
            self._say(
                run,
                "Comprobación",
                f"{c.get('links', 0)} enlaces y {c.get('figures', 0)} cifras cotejados"
                + (" · el supervisor corrigió el informe" if run.revised else ""),
            )
            run.status = "done"
        except Exception as exc:  # noqa: BLE001
            logger.exception("swarm %s failed", run.id)
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"[:400]
        finally:
            run.ended = time.time()
            for s in run.subtasks:
                s.current = ""
            self._save(run)
            self._event(run, "finished", status=run.status)
            # Dissolved: nothing of the swarm keeps running.
            with self._lock:
                self._cancel.pop(run.id, None)
                self._reserved.pop(run.id, None)

    # -- the budget shared by every sub-agent ------------------------------------
    def _reserve(self, run: SwarmRun, want: int) -> int:
        with self._lock:
            left = run.budget - run.used() - self._reserved.get(run.id, 0)
            take = max(0, min(want, left))
            self._reserved[run.id] = self._reserved.get(run.id, 0) + take
            return take

    def _release(self, run: SwarmRun, taken: int) -> None:
        with self._lock:
            self._reserved[run.id] = max(0, self._reserved.get(run.id, 0) - taken)

    def _call(
        self, prompt: str, tools: List[str], budget: int, on_tool: Optional[OnTool]
    ):
        if self._live and on_tool is not None:
            return self.runner(prompt, tools, budget, on_tool=on_tool)
        return self.runner(prompt, tools, budget)

    def _scout(self, run: SwarmRun) -> None:
        """A quick look at the ground so the plan splits real work."""
        run.status = "scouting"
        self._event(run, "scouting")
        budget = self._reserve(run, SCOUT_BUDGET)

        self._say(run, "Explorador", "Mira el terreno antes de repartir")

        def seen(tool: str, args: Any) -> None:
            text = describe(tool, args)
            self._event(run, "scout_tool", text=text)
            self._say(run, "Explorador", text)

        try:
            answer, calls = self._call(
                SCOUT_PROMPT.format(task=run.task),
                ["web_search", "http_request", "think"],
                budget,
                seen,
            )
            run.scout = str(answer or "").strip()[:8000]
            run.scout_calls = min(int(calls or 0), budget) if budget else 0
        except Exception as exc:  # noqa: BLE001 - the plan works without a map too
            logger.info("swarm scout failed: %s", exc)
        finally:
            self._release(run, budget)
        self._event(run, "scouted", preview=run.scout[:400], tool_calls=run.scout_calls)
        found = len(listed_items(run.scout))
        self._say(
            run,
            "Explorador",
            f"Mapa listo: {found} elementos y sus fuentes"
            if found
            else (
                "Mapa listo" if run.scout else "Sin mapa: el orquestador reparte igual"
            ),
        )

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

        who = f"#{sub.id} {sub.role}"

        def seen(tool: str, args: Any) -> None:
            sub.current = describe(tool, args)
            self._event(run, "tool", id=sub.id, text=sub.current, tool=tool)
            self._say(run, who, sub.current)

        delays = (0.0, *self.retry_delays)
        for attempt, delay in enumerate(delays):
            if stop.is_set():
                sub.status = "cancelled"
                break
            if attempt:
                self._event(run, "retry", id=sub.id, attempt=attempt + 1, wait=delay)
                self._say(run, who, f"Lo intenta otra vez ({attempt + 1}.º intento)")
                if delay and stop.wait(delay):
                    sub.status = "cancelled"
                    break
            budget = self._reserve(run, SUBAGENT_BUDGET)
            if budget <= 0:
                sub.status, sub.result = "failed", NO_BUDGET
                break
            sub.attempts = attempt + 1
            try:
                answer, calls = self._call(prompt, sub.tools, budget, seen)
                sub.tool_calls += min(int(calls or 0), budget)
                sub.result = str(answer or "").strip()
                sub.status = "done" if sub.result else "failed"
                if not sub.result:
                    sub.result = "No devolvió nada."
            except Exception as exc:  # noqa: BLE001 - one sub-agent failing never sinks the swarm
                sub.status, sub.result = (
                    "failed",
                    f"Falló: {type(exc).__name__}: {exc}"[:400],
                )
            finally:
                self._release(run, budget)
            if sub.status == "done":
                break
        sub.current = ""
        sub.sources = sources_in(sub.result)
        sub.ended = time.time()
        if sub.status == "done":
            from openjarvis.swarm.report import summary_line

            first = summary_line(sub.result)
            self._say(run, who, f"Terminó: {first}" if first else "Terminó")
        elif sub.status == "failed":
            self._say(run, who, sub.result[:160])
        self._event(
            run,
            "agent",
            id=sub.id,
            status=sub.status,
            tool_calls=sub.tool_calls,
            attempts=sub.attempts,
            sources=sub.sources,
            preview=sub.result[:240],
            counts=run.counts(),
            used=run.used(),
        )

    def _results_text(self, run: SwarmRun) -> str:
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
        return "\n\n".join(parts)

    def _synthesize(self, run: SwarmRun) -> None:
        results = self._results_text(run)
        try:
            data = self.ask(
                SUPERVISOR_PROMPT.format(
                    task=run.task,
                    synthesis=run.synthesis,
                    n=len(run.subtasks),
                    results=results,
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
        if not report:  # the AI could not write: code orders the results
            from openjarvis.swarm.report import fallback_report

            report = fallback_report(
                run.title,
                run.task,
                [
                    {"title": s.title, "status": s.status, "result": s.result}
                    for s in run.subtasks
                ],
            )
            self._say(
                run,
                "Supervisor",
                "La IA no respondió; Sergio ordenó los resultados en una tabla sin inventar nada",
            )
        run.report = report
        run.contradictions = [
            _clean(c, 300) for c in data.get("contradicciones") or [] if _clean(c, 300)
        ][:20]
        run.gaps = [_clean(c, 300) for c in data.get("huecos") or [] if _clean(c, 300)][
            :20
        ]

    def _verify(self, run: SwarmRun, report: str) -> Dict[str, Any]:
        from openjarvis.swarm.report import verify_report

        counts = run.counts()
        return verify_report(
            report,
            [s.result for s in run.subtasks] + [run.scout],
            [u for s in run.subtasks for u in s.sources],
            [
                {"name": s.document, "status": s.status}
                for s in run.subtasks
                if s.document
            ],
            extra_evidence=[
                run.task,
                " ".join(str(v) for v in counts.values()),
                f"{len(run.subtasks)} {len(run.documents)} {run.used()}",
            ],
        )

    def _check(self, run: SwarmRun) -> None:
        """Code checks the report; what fails goes back to the supervisor once."""
        from openjarvis.swarm.report import check_note, issues

        checks = self._verify(run, run.report)
        bad = checks["links_unverified"] + checks["figures_unbacked"]
        if bad:
            try:
                data = self.ask(
                    REVISE_PROMPT.format(
                        task=run.task,
                        report=run.report[:60000],
                        links=", ".join(checks["links_unverified"]) or "ninguno",
                        figures=", ".join(checks["figures_unbacked"]) or "ninguna",
                        results=self._results_text(run),
                    ),
                    effort="medium",
                    deep=True,
                    max_tokens=24000,
                )
                fixed = (
                    str((data or {}).get("informe") or "").strip()
                    if isinstance(data, dict)
                    else ""
                )
            except Exception as exc:  # noqa: BLE001 - keep the first report, flagged
                logger.info("swarm revision failed: %s", exc)
                fixed = ""
            if fixed:
                again = self._verify(run, fixed)
                if issues(again) < issues(checks):
                    run.report, checks, run.revised = fixed, again, True
        run.checks = checks
        run.report = run.report.rstrip() + check_note(checks)

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
    "RUN_BUDGET",
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

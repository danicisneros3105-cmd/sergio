"""How a Node works: one turn at a time, in the background, by its rules.

A turn is a request (yours, a routine's, or an approved action) handed to an
agent with only the tools its rules allow. The answer may carry tags:

* ``<aprobacion categoria="…">what it wants to do</aprobacion>`` — it needs
  your OK for something its rules mark «ask»: the turn stops, you approve or
  deny in the Node, and on approval it does exactly that, once;
* ``<usuario>what it needs, with the URL</usuario>`` — take over: a login or
  a decision only you can make; «Listo» hands control back;
* ``<recordar>a lasting fact</recordar>`` — written to its memory.

The scheduler wakes every 30 s and runs the routines that are due.
"""

from __future__ import annotations

import copy
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from openjarvis.nodes.store import RULES, Node, NodeError, NodeStore, tools_for

logger = logging.getLogger(__name__)

TURN_BUDGET = 30  # tool calls per turn
TICK_SECONDS = 30

Runner = Callable[[str, List[str], int, Callable[[str, Any], None]], Tuple[str, int]]
Ask = Callable[..., Any]

TAG_APPROVAL = re.compile(
    r"<aprobaci[oó]n(?:\s+categor[ií]a=\"?([\w]+)\"?)?\s*>(.*?)</aprobaci[oó]n>",
    re.S | re.I,
)
TAG_USER = re.compile(r"<usuario>(.*?)</usuario>", re.S | re.I)
TAG_REMEMBER = re.compile(r"<recordar>(.*?)</recordar>", re.S | re.I)

LABEL = {
    "allow": "lo haces solo",
    "ask": "pides permiso antes",
    "block": "nunca lo haces",
}

TURN_PROMPT = """Eres «{name}», un Node de Sergio: un empleado digital persistente que trabaja \
para el usuario de forma continua, como un asistente de confianza a distancia.
Tu función: {instructions}

Tu computadora es la carpeta {computer} — guarda ahí todo lo que produzcas (informes, \
tablas, notas), con rutas completas; el usuario la ve en «Computadora».
Apps del usuario que puedes leer (con knowledge_search y su «source»): {apps}. No uses otras.

Tus reglas:
{rules}
Si para cumplir necesitas algo marcado «pides permiso antes», NO lo hagas: prepáralo \
(p. ej. el borrador exacto del correo) y escribe <aprobacion categoria="CLAVE">qué harás \
exactamente</aprobacion>, con CLAVE una de: {keys}. Luego termina.
Nunca envías mensajes ni correos tú mismo: los dejas como borrador para que el usuario los envíe.
Si necesitas que el usuario inicie sesión en una web o decida algo, escribe \
<usuario>qué necesitas, con la URL</usuario> y termina.
Si aprendes algo duradero sobre el usuario o el proyecto, añade <recordar>el hecho</recordar> (uno por etiqueta).

Lo que recuerdas:
{memory}

Conversación reciente:
{recent}

{source}: {request}
Responde al usuario en su idioma, tratándole de usted, breve y concreto: qué hiciste, \
qué encontraste y qué sigue."""

INTRO_PROMPT = """Eres «{name}», un Node nuevo de Sergio (un empleado digital 24/7).
Tu función: {instructions}
Preséntate al usuario en 3 o 4 frases, en español, tratándole de usted, cálido y concreto: \
quién eres, qué puedes hacer por él con tu propia computadora, memoria y apps, y pregúntale \
con qué empezar.
Devuelve SOLO JSON: {{"presentacion": "..."}}"""


def _node_runner(
    prompt: str, tools: List[str], budget: int, on_tool: Callable[[str, Any], None]
) -> Tuple[str, int]:
    """The default: Sergio's agent with only these tools; every tool call is
    reported to *on_tool* as it starts."""
    from openjarvis.core.config import load_config
    from openjarvis.core.events import EventType
    from openjarvis.cowork.runner import usable_tools
    from openjarvis.sdk import Jarvis

    config = copy.deepcopy(load_config())
    config.agent.max_turns = max(1, min(int(config.agent.max_turns or 10) * 3, budget))
    jarvis = Jarvis(config=config)
    calls = {"n": 0}

    def started(event: Any) -> None:
        calls["n"] += 1
        data = getattr(event, "data", {}) or {}
        on_tool(str(data.get("tool") or "?"), data.get("args"))

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
    return str(result.get("content") or ""), max(
        calls["n"], len(result.get("tool_results") or [])
    )


def _ask_default(prompt: str, **kw: Any) -> Any:
    from openjarvis.coach.brain import ask

    return ask(prompt, **kw)


def parse_answer(text: str) -> Dict[str, Any]:
    """Split an answer into what it says and what it asks for."""
    approvals = [
        ((m.group(1) or "messages").lower(), " ".join(m.group(2).split()))
        for m in TAG_APPROVAL.finditer(text)
    ]
    user = [" ".join(m.group(1).split()) for m in TAG_USER.finditer(text)]
    remember = [" ".join(m.group(1).split()) for m in TAG_REMEMBER.finditer(text)]
    say = TAG_REMEMBER.sub("", TAG_USER.sub("", TAG_APPROVAL.sub("", text))).strip()
    return {
        "say": say,
        "approvals": [a for a in approvals if a[1]],
        "user": [u for u in user if u],
        "remember": [r for r in remember if r],
    }


def describe_tool(tool: str, args: Any) -> str:
    args = args if isinstance(args, dict) else {}
    what = (
        args.get("query")
        or args.get("url")
        or args.get("path")
        or args.get("expression")
        or ""
    )
    labels = {
        "web_search": "Busca en la web",
        "http_request": "Lee una página",
        "browser_navigate": "Abre en su navegador",
        "browser_extract": "Lee la página abierta",
        "browser_screenshot": "Captura su navegador",
        "knowledge_search": "Busca en sus apps",
        "file_write": "Escribe un archivo",
        "file_read": "Lee un archivo",
        "pdf_extract": "Lee un PDF",
        "python_run": "Ejecuta código",
        "code_interpreter": "Ejecuta código",
        "calculator": "Calcula",
        "workspace": "Escribe en su Workspace",
        "memory_store": "Guarda un recuerdo",
        "memory_search": "Recuerda",
        "think": "Piensa",
    }
    text = labels.get(tool, tool)
    return f"{text}: {str(what)[:160]}" if what else text


class NodeWorker:
    """Runs Nodes' turns in background threads and their routines on time."""

    def __init__(
        self,
        store: Optional[NodeStore] = None,
        runner: Optional[Runner] = None,
        ask: Optional[Ask] = None,
    ) -> None:
        self.store = store or NodeStore()
        self.runner = runner or _node_runner
        self.ask = ask or _ask_default
        self._queues: Dict[str, List[Dict[str, Any]]] = {}
        self._busy: Dict[str, threading.Thread] = {}
        self._stop: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._ticker: Optional[threading.Thread] = None
        self._halt = threading.Event()

    # -- creating ---------------------------------------------------------------
    def create(self, name: str, instructions: str = "", **kw: Any) -> Node:
        node = self.store.create(name, instructions, **kw)
        self.store.log(
            node.id,
            "created",
            f"{node.name} recibió su computadora, su navegador y su memoria.",
        )
        self.store.say(node.id, "node", self.introduce(node))
        return node

    def introduce(self, node: Node) -> str:
        try:
            data = self.ask(
                INTRO_PROMPT.format(
                    name=node.name,
                    instructions=node.instructions or "ayudar en lo que haga falta",
                ),
                effort="low",
            )
            text = (
                str((data or {}).get("presentacion") or "").strip()
                if isinstance(data, dict)
                else ""
            )
        except Exception:  # noqa: BLE001 - a plain hello is fine
            text = ""
        return text or (
            f"Hola, soy {node.name}. Tengo mi propia computadora, un navegador y memoria a largo plazo, "
            "así que puedo seguir trabajando aunque usted cierre esto. Dígame qué proyecto llevo y con qué empiezo."
        )

    # -- turns ------------------------------------------------------------------
    def send(self, node_id: str, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise NodeError("Escriba algo para su Node.")
        node = self.store.get(node_id)
        if node is None:
            raise NodeError("No existe ese Node.")
        message = self.store.say(node_id, "user", text)
        self.enqueue(node_id, text, source="Encargo del usuario")
        return message

    def enqueue(
        self,
        node_id: str,
        request: str,
        source: str,
        extra: Iterable[str] = (),
        routine: str = "",
    ) -> None:
        job = {
            "request": request,
            "source": source,
            "extra": list(extra),
            "routine": routine,
        }
        with self._lock:
            self._queues.setdefault(node_id, []).append(job)
            thread = self._busy.get(node_id)
            if thread is not None and thread.is_alive():
                return
            self._stop[node_id] = threading.Event()
            thread = threading.Thread(
                target=self._drain, args=(node_id,), daemon=True, name=f"node-{node_id}"
            )
            self._busy[node_id] = thread
        thread.start()

    def busy(self, node_id: str) -> bool:
        thread = self._busy.get(node_id)
        return bool(thread and thread.is_alive())

    def wait(self, node_id: str, timeout: float = 10.0) -> None:
        thread = self._busy.get(node_id)
        if thread is not None:
            thread.join(timeout)

    def stop(self, node_id: str) -> bool:
        """Emergency stop: drop what is queued, discard the running turn's
        result and pause the Node until you resume it."""
        with self._lock:
            self._queues[node_id] = []
            stop = self._stop.get(node_id)
        if stop is not None:
            stop.set()
        node = self.store.get(node_id)
        if node is None:
            return False
        self.store.update(node_id, status="paused", doing="")
        self.store.log(
            node_id, "stopped", "Detenido por usted. No hará nada hasta que lo reanude."
        )
        return True

    def resume(self, node_id: str) -> None:
        self.store.update(node_id, status="idle", waiting="")
        self.store.log(node_id, "resumed", "Reanudado.")

    def _drain(self, node_id: str) -> None:
        while True:
            with self._lock:
                queue = self._queues.get(node_id) or []
                if not queue:
                    self._busy.pop(node_id, None)
                    return
                job = queue.pop(0)
                stop = self._stop.setdefault(node_id, threading.Event())
            try:
                self._turn(node_id, job, stop)
            except Exception as exc:  # noqa: BLE001 - one bad turn never kills the Node
                logger.exception("node %s turn failed", node_id)
                self.store.log(
                    node_id, "failed", f"Falló: {type(exc).__name__}: {exc}"[:400]
                )
                self.store.update(node_id, status="idle", doing="")

    def _prompt(self, node: Node, job: Dict[str, Any]) -> str:
        rules = "\n".join(
            f"- {RULES[k]['label']} ({k}): {LABEL[v]}"
            for k, v in node.rules.items()
            if k in RULES
        )
        approved = job.get("extra") or []
        if approved:
            rules += (
                "\nPara ESTE encargo el usuario ya aprobó: "
                + ", ".join(approved)
                + " — hazlo exactamente como lo describiste."
            )
        recent = self.store.messages(node.id, limit=12)
        lines = [
            f"{'Usuario' if m['role'] == 'user' else node.name}: {m['text'][:600]}"
            for m in recent
        ]
        return TURN_PROMPT.format(
            name=node.name,
            instructions=node.instructions or "ayudar al usuario en lo que pida",
            computer=self.store.computer(node.id),
            apps=", ".join(node.apps) or "ninguna todavía",
            rules=rules,
            keys=", ".join(k for k, v in node.rules.items() if v == "ask") or "ninguna",
            memory=self.store.memory(node.id)[-6000:] or "(nada todavía)",
            recent="\n".join(lines) or "(nada)",
            source=job["source"],
            request=job["request"],
        )

    def _turn(self, node_id: str, job: Dict[str, Any], stop: threading.Event) -> None:
        node = self.store.get(node_id)
        if (
            node is None
            or node.status == "paused"
            and job["source"] != "Acción aprobada"
        ):
            return
        doing = job["request"][:140]
        self.store.update(node_id, status="working", doing=doing, waiting="")
        self.store.log(
            node_id,
            "started",
            doing,
            source=job["source"],
            routine=job.get("routine", ""),
        )

        def on_tool(tool: str, args: Any) -> None:
            if not stop.is_set():
                line = describe_tool(tool, args)
                self.store.update(node_id, doing=line)
                self.store.log(node_id, "tool", line, tool=tool)

        tools = tools_for(node.rules, job.get("extra") or [])
        answer, calls = self.runner(
            self._prompt(node, job), tools, TURN_BUDGET, on_tool
        )
        if stop.is_set():
            self.store.log(
                node_id, "discarded", "Resultado descartado: lo detuvo usted."
            )
            return
        parsed = parse_answer(answer or "")
        if parsed["remember"] and node.rules.get("memory") != "block":
            for fact in self.store.remember(node_id, parsed["remember"]):
                self.store.log(node_id, "memory", f"Recordará: {fact}")
        status, waiting = "idle", ""
        for category, what in parsed["approvals"]:
            if node.rules.get(category) == "block":
                self.store.log(
                    node_id, "blocked", f"Quería «{what}», pero sus reglas lo prohíben."
                )
                continue
            item = self.store.request_approval(node_id, category, what, job["request"])
            self.store.log(
                node_id,
                "approval",
                what,
                approval=item["id"],
                category=item["category"],
            )
            status = "waiting_approval"
        if parsed["user"]:
            waiting = parsed["user"][0]
            self.store.log(node_id, "needs_you", waiting)
            status = "needs_you"
        say = parsed["say"] or (
            "Necesito su aprobación." if status == "waiting_approval" else "Hecho."
        )
        self.store.say(node_id, "node", say, source=job["source"], tool_calls=calls)
        self.store.log(node_id, "done", say[:300], tool_calls=calls)
        self.store.update(node_id, status=status, doing="", waiting=waiting)

    # -- you, in the loop ---------------------------------------------------------
    def decide(self, node_id: str, approval_id: str, approve: bool) -> Dict[str, Any]:
        item = self.store.decide(node_id, approval_id, approve)
        if item is None:
            raise NodeError("Esa aprobación ya no está pendiente.")
        pending = [a for a in self.store.approvals(node_id) if a["status"] == "pending"]
        if approve:
            self.store.log(node_id, "approved", item["what"])
            if item["category"] in ("messages", "delete"):
                # Never done by a Node: the draft is yours to send or do.
                self.store.say(
                    node_id,
                    "node",
                    f"Aprobado. Le dejo esto listo para que usted lo haga: {item['what']}",
                )
            else:
                self.enqueue(
                    node_id,
                    item["what"],
                    source="Acción aprobada",
                    extra=[item["category"]],
                )
        else:
            self.store.log(node_id, "denied", item["what"])
            self.store.say(node_id, "node", "Entendido, no lo haré.")
        if not pending:
            node = self.store.get(node_id)
            if node and node.status == "waiting_approval":
                self.store.update(node_id, status="idle")
        return item

    def hand_back(self, node_id: str, note: str = "") -> None:
        """Take over finished: the Node continues where it stopped."""
        node = self.store.get(node_id)
        if node is None:
            raise NodeError("No existe ese Node.")
        what = node.waiting
        self.store.update(node_id, status="idle", waiting="")
        self.store.log(node_id, "handed_back", "Usted le devolvió el control.")
        self.enqueue(
            node_id,
            f"El usuario ya hizo lo que pediste ({what}). {note}".strip(),
            source="Continúa",
        )

    # -- routines -----------------------------------------------------------------
    def tick(self, now: Optional[float] = None) -> int:
        now = now or time.time()
        started = 0
        for node in self.store.all():
            if node.status == "paused":
                continue
            for routine in node.routines:
                if routine.due(now):
                    self.store.mark_routine(node.id, routine.id, now)
                    self.enqueue(
                        node.id, routine.task, source="Rutina", routine=routine.id
                    )
                    started += 1
        return started

    def start(self) -> None:
        if self._ticker and self._ticker.is_alive():
            return
        self._halt.clear()

        def loop() -> None:
            while not self._halt.wait(TICK_SECONDS):
                try:
                    self.tick()
                except Exception:  # noqa: BLE001
                    logger.exception("node scheduler tick failed")

        self._ticker = threading.Thread(
            target=loop, daemon=True, name="nodes-scheduler"
        )
        self._ticker.start()

    def shutdown(self) -> None:
        self._halt.set()


__all__ = ["NodeWorker", "describe_tool", "parse_answer"]

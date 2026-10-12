"""How a Node works: one turn at a time, in the background, by its rules.

A turn is a request (yours, a routine's, a trigger's, an approved action)
handed to an agent with only the tools its rules allow. The model writes;
**code** does the rest. Its answer may carry tags, which code reads:

* ``<aprobacion categoria="…">what it wants to do</aprobacion>`` — something
  its rules mark «ask»: the turn stops, you approve or deny;
* ``<usuario>what it needs, with the URL</usuario>`` — take over;
* ``<recordar>a lasting fact</recordar>`` — written to its memory;
* ``<cli>git log -5</cli>``, ``<mcp servidor="s" herramienta="t">{json}</mcp>``,
  ``<api nombre="n" metodo="GET" ruta="/x">{json}</api>`` — run by code
  (connections.py) under the rules; the real output comes back to the Node
  in the next round (at most four rounds per request);
* ``<enjambre>a huge task</enjambre>`` — an Agent Swarm, whose report comes
  back to the Node when it is done.

After every answer code checks it: files it claims to have saved must exist
in its computer, or the answer says so. Routines that watch a page or an app
are checked by code too (skills.py); the model only wakes on a real change.
"""

from __future__ import annotations

import copy
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from openjarvis.nodes import connections, skills
from openjarvis.nodes.store import (
    MAIN_THREAD,
    RULES,
    TONES,
    Node,
    NodeError,
    NodeStore,
    tools_for,
)

logger = logging.getLogger(__name__)

TURN_BUDGET = 30  # tool calls per round
MAX_ROUNDS = 4  # model ↔ code rounds per request
MAX_ACTIONS = 6  # tagged actions per round
TICK_SECONDS = 30

Runner = Callable[[str, List[str], int, Callable[[str, Any], None]], Tuple[str, int]]
Ask = Callable[..., Any]

TAG_APPROVAL = re.compile(
    r"<aprobaci[oó]n(?:\s+categor[ií]a=\"?([\w]+)\"?)?\s*>(.*?)</aprobaci[oó]n>",
    re.S | re.I,
)
TAG_USER = re.compile(r"<usuario>(.*?)</usuario>", re.S | re.I)
TAG_REMEMBER = re.compile(r"<recordar>(.*?)</recordar>", re.S | re.I)
TAG_CLI = re.compile(r"<cli>(.*?)</cli>", re.S | re.I)
TAG_MCP = re.compile(r"<mcp\s+([^>]*)>(.*?)</mcp>", re.S | re.I)
TAG_API = re.compile(r"<api\s+([^>]*?)(?:/>|>(.*?)</api>)", re.S | re.I)
TAG_SWARM = re.compile(r"<enjambre>(.*?)</enjambre>", re.S | re.I)
ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
SAVE_VERB = re.compile(
    r"\b(guard|dej|cre|escrib|export|sav|wrote|writ|creat|stor)\w*", re.I
)
FILE_NAME = re.compile(
    r"[\w\-./]+\.(?:md|txt|csv|json|html|pdf|xlsx|docx|py|png|jpg)\b", re.I
)

LABEL = {
    "allow": "lo haces solo",
    "ask": "pides permiso antes",
    "block": "nunca lo haces",
}

TURN_PROMPT = """Eres «{name}», un Node de Sergio: un empleado digital persistente que trabaja \
para el usuario de forma continua, como un asistente de confianza a distancia.
Tu función: {instructions}
Tu forma de hablar: {tone}.

Tu computadora es la carpeta {computer} — guarda ahí todo lo que produzcas (informes, \
tablas, notas), con rutas completas; el usuario la ve en «Computadora».
Apps del usuario (con knowledge_search y su «source»): {apps}. No uses otras. «escritura» \
significa que puedes preparar cambios en ella, siempre con aprobación.

Tus reglas:
{rules}
Si para cumplir necesitas algo marcado «pides permiso antes», NO lo hagas: prepáralo \
(p. ej. el borrador exacto del correo) y escribe <aprobacion categoria="CLAVE">qué harás \
exactamente</aprobacion>, con CLAVE una de: {keys}. Luego termina.
Nunca envías mensajes ni correos tú mismo: los dejas como borrador para que el usuario los envíe.
Si necesitas que el usuario inicie sesión en una web o decida algo, escribe \
<usuario>qué necesitas, con la URL</usuario> y termina.
Si aprendes algo duradero sobre el usuario o el proyecto, añade <recordar>el hecho</recordar>.
{connections}
Nunca inventes resultados: si no lo comprobaste con una herramienta, dilo.

Lo que recuerdas:
{memory}

Conversación reciente:
{recent}

{source}: {request}
Responde al usuario en su idioma, tratándole de usted: qué hiciste, qué encontraste y qué sigue."""

CONNECTIONS_HELP = """Acciones que ejecuta el sistema por ti (escribe la etiqueta y termina; \
te llegará el resultado real):
{lines}"""

INTRO_PROMPT = """Eres «{name}», un Node nuevo de Sergio (un empleado digital 24/7).
Tu función: {instructions}
Tu forma de hablar: {tone}.
Preséntate al usuario en 3 o 4 frases, en español, tratándole de usted: quién eres, qué \
puedes hacer por él con tu propia computadora, memoria y apps, y pregúntale con qué empezar.
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
        on_tool(str(data.get("tool") or "?"), data.get("arguments", data.get("args")))

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


def _attrs(text: str) -> Dict[str, str]:
    return {k.lower(): v for k, v in ATTR.findall(text or "")}


def parse_answer(text: str) -> Dict[str, Any]:
    """Split an answer into what it says and what it asks for."""
    text = text or ""
    approvals = [
        ((m.group(1) or "messages").lower(), " ".join(m.group(2).split()))
        for m in TAG_APPROVAL.finditer(text)
    ]
    user = [" ".join(m.group(1).split()) for m in TAG_USER.finditer(text)]
    remember = [" ".join(m.group(1).split()) for m in TAG_REMEMBER.finditer(text)]
    actions: List[Dict[str, Any]] = []
    for m in TAG_CLI.finditer(text):
        command = " ".join(m.group(1).split())
        if command:
            actions.append({"kind": "cli", "command": command})
    for m in TAG_MCP.finditer(text):
        a = _attrs(m.group(1))
        actions.append(
            {
                "kind": "mcp",
                "server": a.get("servidor") or a.get("server", ""),
                "tool": a.get("herramienta") or a.get("tool", ""),
                "args": (m.group(2) or "").strip(),
            }
        )
    for m in TAG_API.finditer(text):
        a = _attrs(m.group(1))
        actions.append(
            {
                "kind": "api",
                "name": a.get("nombre") or a.get("name", ""),
                "method": (a.get("metodo") or a.get("method") or "GET").upper(),
                "path": a.get("ruta") or a.get("path", "/"),
                "body": (m.group(2) or "").strip(),
            }
        )
    for m in TAG_SWARM.finditer(text):
        task = " ".join(m.group(1).split())
        if task:
            actions.append({"kind": "swarm", "task": task})
    say = text
    for tag in (
        TAG_APPROVAL,
        TAG_USER,
        TAG_REMEMBER,
        TAG_CLI,
        TAG_MCP,
        TAG_API,
        TAG_SWARM,
    ):
        say = tag.sub("", say)
    return {
        "say": say.strip(),
        "approvals": [a for a in approvals if a[1]],
        "user": [u for u in user if u],
        "remember": [r for r in remember if r],
        "actions": actions[:MAX_ACTIONS],
    }


def describe_tool(tool: str, args: Any) -> str:
    args = args if isinstance(args, dict) else {}
    what = (
        args.get("query")
        or args.get("url")
        or args.get("path")
        or args.get("file_path")
        or args.get("filename")
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
        "screen_read": "Mira su pantalla",
        "desktop_action": "Usa su PC",
    }
    text = labels.get(tool, tool)
    return f"{text}: {str(what)[:160]}" if what else text


def action_category(action: Dict[str, Any]) -> str:
    return {"cli": "cli", "mcp": "mcp", "api": "api", "swarm": "swarm"}[action["kind"]]


def describe_action(action: Dict[str, Any]) -> str:
    kind = action["kind"]
    if kind == "cli":
        return f"Ejecutar «{action['command']}»"
    if kind == "mcp":
        return f"Usar {action['tool']} en el servidor MCP {action['server']}"
    if kind == "api":
        return f"{action['method']} {action['path']} en la API {action['name']}"
    return f"Lanzar un Agent Swarm: {action['task'][:200]}"


def unverified_files(say: str, existing: Iterable[str]) -> List[str]:
    """Files the answer says it saved (in a sentence with «guardé», «creé»,
    «saved»…) that are not in its computer."""
    have = {p.lower() for p in existing} | {
        p.rsplit("/", 1)[-1].lower() for p in existing
    }
    missing: List[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", say or ""):
        if not SAVE_VERB.search(sentence):
            continue
        for name in FILE_NAME.findall(sentence):
            name = name.strip("`«»\"'.")
            base = name.rsplit("/", 1)[-1].lower()
            if base not in have and name.lower() not in have and name not in missing:
                missing.append(name)
    return missing


class NodeWorker:
    """Runs Nodes' turns in background threads and their routines on time."""

    def __init__(
        self,
        store: Optional[NodeStore] = None,
        runner: Optional[Runner] = None,
        ask: Optional[Ask] = None,
        swarm: Any = None,
        notify: Optional[Callable[[str], Any]] = None,
        fetch: Optional[Callable[[str], str]] = None,
        app_items: Optional[Callable[..., List[Dict[str, str]]]] = None,
        http: Any = None,
    ) -> None:
        self.store = store or NodeStore()
        self.runner = runner or _node_runner
        self.ask = ask or _ask_default
        self.swarm = swarm  # a SwarmEngine (set by the server), for <enjambre>
        self.notify = notify  # send(text) to the owner, for decisions
        self.fetch = fetch or skills.fetch_text
        self.app_items = app_items or skills.app_items
        self.http = http
        self._queues: Dict[str, List[Dict[str, Any]]] = {}
        self._busy: Dict[str, threading.Thread] = {}
        self._stop: Dict[str, threading.Event] = {}
        self._checking: set[str] = set()
        self._lock = threading.Lock()
        self._ticker: Optional[threading.Thread] = None
        self._halt = threading.Event()

    # -- creating ---------------------------------------------------------------
    def create(
        self, name: str, instructions: str = "", template: str = "", **kw: Any
    ) -> Node:
        spec = skills.template(template) if template else None
        if spec:
            kw.setdefault("avatar", spec.get("avatar"))
            kw.setdefault("rules", spec.get("rules"))
            if not kw.get("apps") and spec.get("apps"):
                kw["apps"] = spec["apps"]
            instructions = instructions or spec["instructions"]
        node = self.store.create(name, instructions, template=template, **kw)
        self.store.log(
            node.id,
            "created",
            f"{node.name} recibió su computadora, su navegador y su memoria.",
        )
        for routine in (spec or {}).get("routines", []):
            if routine.get("kind") == "web" and not routine.get("url"):
                continue  # needs your URL: added from «Rutinas»
            try:
                self.store.add_routine(node.id, routine)
            except NodeError:
                continue
        self.store.say(node.id, "node", self.introduce(self.store.get(node.id) or node))
        return self.store.get(node.id) or node

    def introduce(self, node: Node) -> str:
        try:
            data = self.ask(
                INTRO_PROMPT.format(
                    name=node.name,
                    instructions=node.instructions or "ayudar en lo que haga falta",
                    tone=TONES[node.tone],
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
    def send(
        self, node_id: str, text: str, thread: str = MAIN_THREAD
    ) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise NodeError("Escriba algo para su Node.")
        node = self.store.get(node_id)
        if node is None:
            raise NodeError("No existe ese Node.")
        thread = self.store.thread_ok(node, thread)
        message = self.store.say(node_id, "user", text, thread=thread)
        self.enqueue(node_id, text, source="Encargo del usuario", thread=thread)
        return message

    def enqueue(
        self,
        node_id: str,
        request: str,
        source: str,
        extra: Iterable[str] = (),
        routine: str = "",
        thread: str = MAIN_THREAD,
        round_: int = 1,
    ) -> None:
        job = {
            "request": request,
            "source": source,
            "extra": list(extra),
            "routine": routine,
            "thread": thread,
            "round": round_,
        }
        with self._lock:
            self._queues.setdefault(node_id, []).append(job)
            thread_ = self._busy.get(node_id)
            if thread_ is not None and thread_.is_alive():
                return
            self._stop[node_id] = threading.Event()
            thread_ = threading.Thread(
                target=self._drain, args=(node_id,), daemon=True, name=f"node-{node_id}"
            )
            self._busy[node_id] = thread_
        thread_.start()

    def busy(self, node_id: str) -> bool:
        thread = self._busy.get(node_id)
        return bool(thread and thread.is_alive())

    def wait(self, node_id: str, timeout: float = 10.0) -> None:
        end = time.time() + timeout
        while time.time() < end:
            thread = self._busy.get(node_id)
            if thread is None or not thread.is_alive():
                with self._lock:
                    if not self._queues.get(node_id):
                        return
            if thread is not None:
                thread.join(0.05)
            else:
                time.sleep(0.02)

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
                if job.get("routine"):
                    self.store.routine_result(node_id, job["routine"], str(exc))

    def _connections_help(self, node: Node) -> str:
        lines = []
        cli = [c["command"] for c in node.connections.get("cli", [])]
        if cli and node.rules.get("cli") != "block":
            allowed = ", ".join(cli)
            lines.append(
                f"- Comandos permitidos, uno por etiqueta y sin tuberías: <cli>comando</cli>. Son: {allowed}"
            )
        mcp = [c["name"] for c in node.connections.get("mcp", [])]
        if mcp and node.rules.get("mcp") != "block":
            servers = ", ".join(mcp)
            tag = '<mcp servidor="NOMBRE" herramienta="HERRAMIENTA">{"arg": "valor"}</mcp>'
            lines.append(f"- Servidores MCP: {tag}. Servidores: {servers}")
        api = [c["name"] for c in node.connections.get("api", [])]
        if api and node.rules.get("api") != "block" and connections.api_allowed():
            names = ", ".join(api)
            tag = '<api nombre="NOMBRE" metodo="GET" ruta="/ruta">{json opcional}</api>'
            lines.append(f"- APIs: {tag}. APIs: {names}")
        if node.rules.get("swarm") != "block" and self.swarm is not None:
            lines.append(
                "- Para un trabajo enorme (decenas de fuentes o documentos a la vez): <enjambre>la tarea</enjambre>"
            )
        return CONNECTIONS_HELP.format(lines="\n".join(lines)) if lines else ""

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
        recent = self.store.messages(
            node.id, limit=12, thread=job.get("thread", MAIN_THREAD)
        )
        lines = [
            f"{'Usuario' if m['role'] == 'user' else node.name}: {m['text'][:600]}"
            for m in recent
        ]
        apps = ", ".join(
            f"{a} ({'escritura' if lvl == 'write' else 'lectura'})"
            for a, lvl in node.apps.items()
        )
        return TURN_PROMPT.format(
            name=node.name,
            instructions=node.instructions or "ayudar al usuario en lo que pida",
            tone=TONES.get(node.tone, TONES["cercano"]),
            computer=self.store.computer(node.id),
            apps=apps or "ninguna todavía",
            rules=rules,
            keys=", ".join(k for k, v in node.rules.items() if v == "ask") or "ninguna",
            connections=self._connections_help(node),
            memory=self.store.memory(node.id)[-6000:] or "(nada todavía)",
            recent="\n".join(lines) or "(nada)",
            source=job["source"],
            request=job["request"],
        )

    def _turn(self, node_id: str, job: Dict[str, Any], stop: threading.Event) -> None:
        node = self.store.get(node_id)
        if node is None or (
            node.status == "paused"
            and job["source"] not in ("Acción aprobada", "Resultado aprobado")
        ):
            return
        thread = job.get("thread", MAIN_THREAD)
        doing = job["request"][:140]
        self.store.update(node_id, status="working", doing=doing, waiting="")
        self.store.log(
            node_id,
            "started",
            doing,
            source=job["source"],
            routine=job.get("routine", ""),
            thread=thread,
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
        node = self.store.get(node_id) or node
        if parsed["remember"] and node.rules.get("memory") != "block":
            for fact in self.store.remember(node_id, parsed["remember"]):
                self.store.log(node_id, "memory", f"Recordará: {fact}")
        status, waiting = "idle", ""

        # Actions the model asked for: run by code under the rules.
        results: List[str] = []
        for action in parsed["actions"]:
            category = action_category(action)
            rule = node.rules.get(category, "block")
            if (
                action["kind"] == "api"
                and action["method"] != "GET"
                and category not in (job.get("extra") or [])
            ):
                rule = "ask" if rule != "block" else rule  # changing data always asks
            if rule == "block":
                self.store.log(
                    node_id,
                    "blocked",
                    f"Quería: {describe_action(action)}, pero sus reglas lo prohíben.",
                )
                results.append(f"{describe_action(action)}: bloqueado por las reglas.")
                continue
            if rule == "ask" and category not in (job.get("extra") or []):
                item = self.store.request_approval(
                    node_id,
                    category,
                    describe_action(action),
                    job["request"],
                    action=action,
                    thread=thread,
                )
                self.store.log(
                    node_id,
                    "approval",
                    item["what"],
                    approval=item["id"],
                    category=category,
                )
                status = "waiting_approval"
                continue
            results.append(self._run_action(node, action, thread))
        for category, what in parsed["approvals"]:
            if node.rules.get(category) == "block":
                self.store.log(
                    node_id, "blocked", f"Quería «{what}», pero sus reglas lo prohíben."
                )
                continue
            item = self.store.request_approval(
                node_id, category, what, job["request"], thread=thread
            )
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

        say = parsed["say"]
        missing = unverified_files(say, [f["path"] for f in self.store.files(node_id)])
        if missing:
            note = (
                "Comprobación: no encuentro en mi computadora "
                + ", ".join(f"«{m}»" for m in missing)
                + "; no lo dé por guardado."
            )
            say = f"{say}\n\n_{note}_" if say else note
            self.store.log(node_id, "verify", note)
        if say or not results:
            say = say or (
                "Necesito su aprobación." if status == "waiting_approval" else "Hecho."
            )
            self.store.say(
                node_id,
                "node",
                say,
                thread=thread,
                source=job["source"],
                tool_calls=calls,
            )
            self.store.log(node_id, "done", say[:300], tool_calls=calls)
        self.store.update(node_id, status=status, doing="", waiting=waiting)
        if job.get("routine"):
            self.store.routine_result(node_id, job["routine"])
        if status in ("waiting_approval", "needs_you"):
            self._tell_owner(node, waiting or "necesita su aprobación")

        # Real results go back to the Node for another round.
        real = [r for r in results if r]
        if real and job.get("round", 1) < MAX_ROUNDS and not stop.is_set():
            self.enqueue(
                node_id,
                f"{job['request']}\n\nResultados reales de lo que pediste ejecutar:\n"
                + "\n\n".join(real),
                source="Resultados",
                thread=thread,
                round_=job.get("round", 1) + 1,
                extra=job.get("extra") or [],
            )

    def _run_action(self, node: Node, action: Dict[str, Any], thread: str) -> str:
        kind = action["kind"]
        label = describe_action(action)
        self.store.update(node.id, doing=label)
        self.store.log(node.id, "tool", label, tool=kind)
        try:
            if kind == "cli":
                out = connections.run_cli(self.store, node, action["command"])
            elif kind == "mcp":
                out = connections.run_mcp(
                    node, action["server"], action["tool"], action.get("args") or ""
                )
            elif kind == "api":
                out = connections.run_api(
                    self.store,
                    node,
                    action["name"],
                    action["method"],
                    action["path"],
                    action.get("body"),
                    http=self.http,
                )
            else:
                return self._start_swarm(node, action["task"], thread)
        except NodeError as exc:
            out = f"No se pudo: {exc}"
        except Exception as exc:  # noqa: BLE001 - the Node hears what failed
            out = f"Falló: {type(exc).__name__}: {exc}"[:600]
        self.store.log(node.id, "result", f"{label} → {out[:200]}", tool=kind)
        return f"{label}:\n{out}"

    def _start_swarm(self, node: Node, task: str, thread: str) -> str:
        if self.swarm is None:
            return "Agent Swarm no está disponible ahora."
        run = self.swarm.start(task)
        self.store.log(
            node.id, "swarm", f"Lanzó un Agent Swarm: {task[:160]}", swarm=run.id
        )
        self.store.say(
            node.id,
            "node",
            f"Lancé un Agent Swarm para esto; le traigo su informe en cuanto termine. (/swarm/{run.id})",
            thread=thread,
        )

        def follow() -> None:
            while run.status not in ("done", "failed", "cancelled"):
                time.sleep(2)
            report = run.report or run.error or "(sin informe)"
            self.enqueue(
                node.id,
                f"El Agent Swarm que lanzaste terminó ({run.status}). Su informe:\n\n{report[:12000]}",
                source="Agent Swarm",
                thread=thread,
            )

        threading.Thread(
            target=follow, daemon=True, name=f"node-swarm-{run.id}"
        ).start()
        return ""  # the report comes back later, as its own turn

    def _tell_owner(self, node: Node, what: str) -> None:
        if self.notify is None:
            return
        try:
            self.notify(f"{node.name} (Node) {what}. Ábralo en Sergio → Nodes.")
        except Exception:  # noqa: BLE001 - a notice never stops the work
            logger.debug("owner notice failed", exc_info=True)

    # -- you, in the loop ---------------------------------------------------------
    def decide(self, node_id: str, approval_id: str, approve: bool) -> Dict[str, Any]:
        item = self.store.decide(node_id, approval_id, approve)
        if item is None:
            raise NodeError("Esa aprobación ya no está pendiente.")
        thread = item.get("thread", MAIN_THREAD)
        pending = [a for a in self.store.approvals(node_id) if a["status"] == "pending"]
        node = self.store.get(node_id)
        if approve:
            self.store.log(node_id, "approved", item["what"])
            if item.get("action") and node is not None:
                # Exactly what was approved, run by code; the result goes back.
                result = self._run_action(node, item["action"], thread)
                if result:
                    self.enqueue(
                        node_id,
                        f"{item['request']}\n\nResultado real de lo aprobado:\n{result}",
                        source="Resultado aprobado",
                        thread=thread,
                        round_=2,
                    )
            elif item["category"] in ("messages", "delete"):
                # Never done by a Node: the draft is yours to send or do.
                self.store.say(
                    node_id,
                    "node",
                    f"Aprobado. Le dejo esto listo para que usted lo haga: {item['what']}",
                    thread=thread,
                )
            else:
                self.enqueue(
                    node_id,
                    item["what"],
                    source="Acción aprobada",
                    extra=[item["category"]],
                    thread=thread,
                )
        else:
            self.store.log(node_id, "denied", item["what"])
            self.store.say(node_id, "node", "Entendido, no lo haré.", thread=thread)
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

    # -- routines and triggers ------------------------------------------------------
    def tick(self, now: Optional[float] = None) -> int:
        now = now or time.time()
        started = 0
        for node in self.store.all():
            if node.status == "paused":
                continue
            for routine in node.routines:
                if not routine.due(now):
                    continue
                key = f"{node.id}:{routine.id}"
                if routine.kind == "time":
                    self.store.mark_routine(node.id, routine.id, now)
                    self.enqueue(
                        node.id, routine.task, source="Rutina", routine=routine.id
                    )
                    started += 1
                elif key not in self._checking:
                    # Code checks first, off the scheduler's thread.
                    self._checking.add(key)
                    self.store.mark_routine(node.id, routine.id, now)
                    threading.Thread(
                        target=self._check, args=(node.id, routine.id, now), daemon=True
                    ).start()
                    started += 1
        return started

    def check_now(self, node_id: str, routine_id: str) -> Dict[str, Any]:
        """Run a watcher's code check right away (also used by tests)."""
        return self._check(node_id, routine_id, time.time())

    def _check(self, node_id: str, routine_id: str, now: float) -> Dict[str, Any]:
        key = f"{node_id}:{routine_id}"
        try:
            node = self.store.get(node_id)
            routine = next(
                (r for r in (node.routines if node else []) if r.id == routine_id), None
            )
            if node is None or routine is None:
                return {"woke": False}
            if routine.kind == "web":
                check = skills.check_page(
                    routine.url, routine.last_hash, routine.snapshot, fetch=self.fetch
                )
                self.store.mark_routine(
                    node_id,
                    routine_id,
                    0,
                    last_hash=check["hash"],
                    snapshot=check["text"],
                    last_check=now,
                )
                self.store.routine_result(node_id, routine_id)
                if not check["changed"]:
                    self.store.log(
                        node_id,
                        "watch",
                        f"Revisó {routine.url}: sin cambios.",
                        routine=routine_id,
                    )
                    return {"woke": False}
                change = skills.describe_page_change(routine.url, check)
                self.store.log(
                    node_id, "trigger", f"Cambió {routine.url}", routine=routine_id
                )
                self.enqueue(
                    node_id,
                    f"{routine.task}\n\n{change}",
                    source="Vigilancia",
                    routine=routine_id,
                )
                return {"woke": True, "change": change}
            if routine.kind == "app":
                since = skills.iso(
                    routine.last_check or (now - routine.every_minutes * 60)
                )
                items = self.app_items(routine.app, since, routine.keywords)
                self.store.routine_result(node_id, routine_id)
                self.store.mark_routine(node_id, routine_id, 0, last_check=now)
                if not items:
                    self.store.log(
                        node_id,
                        "watch",
                        f"Revisó {routine.app}: nada nuevo.",
                        routine=routine_id,
                    )
                    return {"woke": False}
                found = skills.describe_app_items(routine.app, items)
                self.store.log(
                    node_id,
                    "trigger",
                    f"{len(items)} novedades en {routine.app}",
                    routine=routine_id,
                )
                self.enqueue(
                    node_id,
                    f"{routine.task}\n\n{found}",
                    source="Disparador",
                    routine=routine_id,
                )
                return {"woke": True, "items": items}
            return {"woke": False}
        except Exception as exc:  # noqa: BLE001 - a watcher never kills the scheduler
            # Offline transport failures wait for the next tick, without
            # burning the routine's allowance of three real failures.
            import httpx

            if not isinstance(
                exc, (ConnectionError, TimeoutError, httpx.TransportError)
            ):
                self.store.routine_result(node_id, routine_id, str(exc))
            self.store.log(
                node_id,
                "failed",
                f"No pude revisar: {type(exc).__name__}: {exc}"[:300],
                routine=routine_id,
            )
            return {"woke": False, "error": str(exc)}
        finally:
            self._checking.discard(key)

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


__all__ = [
    "NodeWorker",
    "describe_action",
    "describe_tool",
    "parse_answer",
    "unverified_files",
]

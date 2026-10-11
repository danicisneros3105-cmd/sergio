"""Nodes: your digital employees, working 24/7 (OpenAI's Dots + Meta's Muse).

A Node is not a chat that answers and forgets. Each one has:

* a **face of its own**: a plush character you design (shape, colour,
  accessory, eyes), a name and a **way of talking** (tone);
* its own **computer**: a folder that is its disk (files it makes stay
  there, and you can open them), plus the browser and code tools it is
  allowed to use;
* **long-term memory** that it writes itself (``<recordar>``) and you can
  read and edit (unlike Dots, nothing about you is hidden);
* **rules** for what it does on its own, what it must ask you first and
  what it never does (sending, paying and deleting are never automatic);
* **apps** it may use, each with its own access — read, or read and write
  (Muse's Sentinel); writing always goes through your approval;
* **connections**: commands it may run (CLI allow-list), MCP servers and,
  on the Dev plan, your own APIs (the key stays on this computer);
* **routines and triggers**: work it repeats on its own (every N minutes, at
  a time on some days), a web page it watches, new items in an app — the
  checks are plain code; the model only wakes when something changed;
* **threads**: separate conversations with the same Node and memory;
* an **activity** feed of everything it did, live, and a **take over**
  moment when it needs you (a login, a decision).

Everything lives under ``~/.openjarvis/nodes/<id>/``. A Node runs where the
Sergio server runs: on your PC (when it is on) or on a server you deploy.
"""

from __future__ import annotations

import json
import os
import random
import re
import secrets
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

NODE_ID = re.compile(r"^n_[a-z0-9]{8,24}$")
APP_ID = re.compile(r"^[\w\-]{1,40}$")
NAME = re.compile(r"^[\w\-. ]{1,40}$")
MEMORY_LIMIT = 20_000
ACTIVITY_KEEP = 2000
MESSAGES_KEEP = 2000
MAIN_THREAD = "main"

# What a Node may do: each category, the tools it unlocks, its default, and
# the choices you have (sending and paying can never be fully automatic).
# Categories without tools are carried out by code when the Node asks for
# them with a tag (see worker.py): commands, MCP, APIs, a swarm.
RULES: Dict[str, Dict[str, Any]] = {
    "web": {
        "label": "Buscar y leer la web",
        "tools": [
            "web_search",
            "http_request",
            "browser_navigate",
            "browser_extract",
            "browser_screenshot",
        ],
        "default": "allow",
        "choices": ["allow", "ask", "block"],
    },
    "apps": {
        "label": "Leer sus apps conectadas",
        "tools": ["knowledge_search", "calendar_upcoming", "calendar_search"],
        "default": "allow",
        "choices": ["allow", "ask", "block"],
    },
    "computer": {
        "label": "Crear y editar archivos en su computadora",
        "tools": ["file_read", "file_write", "pdf_extract"],
        "default": "allow",
        "choices": ["allow", "ask", "block"],
    },
    "code": {
        "label": "Ejecutar código",
        "tools": ["python_run", "code_interpreter", "calculator", "verified_math", "scene_reason"],
        "default": "allow",
        "choices": ["allow", "ask", "block"],
    },
    "workspace": {
        "label": "Escribir en su Workspace",
        "tools": ["workspace"],
        "default": "ask",
        "choices": ["allow", "ask", "block"],
    },
    "memory": {
        "label": "Recordar cosas sobre usted",
        "tools": ["memory_search", "memory_store"],
        "default": "allow",
        "choices": ["allow", "block"],
    },
    "cli": {
        "label": "Ejecutar los comandos que usted permita (CLI)",
        "tools": [],
        "default": "ask",
        "choices": ["allow", "ask", "block"],
    },
    "mcp": {
        "label": "Usar sus servidores MCP",
        "tools": [],
        "default": "ask",
        "choices": ["allow", "ask", "block"],
    },
    "api": {
        "label": "Llamar a sus APIs (plan Dev)",
        "tools": [],
        "default": "ask",
        "choices": ["allow", "ask", "block"],
    },
    "swarm": {
        "label": "Lanzar un Agent Swarm para trabajos enormes",
        "tools": [],
        "default": "ask",
        "choices": ["allow", "ask", "block"],
    },
    "pc": {
        "label": "Usar su PC (pantalla y teclado)",
        "tools": ["screen_read", "desktop_action"],
        "default": "block",
        "choices": ["allow", "ask", "block"],
    },
    "messages": {
        "label": "Enviar mensajes o correos",
        "tools": [],  # never sent by a Node: it drafts, you send
        "default": "ask",
        "choices": ["ask", "block"],
    },
    "delete": {
        "label": "Borrar cosas",
        "tools": [],
        "default": "ask",
        "choices": ["ask", "block"],
    },
    "purchases": {
        "label": "Comprar o pagar",
        "tools": [],
        "default": "block",
        "choices": ["block"],
    },
}
STATUSES = ("idle", "working", "waiting_approval", "needs_you", "paused")
COLORS = ("#9fd3ff", "#111111", "#ffffff", "#5fb4f0", "#cfe9ff", "#3a3a3a")

# The plush characters (own design): body shapes, felt colours, things they
# wear and their eyes. Any combination is a valid character.
SHAPES = ("bean", "blob", "drop", "heart", "frog", "bear", "star", "ghost")
FELT = (
    "#f1e6d6",  # oat
    "#3f7be8",  # blue
    "#f6c945",  # yellow
    "#8fd14f",  # green
    "#f05aa6",  # pink
    "#9fd3ff",  # light blue
    "#ff8a4c",  # orange
    "#b58cf0",  # lilac
    "#2b2b2b",  # charcoal
    "#fafafa",  # snow
)
ACCESSORIES = (
    "none",
    "headphones",
    "beret",
    "glasses",
    "sunglasses",
    "bow",
    "cap",
    "beanie",
    "crown",
    "scarf",
)
EYES = ("dots", "happy", "big", "sleepy", "googly")
TONES = {
    "cercano": "cercano y cálido, como un buen compañero de trabajo",
    "formal": "formal y preciso, de usted, sin coloquialismos",
    "breve": "muy breve: lo justo, en viñetas cuando ayude",
    "detallado": "detallado y explicativo, con el porqué de cada cosa",
    "divertido": "con humor ligero y buen ánimo, sin perder la precisión",
    "caballero": "un caballero británico: elegante, irónico con cariño",
}
API_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


class NodeError(ValueError):
    """Something a Node cannot be or do as asked."""


def default_rules() -> Dict[str, str]:
    return {key: spec["default"] for key, spec in RULES.items()}


def clean_rules(rules: Any, base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    out = dict(base or default_rules())
    if isinstance(rules, dict):
        for key, value in rules.items():
            spec = RULES.get(str(key))
            if spec and value in spec["choices"]:
                out[str(key)] = str(value)
    for key, spec in RULES.items():  # locked choices stay locked; new ones appear
        if out.get(key) not in spec["choices"]:
            out[key] = spec["default"]
    return {k: v for k, v in out.items() if k in RULES}


def tools_for(rules: Dict[str, str], extra: Iterable[str] = ()) -> List[str]:
    """The tools a run may use: the «allow» categories, plus the categories
    approved for this one run."""
    extra = set(extra)
    tools: List[str] = []
    for key, spec in RULES.items():
        if rules.get(key) == "allow" or (key in extra and rules.get(key) == "ask"):
            tools += [t for t in spec["tools"] if t not in tools]
    return tools


def random_avatar(seed: str = "") -> Dict[str, str]:
    rng = random.Random(seed or secrets.token_hex(4))
    return {
        "shape": rng.choice(SHAPES),
        "color": rng.choice(FELT[:8]),
        "accessory": rng.choice(ACCESSORIES),
        "eyes": rng.choice(EYES[:4]),
    }


def clean_avatar(data: Any, base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    out = dict(base or random_avatar())
    if isinstance(data, dict):
        if data.get("shape") in SHAPES:
            out["shape"] = data["shape"]
        color = str(data.get("color") or "")
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            out["color"] = color.lower()
        if data.get("accessory") in ACCESSORIES:
            out["accessory"] = data["accessory"]
        if data.get("eyes") in EYES:
            out["eyes"] = data["eyes"]
    return out


def clean_apps(apps: Any) -> Dict[str, str]:
    """``{"gmail": "read", "gcalendar": "write"}`` (a plain list means read)."""
    if isinstance(apps, list):
        apps = {a: "read" for a in apps if isinstance(a, str)}
    out: Dict[str, str] = {}
    if isinstance(apps, dict):
        for app, level in list(apps.items())[:40]:
            if (
                isinstance(app, str)
                and APP_ID.match(app)
                and level in ("read", "write")
            ):
                out[app] = level
    return out


@dataclass
class Routine:
    """Recurring work. ``kind``: «time» (every N minutes or at a time), «web»
    (watch a page: code compares it and the Node wakes only on a change) or
    «app» (new items from an app, optionally with keywords)."""

    id: str
    task: str
    every_minutes: int = 0  # 0: not by interval
    at: str = ""  # "HH:MM" local time
    days: List[int] = field(default_factory=list)  # 0=Monday; empty = every day
    last_run: float = 0.0
    enabled: bool = True
    kind: str = "time"
    url: str = ""
    app: str = ""
    keywords: List[str] = field(default_factory=list)
    last_hash: str = ""
    last_check: float = 0.0
    snapshot: str = ""  # the last text seen (web), to show what changed
    failures: int = 0
    last_error: str = ""

    def due(self, now: float) -> bool:
        if not self.enabled:
            return False
        if self.every_minutes:
            return now - self.last_run >= self.every_minutes * 60
        if not self.at:
            return False
        local = time.localtime(now)
        if self.days and local.tm_wday not in self.days:
            return False
        hour, minute = (int(x) for x in self.at.split(":"))
        target = time.mktime(
            (local.tm_year, local.tm_mon, local.tm_mday, hour, minute, 0, 0, 0, -1)
        )
        return now >= target and self.last_run < target

    def public(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("snapshot", None)
        return data


def clean_routine(data: Any) -> Routine:
    data = data if isinstance(data, dict) else {}
    task = " ".join(str(data.get("task") or "").split())[:1000]
    if not task:
        raise NodeError("Diga qué debe hacer la rutina.")
    kind = str(data.get("kind") or "time")
    if kind not in ("time", "web", "app"):
        raise NodeError("Tipo de rutina no válido.")
    every = int(data.get("every_minutes") or 0)
    at = str(data.get("at") or "")
    url = str(data.get("url") or "").strip()
    app = str(data.get("app") or "").strip()
    keywords = [
        " ".join(str(k).split())[:40]
        for k in data.get("keywords") or []
        if str(k).strip()
    ][:10]
    if kind == "web":
        if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", url):
            raise NodeError("Escriba la dirección completa de la página (https://…).")
        every = max(15, min(every or 60, 7 * 24 * 60))
        at = ""
    elif kind == "app":
        if not APP_ID.match(app):
            raise NodeError("Elija la app que debe vigilar.")
        every = max(15, min(every or 30, 7 * 24 * 60))
        at = ""
    elif every:
        every = max(15, min(every, 7 * 24 * 60))  # at most every 15 minutes
        at = ""
    elif not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
        raise NodeError("Elija cada cuántos minutos o a qué hora (HH:MM).")
    days = sorted(
        {
            int(d)
            for d in data.get("days") or []
            if str(d).isdigit() and 0 <= int(d) <= 6
        }
    )
    return Routine(
        id=f"r_{secrets.token_hex(4)}",
        task=task,
        every_minutes=every,
        at=at,
        days=days,
        kind=kind,
        url=url,
        app=app,
        keywords=keywords,
    )


@dataclass
class Node:
    id: str
    name: str
    instructions: str = ""
    color: str = COLORS[0]
    apps: Dict[str, str] = field(default_factory=dict)
    rules: Dict[str, str] = field(default_factory=default_rules)
    routines: List[Routine] = field(default_factory=list)
    status: str = "idle"
    doing: str = ""  # what it is doing right now, in one line
    waiting: str = ""  # what it needs from you (take over)
    primary: bool = False
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    last_seen: float = 0.0  # when you last opened it (unread activity)
    avatar: Dict[str, str] = field(default_factory=random_avatar)
    tone: str = "cercano"
    template: str = ""
    threads: List[Dict[str, Any]] = field(
        default_factory=lambda: [
            {"id": MAIN_THREAD, "title": "Principal", "created": time.time()}
        ]
    )
    connections: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=lambda: {"cli": [], "mcp": [], "api": []}
    )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["routines"] = [r.public() for r in self.routines]
        return data

    def to_disk(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Node":
        fields = {
            k: v
            for k, v in data.items()
            if k in cls.__dataclass_fields__ and k != "routines"
        }
        node = cls(**fields)
        node.routines = [
            Routine(**{k: v for k, v in r.items() if k in Routine.__dataclass_fields__})
            for r in data.get("routines") or []
            if isinstance(r, dict)
        ]
        node.rules = clean_rules(node.rules)
        node.apps = clean_apps(node.apps)
        node.avatar = clean_avatar(node.avatar, random_avatar(node.id))
        if node.tone not in TONES:
            node.tone = "cercano"
        if not any(t.get("id") == MAIN_THREAD for t in node.threads):
            node.threads.insert(
                0, {"id": MAIN_THREAD, "title": "Principal", "created": node.created}
            )
        for kind in ("cli", "mcp", "api"):
            node.connections.setdefault(kind, [])
        if node.status not in STATUSES:
            node.status = "idle"
        return node


def _home() -> Path:
    return (
        Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis") / "nodes"
    )


def _atomic(path: Path, text: str, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


class NodeStore:
    """Files on disk; one lock for writes."""

    def __init__(self, home: Optional[Path] = None) -> None:
        self.home = home or _home()
        self._lock = threading.RLock()

    # -- paths -------------------------------------------------------------------
    def dir(self, node_id: str) -> Path:
        if not NODE_ID.match(node_id or ""):
            raise NodeError("Identificador de Node no válido.")
        return self.home / node_id

    def computer(self, node_id: str) -> Path:
        path = self.dir(node_id) / "computer"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- nodes -------------------------------------------------------------------
    def create(
        self,
        name: str,
        instructions: str = "",
        color: str = "",
        apps: Any = None,
        rules: Any = None,
        avatar: Any = None,
        tone: str = "",
        template: str = "",
    ) -> Node:
        name = " ".join((name or "").split())[:40]
        if not name:
            raise NodeError("Póngale un nombre a su Node.")
        with self._lock:
            node_id = f"n_{secrets.token_hex(6)}"
            node = Node(
                id=node_id,
                name=name,
                instructions=" ".join((instructions or "").split())[:4000],
                color=color
                if color in COLORS
                else COLORS[len(self.all()) % len(COLORS)],
                apps=clean_apps(apps),
                rules=clean_rules(rules),
                primary=not self.all(),
                avatar=clean_avatar(avatar, random_avatar(node_id)),
                tone=tone if tone in TONES else "cercano",
                template=str(template or "")[:40],
            )
            self.save(node)
            self.computer(node.id)
        return node

    def save(self, node: Node) -> Node:
        node.updated = time.time()
        with self._lock:
            _atomic(
                self.dir(node.id) / "node.json",
                json.dumps(node.to_disk(), ensure_ascii=False, indent=1),
            )
        return node

    def get(self, node_id: str) -> Optional[Node]:
        try:
            path = self.dir(node_id) / "node.json"
        except NodeError:
            return None
        if not path.is_file():
            return None
        try:
            return Node.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def all(self) -> List[Node]:
        if not self.home.is_dir():
            return []
        nodes = [
            self.get(p.name)
            for p in self.home.iterdir()
            if p.is_dir() and NODE_ID.match(p.name)
        ]
        return sorted([n for n in nodes if n], key=lambda n: (not n.primary, n.created))

    def update(self, node_id: str, **changes: Any) -> Node:
        with self._lock:
            node = self.get(node_id)
            if node is None:
                raise NodeError("No existe ese Node.")
            if "name" in changes:
                name = " ".join(str(changes["name"] or "").split())[:40]
                if not name:
                    raise NodeError("El nombre no puede quedar vacío.")
                node.name = name
            if "instructions" in changes:
                node.instructions = " ".join(
                    str(changes["instructions"] or "").split()
                )[:4000]
            if "color" in changes and changes["color"] in COLORS:
                node.color = changes["color"]
            if "apps" in changes:
                node.apps = clean_apps(changes["apps"])
            if "rules" in changes:
                node.rules = clean_rules(changes["rules"], node.rules)
            if "avatar" in changes:
                node.avatar = clean_avatar(changes["avatar"], node.avatar)
            if "tone" in changes and changes["tone"] in TONES:
                node.tone = changes["tone"]
            for key in ("status", "doing", "waiting", "last_seen"):
                if key in changes:
                    setattr(node, key, changes[key])
            if node.status not in STATUSES:
                node.status = "idle"
            return self.save(node)

    def delete(self, node_id: str) -> bool:
        with self._lock:
            path = self.dir(node_id)
            if not path.is_dir():
                return False
            shutil.rmtree(path, ignore_errors=True)
            rest = self.all()
            if rest and not any(n.primary for n in rest):
                rest[0].primary = True
                self.save(rest[0])
            return True

    # -- threads -------------------------------------------------------------------
    def add_thread(self, node_id: str, title: str = "") -> Dict[str, Any]:
        with self._lock:
            node = self.get(node_id)
            if node is None:
                raise NodeError("No existe ese Node.")
            if len(node.threads) >= 50:
                raise NodeError("Como mucho 50 hilos por Node.")
            thread = {
                "id": f"t_{secrets.token_hex(4)}",
                "title": " ".join((title or "").split())[:60]
                or f"Hilo {len(node.threads) + 1}",
                "created": time.time(),
            }
            node.threads.append(thread)
            self.save(node)
            return thread

    def thread_ok(self, node: Node, thread: str) -> str:
        return (
            thread if any(t.get("id") == thread for t in node.threads) else MAIN_THREAD
        )

    # -- routines ----------------------------------------------------------------
    def add_routine(self, node_id: str, data: Any) -> Routine:
        routine = clean_routine(data)
        with self._lock:
            node = self.get(node_id)
            if node is None:
                raise NodeError("No existe ese Node.")
            if len(node.routines) >= 20:
                raise NodeError("Como mucho 20 rutinas por Node.")
            if routine.kind == "app" and routine.app not in node.apps:
                raise NodeError("Dele primero acceso a esa app (pestaña Apps).")
            routine.last_run = (
                time.time() if routine.every_minutes and routine.kind == "time" else 0.0
            )
            node.routines.append(routine)
            self.save(node)
        return routine

    def remove_routine(self, node_id: str, routine_id: str) -> bool:
        with self._lock:
            node = self.get(node_id)
            if node is None:
                return False
            before = len(node.routines)
            node.routines = [r for r in node.routines if r.id != routine_id]
            self.save(node)
            return len(node.routines) < before

    def mark_routine(
        self, node_id: str, routine_id: str, when: float, **changes: Any
    ) -> None:
        with self._lock:
            node = self.get(node_id)
            if node is None:
                return
            for r in node.routines:
                if r.id == routine_id:
                    if when:
                        r.last_run = when
                    for key, value in changes.items():
                        if hasattr(r, key):
                            setattr(r, key, value)
            self.save(node)

    # -- connections ---------------------------------------------------------------
    def routine_result(self, node_id: str, routine_id: str, error: str = "") -> None:
        with self._lock:
            node = self.get(node_id)
            if node is None:
                return
            for routine in node.routines:
                if routine.id == routine_id:
                    routine.failures = routine.failures + 1 if error else 0
                    routine.last_error = error[:300]
                    if routine.failures >= 3:
                        routine.enabled = False
            self.save(node)

    def add_connection(
        self, node_id: str, kind: str, data: Dict[str, Any], secret: str = ""
    ) -> Dict[str, Any]:
        """A command (cli), an MCP server (mcp) or an API (api) for this Node.
        API keys are kept apart, readable only by you (0600), never sent back."""
        if kind not in ("cli", "mcp", "api"):
            raise NodeError("Tipo de conexión no válido.")
        name = " ".join(str(data.get("name") or "").split())[:40]
        if not NAME.match(name):
            raise NodeError("Póngale un nombre corto (letras, números, guiones).")
        item: Dict[str, Any] = {
            "id": f"c_{secrets.token_hex(4)}",
            "name": name,
            "added": time.time(),
        }
        if kind == "cli":
            command = " ".join(str(data.get("command") or "").split())[:200]
            program = command.split(" ", 1)[0] if command else ""
            if (
                not program
                or not re.fullmatch(r"[\w.\-/]{1,80}", program)
                or program in BLOCKED_PROGRAMS
            ):
                raise NodeError(
                    "Escriba el programa permitido, p. ej. «git» o «git status»."
                )
            item["command"] = (
                command  # the program and, optionally, the only arguments it may start with
            )
        elif kind == "mcp":
            url = str(data.get("url") or "").strip()
            command = str(data.get("command") or "").strip()
            if url and not re.match(r"^https?://", url):
                raise NodeError(
                    "La URL del servidor MCP debe empezar por http:// o https://."
                )
            if not url and not command:
                raise NodeError("Escriba el comando o la URL del servidor MCP.")
            item.update(url=url[:300], command=command[:300])
        else:
            base = str(data.get("base_url") or "").strip().rstrip("/")
            if not re.match(r"^https?://[^\s/]+", base):
                raise NodeError("La dirección base debe empezar por https://.")
            header = str(data.get("auth_header") or "Authorization").strip()[:60]
            if not re.fullmatch(r"[A-Za-z0-9\-]{1,60}", header):
                raise NodeError("Nombre de cabecera no válido.")
            item.update(
                base_url=base[:300], auth_header=header, has_secret=bool(secret)
            )
            item["prefix"] = str(data.get("prefix") or "")[:20]  # e.g. "Bearer"
        with self._lock:
            node = self.get(node_id)
            if node is None:
                raise NodeError("No existe ese Node.")
            if len(node.connections[kind]) >= 20:
                raise NodeError("Como mucho 20 conexiones de cada tipo.")
            if any(c["name"].lower() == name.lower() for c in node.connections[kind]):
                raise NodeError("Ya hay una conexión con ese nombre.")
            node.connections[kind].append(item)
            self.save(node)
            if kind == "api" and secret:
                secrets_ = self._secrets(node_id)
                secrets_[item["id"]] = secret
                _atomic(
                    self.dir(node_id) / "secrets.json",
                    json.dumps(secrets_),
                    private=True,
                )
        return item

    def remove_connection(self, node_id: str, kind: str, conn_id: str) -> bool:
        with self._lock:
            node = self.get(node_id)
            if node is None or kind not in node.connections:
                return False
            before = len(node.connections[kind])
            node.connections[kind] = [
                c for c in node.connections[kind] if c["id"] != conn_id
            ]
            self.save(node)
            secrets_ = self._secrets(node_id)
            if secrets_.pop(conn_id, None) is not None:
                _atomic(
                    self.dir(node_id) / "secrets.json",
                    json.dumps(secrets_),
                    private=True,
                )
            return len(node.connections[kind]) < before

    def _secrets(self, node_id: str) -> Dict[str, str]:
        path = self.dir(node_id) / "secrets.json"
        try:
            return (
                json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            )
        except (OSError, ValueError):
            return {}

    def secret(self, node_id: str, conn_id: str) -> str:
        return self._secrets(node_id).get(conn_id, "")

    # -- memory ------------------------------------------------------------------
    def memory(self, node_id: str) -> str:
        path = self.dir(node_id) / "memory.md"
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def set_memory(self, node_id: str, text: str) -> str:
        text = (text or "")[-MEMORY_LIMIT:]
        _atomic(self.dir(node_id) / "memory.md", text)
        return text

    def remember(self, node_id: str, facts: Iterable[str]) -> List[str]:
        with self._lock:
            current = self.memory(node_id)
            added = []
            for fact in facts:
                fact = " ".join(str(fact).split())[:400]
                if fact and fact.lower() not in current.lower():
                    current += (
                        "" if current.endswith("\n") or not current else "\n"
                    ) + f"- {fact}\n"
                    added.append(fact)
            if added:
                self.set_memory(node_id, current)
            return added

    # -- feeds -------------------------------------------------------------------
    def _append(
        self, node_id: str, name: str, item: Dict[str, Any], keep: int
    ) -> Dict[str, Any]:
        path = self.dir(node_id) / name
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
            if path.stat().st_size > keep * 600:
                lines = path.read_text(encoding="utf-8").splitlines()[-keep:]
                _atomic(path, "\n".join(lines) + "\n")
        return item

    def _read(
        self, node_id: str, name: str, after: float = 0.0, limit: int = 200
    ) -> List[Dict[str, Any]]:
        path = self.dir(node_id) / name
        if not path.is_file():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if float(item.get("at", 0)) > after:
                out.append(item)
        return out[-limit:]

    def log(self, node_id: str, kind: str, text: str, **data: Any) -> Dict[str, Any]:
        item = {
            "id": secrets.token_hex(5),
            "at": time.time(),
            "kind": kind,
            "text": str(text)[:2000],
            **data,
        }
        return self._append(node_id, "activity.jsonl", item, ACTIVITY_KEEP)

    def activity(
        self, node_id: str, after: float = 0.0, limit: int = 200
    ) -> List[Dict[str, Any]]:
        return self._read(node_id, "activity.jsonl", after, limit)

    def say(
        self, node_id: str, role: str, text: str, thread: str = MAIN_THREAD, **data: Any
    ) -> Dict[str, Any]:
        item = {
            "id": secrets.token_hex(5),
            "at": time.time(),
            "role": role,
            "text": str(text)[:20000],
            "thread": thread or MAIN_THREAD,
            **data,
        }
        return self._append(node_id, "messages.jsonl", item, MESSAGES_KEEP)

    def messages(
        self,
        node_id: str,
        after: float = 0.0,
        limit: int = 200,
        thread: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        items = self._read(node_id, "messages.jsonl", after, MESSAGES_KEEP)
        if thread is not None:
            items = [m for m in items if m.get("thread", MAIN_THREAD) == thread]
        return items[-limit:]

    # -- approvals ---------------------------------------------------------------
    def approvals(self, node_id: str) -> List[Dict[str, Any]]:
        path = self.dir(node_id) / "approvals.json"
        try:
            return (
                json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
            )
        except (OSError, ValueError):
            return []

    def _save_approvals(self, node_id: str, items: List[Dict[str, Any]]) -> None:
        _atomic(
            self.dir(node_id) / "approvals.json",
            json.dumps(items[-200:], ensure_ascii=False),
        )

    def request_approval(
        self,
        node_id: str,
        category: str,
        what: str,
        request: str,
        action: Optional[Dict[str, Any]] = None,
        thread: str = MAIN_THREAD,
    ) -> Dict[str, Any]:
        item = {
            "id": f"a_{secrets.token_hex(4)}",
            "at": time.time(),
            "category": category if category in RULES else "messages",
            "what": " ".join(str(what).split())[:1500],
            "request": request[:2000],
            "status": "pending",
            "thread": thread,
        }
        if action:
            item["action"] = action  # exactly what code will run on approval
        with self._lock:
            items = self.approvals(node_id)
            items.append(item)
            self._save_approvals(node_id, items)
        return item

    def decide(
        self, node_id: str, approval_id: str, approve: bool
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            items = self.approvals(node_id)
            for item in items:
                if item["id"] == approval_id and item["status"] == "pending":
                    item["status"] = "approved" if approve else "denied"
                    item["decided"] = time.time()
                    self._save_approvals(node_id, items)
                    return item
        return None

    # -- its computer --------------------------------------------------------------
    def files(self, node_id: str) -> List[Dict[str, Any]]:
        root = self.computer(node_id)
        out = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                st = path.stat()
                out.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "size": st.st_size,
                        "modified": st.st_mtime,
                    }
                )
        return out[:500]

    def file_path(self, node_id: str, rel: str) -> Optional[Path]:
        root = self.computer(node_id).resolve()
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return None
        return path


# Programs a Node may never be allowed to run, whatever you add: shells and
# interpreters run anything; privilege and disk tools can wreck the machine.
BLOCKED_PROGRAMS = frozenset(
    {
        "sh", "bash", "zsh", "fish", "dash", "cmd", "cmd.exe", "powershell", "pwsh",
        "sudo", "su", "doas", "rm", "rmdir", "dd", "mkfs", "shutdown", "reboot", "halt",
        "poweroff", "chmod", "chown", "mount", "umount", "kill", "killall", "pkill", "eval",
        "exec", "env", "xargs", "nohup", "setsid", "crontab", "at", "systemctl", "service",
    }
)  # fmt: skip


__all__ = [
    "ACCESSORIES",
    "API_METHODS",
    "BLOCKED_PROGRAMS",
    "COLORS",
    "EYES",
    "FELT",
    "MAIN_THREAD",
    "Node",
    "NodeError",
    "NodeStore",
    "RULES",
    "Routine",
    "SHAPES",
    "TONES",
    "clean_apps",
    "clean_avatar",
    "clean_routine",
    "clean_rules",
    "default_rules",
    "random_avatar",
    "tools_for",
]

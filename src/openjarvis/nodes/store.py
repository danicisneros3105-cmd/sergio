"""Nodes: your digital employees, working 24/7 (modelled on OpenAI's Dots).

A Node is not a chat that answers and forgets. Each one has:

* its own **computer**: a folder that is its disk (files it makes stay
  there, and you can open them), plus the browser and code tools it is
  allowed to use;
* **long-term memory** that it writes itself (``<recordar>``) and you can
  read and edit;
* **rules** for what it does on its own, what it must ask you first and
  what it never does (sending, paying and deleting are never automatic);
* **apps** it may read (your connected sources, through knowledge search);
* **routines**: work it repeats on its own (every N minutes, or at a time
  on some days), so it keeps going while you sleep;
* an **activity** feed of everything it did, live, and a **take over**
  moment when it needs you (a login, a decision).

Everything lives under ``~/.openjarvis/nodes/<id>/``. A Node runs where the
Sergio server runs: on your PC (when it is on) or on a server you deploy.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

NODE_ID = re.compile(r"^n_[a-z0-9]{8,24}$")
MEMORY_LIMIT = 20_000
ACTIVITY_KEEP = 2000
MESSAGES_KEEP = 1000

# What a Node may do: each category, the tools it unlocks, its default, and
# the choices you have (sending and paying can never be fully automatic).
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
        "tools": ["python_run", "code_interpreter", "calculator"],
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
    for key, spec in RULES.items():  # locked choices stay locked
        if out.get(key) not in spec["choices"]:
            out[key] = spec["default"]
    return out


def tools_for(rules: Dict[str, str], extra: Iterable[str] = ()) -> List[str]:
    """The tools a run may use: the «allow» categories, plus the categories
    approved for this one run."""
    extra = set(extra)
    tools: List[str] = []
    for key, spec in RULES.items():
        if rules.get(key) == "allow" or (key in extra and rules.get(key) == "ask"):
            tools += [t for t in spec["tools"] if t not in tools]
    return tools


@dataclass
class Routine:
    id: str
    task: str
    every_minutes: int = 0  # 0: not by interval
    at: str = ""  # "HH:MM" local time
    days: List[int] = field(default_factory=list)  # 0=Monday; empty = every day
    last_run: float = 0.0
    enabled: bool = True

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


def clean_routine(data: Any) -> Routine:
    data = data if isinstance(data, dict) else {}
    task = " ".join(str(data.get("task") or "").split())[:1000]
    if not task:
        raise NodeError("Diga qué debe hacer la rutina.")
    every = int(data.get("every_minutes") or 0)
    at = str(data.get("at") or "")
    if every:
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
        id=f"r_{secrets.token_hex(4)}", task=task, every_minutes=every, at=at, days=days
    )


@dataclass
class Node:
    id: str
    name: str
    instructions: str = ""
    color: str = COLORS[0]
    apps: List[str] = field(default_factory=list)
    rules: Dict[str, str] = field(default_factory=default_rules)
    routines: List[Routine] = field(default_factory=list)
    status: str = "idle"
    doing: str = ""  # what it is doing right now, in one line
    waiting: str = ""  # what it needs from you (take over)
    primary: bool = False
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    last_seen: float = 0.0  # when you last opened it (unread activity)

    def to_dict(self) -> Dict[str, Any]:
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
        if node.status not in STATUSES:
            node.status = "idle"
        return node


def _home() -> Path:
    return (
        Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis") / "nodes"
    )


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
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
        apps: Optional[List[str]] = None,
        rules: Any = None,
    ) -> Node:
        name = " ".join((name or "").split())[:40]
        if not name:
            raise NodeError("Póngale un nombre a su Node.")
        with self._lock:
            node = Node(
                id=f"n_{secrets.token_hex(6)}",
                name=name,
                instructions=" ".join((instructions or "").split())[:4000],
                color=color
                if color in COLORS
                else COLORS[len(self.all()) % len(COLORS)],
                apps=[
                    a
                    for a in (apps or [])
                    if isinstance(a, str) and re.fullmatch(r"[\w\-]{1,40}", a)
                ][:40],
                rules=clean_rules(rules),
                primary=not self.all(),
            )
            self.save(node)
            self.computer(node.id)
        return node

    def save(self, node: Node) -> Node:
        node.updated = time.time()
        with self._lock:
            _atomic(
                self.dir(node.id) / "node.json",
                json.dumps(node.to_dict(), ensure_ascii=False, indent=1),
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
            if "apps" in changes and isinstance(changes["apps"], list):
                node.apps = [
                    a
                    for a in changes["apps"]
                    if isinstance(a, str) and re.fullmatch(r"[\w\-]{1,40}", a)
                ][:40]
            if "rules" in changes:
                node.rules = clean_rules(changes["rules"], node.rules)
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

    # -- routines ----------------------------------------------------------------
    def add_routine(self, node_id: str, data: Any) -> Routine:
        routine = clean_routine(data)
        with self._lock:
            node = self.get(node_id)
            if node is None:
                raise NodeError("No existe ese Node.")
            if len(node.routines) >= 20:
                raise NodeError("Como mucho 20 rutinas por Node.")
            routine.last_run = time.time() if routine.every_minutes else 0.0
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

    def mark_routine(self, node_id: str, routine_id: str, when: float) -> None:
        with self._lock:
            node = self.get(node_id)
            if node is None:
                return
            for r in node.routines:
                if r.id == routine_id:
                    r.last_run = when
            self.save(node)

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

    def say(self, node_id: str, role: str, text: str, **data: Any) -> Dict[str, Any]:
        item = {
            "id": secrets.token_hex(5),
            "at": time.time(),
            "role": role,
            "text": str(text)[:20000],
            **data,
        }
        return self._append(node_id, "messages.jsonl", item, MESSAGES_KEEP)

    def messages(
        self, node_id: str, after: float = 0.0, limit: int = 200
    ) -> List[Dict[str, Any]]:
        return self._read(node_id, "messages.jsonl", after, limit)

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
        self, node_id: str, category: str, what: str, request: str
    ) -> Dict[str, Any]:
        item = {
            "id": f"a_{secrets.token_hex(4)}",
            "at": time.time(),
            "category": category if category in RULES else "messages",
            "what": " ".join(str(what).split())[:1500],
            "request": request[:2000],
            "status": "pending",
        }
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


__all__ = [
    "COLORS",
    "Node",
    "NodeError",
    "NodeStore",
    "RULES",
    "Routine",
    "clean_routine",
    "clean_rules",
    "default_rules",
    "tools_for",
]

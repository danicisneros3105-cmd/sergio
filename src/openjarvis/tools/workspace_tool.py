"""Sergio's hands in the Workspace: find, read, write pages and tasks.

So «apunta en mi página de compras: leche», «¿qué decidimos en la reunión
del lunes?» or «crea una página con el plan del viaje» work from chat, the
voice and the agents. Encrypted pages are never read (only their titles).
"""

from __future__ import annotations

import secrets
import time
from typing import Any, Dict, List

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.workspace.store import (
    WorkspaceError,
    WorkspaceStore,
    default_store,
    page_text,
)

KINDS = {
    "text",
    "h1",
    "h2",
    "h3",
    "todo",
    "bullet",
    "number",
    "quote",
    "callout",
    "code",
}


def _block(kind: str, text: str) -> Dict[str, Any]:
    b: Dict[str, Any] = {
        "id": "b_" + secrets.token_hex(7),
        "type": kind if kind in KINDS else "text",
        "text": text,
    }
    if b["type"] == "todo":
        b["checked"] = False
    return b


def _find(store: WorkspaceStore, ref: str) -> Dict[str, Any] | None:
    ref = (ref or "").strip()
    if ref.startswith("p_"):
        return store.get(ref)
    want = ref.lower()
    pages = store.all()
    exact = [p for p in pages if (p.get("title") or "").strip().lower() == want]
    if exact:
        return exact[0]
    hits = store.search(ref, limit=1)
    return store.get(hits[0]["id"]) if hits else None


@ToolRegistry.register("workspace")
class WorkspaceTool(BaseTool):
    tool_id = "workspace"

    def __init__(self, store: WorkspaceStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> WorkspaceStore:
        return self._store or default_store()

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "The user's Workspace (their notes, pages, tables and tasks, kept on their own computer). "
                "Actions: 'search' (query) finds pages; 'read' (page: id or title) returns a page's text; "
                "'create' (title, lines) makes a page; 'append' (page, lines, kind) adds lines to a page; "
                "'task' (page, text) adds a to-do; 'list' shows recent pages. Use it whenever the user "
                "mentions their notes, pages, lists or tasks."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["search", "read", "create", "append", "task", "list"],
                    },
                    "query": {"type": "string"},
                    "page": {"type": "string", "description": "Page id or title."},
                    "title": {"type": "string"},
                    "lines": {"type": "array", "items": {"type": "string"}},
                    "kind": {
                        "type": "string",
                        "description": "Block kind for appended lines: text, bullet, todo, h2…",
                    },
                    "text": {"type": "string"},
                },
                "required": ["action"],
            },
            category="productivity",
        )

    def _ok(self, content: str, **meta: Any) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=content, metadata=meta)

    def _fail(self, message: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=message, success=False)

    def execute(self, **params: Any) -> ToolResult:
        try:
            return self._run(params)
        except WorkspaceError as exc:
            return self._fail(str(exc))

    def _run(self, params: Dict[str, Any]) -> ToolResult:
        action = str(params.get("action") or "")
        store = self.store
        if action == "list":
            pages = sorted(
                store.list(include_archived=False), key=lambda p: -p["updatedAt"]
            )[:20]
            return self._ok(
                "\n".join(f"- {p['title'] or 'Sin título'} ({p['id']})" for p in pages)
                or "No hay páginas.",
                pages=pages,
            )
        if action == "search":
            hits = store.search(
                str(params.get("query") or params.get("text") or ""), limit=8
            )
            if not hits:
                return self._ok(
                    "No encuentro nada con eso en su Workspace.", results=[]
                )
            return self._ok(
                "\n".join(
                    f"- {h['title'] or 'Sin título'} ({h['id']}): {h['snippet']}"
                    for h in hits
                ),
                results=hits,
            )
        if action == "read":
            page = _find(store, str(params.get("page") or params.get("query") or ""))
            if page is None:
                return self._fail("No encuentro esa página.")
            if page.get("sealed"):
                return self._fail(
                    "Esa página está cifrada: solo usted puede abrirla en la app."
                )
            return self._ok(
                f"# {page.get('title') or 'Sin título'}\n{page_text(page, 12000)}",
                id=page["id"],
            )
        if action == "create":
            now = int(time.time() * 1000)
            lines: List[str] = [str(x) for x in params.get("lines") or []]
            kind = str(params.get("kind") or "text")
            page = {
                "id": "p_" + secrets.token_hex(8),
                "title": str(params.get("title") or "Página nueva")[:300],
                "icon": "",
                "parent": None,
                "blocks": [_block(kind, line) for line in lines]
                or [_block("text", "")],
                "createdAt": now,
                "updatedAt": now,
                "openedAt": now,
                "rev": 0,
                "tags": [],
                "sealed": None,
            }
            saved = store.put(page)
            return self._ok(f"Creé la página «{saved['title']}».", id=saved["id"])
        if action in ("append", "task"):
            page = _find(store, str(params.get("page") or ""))
            if page is None:
                return self._fail("No encuentro esa página.")
            if page.get("sealed"):
                return self._fail("Esa página está cifrada: no puedo escribir en ella.")
            if action == "task":
                new = [_block("todo", str(params.get("text") or ""))]
            else:
                new = [
                    _block(str(params.get("kind") or "text"), str(x))
                    for x in params.get("lines") or []
                ]
            if not new or not any(b["text"] for b in new):
                return self._fail("¿Qué quiere que apunte?")
            page["blocks"] = [
                b
                for b in page.get("blocks") or []
                if b.get("text") or b.get("type") != "text"
            ] + new
            page["updatedAt"] = int(time.time() * 1000)
            saved = store.put(page, page.get("rev"))
            what = "la tarea" if action == "task" else f"{len(new)} línea(s)"
            return self._ok(f"Añadí {what} a «{saved['title']}».", id=saved["id"])
        return self._fail("Acción no válida.")


__all__ = ["WorkspaceTool"]

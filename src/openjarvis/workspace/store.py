"""The Workspace on disk: one JSON per page (lossless) and its Markdown twin.

``~/.openjarvis/workspace/``

* ``pages/<id>.json`` — what the app edits (blocks, tables, settings).
* ``pages/<id>.md``   — the portable copy, rewritten on every save.
* ``files/<id>.<ext>`` — voice notes, photos, images.
* ``trash/``          — deleted pages, kept 30 days.
* ``shares.json``     — share links (see shares.py).

Local-first: the browser keeps its own copy (IndexedDB) and works offline;
this store is where copies meet. Every save carries the revision it was
based on: if the page changed meanwhile, the newer one stays and the other
is saved as «(copia en conflicto)», so nothing is lost silently.

End-to-end encrypted pages arrive here already sealed (``sealed`` holds
the ciphertext, ``blocks`` is empty): the server cannot read them.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openjarvis.workspace.markdown import page_markdown

log = logging.getLogger(__name__)

PAGE_ID = re.compile(r"^p_[a-z0-9]{6,24}$")
FILE_ID = re.compile(
    r"^f_[a-z0-9]{6,24}\.(png|jpe?g|webp|gif|webm|ogg|oga|mp3|m4a|wav|mp4)$"
)
FILE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "oga": "audio/ogg",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
    "mp4": "audio/mp4",
}
MAX_PAGE_BYTES = 5_000_000
MAX_FILE_BYTES = 25_000_000
MAX_BLOCKS = 5000
TRASH_DAYS = 30


class WorkspaceError(ValueError):
    """A page or file that cannot be stored as sent."""


class Conflict(Exception):
    """The page changed since the client's copy; its version was kept aside."""

    def __init__(self, current: Dict[str, Any], copy_id: str) -> None:
        super().__init__("conflict")
        self.current = current
        self.copy_id = copy_id


def workspace_home() -> Path:
    base = os.environ.get("OPENJARVIS_HOME") or str(Path.home() / ".openjarvis")
    return Path(base) / "workspace"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _summary(page: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": page["id"],
        "title": page.get("title") or "",
        "icon": page.get("icon") or "",
        "parent": page.get("parent"),
        "rev": int(page.get("rev") or 0),
        "createdAt": page.get("createdAt") or 0,
        "updatedAt": page.get("updatedAt") or 0,
        "favorite": bool(page.get("favorite")),
        "archived": bool(page.get("archived")),
        "sealed": bool(page.get("sealed")),
        "tags": page.get("tags") or [],
    }


def validate_page(page: Any) -> Dict[str, Any]:
    if not isinstance(page, dict):
        raise WorkspaceError("La página debe ser un objeto.")
    page_id = str(page.get("id") or "")
    if not PAGE_ID.match(page_id):
        raise WorkspaceError("Identificador de página no válido.")
    if len(json.dumps(page, ensure_ascii=False)) > MAX_PAGE_BYTES:
        raise WorkspaceError("La página es demasiado grande (máx. 5 MB).")
    blocks = page.get("blocks")
    if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
        raise WorkspaceError("Los bloques deben ser una lista (máx. 5000).")
    if not all(isinstance(b, dict) for b in blocks):
        raise WorkspaceError("Cada bloque debe ser un objeto.")
    title = page.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > 300):
        raise WorkspaceError("Título no válido (máx. 300 caracteres).")
    parent = page.get("parent")
    if parent is not None and not (isinstance(parent, str) and PAGE_ID.match(parent)):
        raise WorkspaceError("Página madre no válida.")
    sealed = page.get("sealed")
    if sealed and (not isinstance(sealed, dict) or blocks):
        raise WorkspaceError("Una página cifrada no lleva bloques legibles.")
    return page


class WorkspaceStore:
    """Pages and files under one folder; safe to share between threads."""

    def __init__(
        self,
        root: Optional[Path] = None,
        on_change: Optional[Callable[[], None]] = None,
    ) -> None:
        self.root = Path(root) if root else workspace_home()
        self.pages_dir = self.root / "pages"
        self.files_dir = self.root / "files"
        self.trash_dir = self.root / "trash"
        self.on_change = on_change
        self._lock = threading.RLock()
        self._cache: Dict[str, tuple[float, Dict[str, Any]]] = {}

    # -- pages ------------------------------------------------------------------
    def _path(self, page_id: str) -> Path:
        if not PAGE_ID.match(page_id or ""):
            raise WorkspaceError("Identificador de página no válido.")
        return self.pages_dir / f"{page_id}.json"

    def get(self, page_id: str) -> Optional[Dict[str, Any]]:
        path = self._path(page_id)
        with self._lock:
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                self._cache.pop(page_id, None)
                return None
            hit = self._cache.get(page_id)
            if hit and hit[0] == mtime:
                return json.loads(json.dumps(hit[1]))
            try:
                page = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                log.warning("Workspace page %s is unreadable", page_id)
                return None
            self._cache[page_id] = (mtime, page)
            return json.loads(json.dumps(page))

    def all(self, include_archived: bool = False) -> List[Dict[str, Any]]:
        out = []
        if not self.pages_dir.is_dir():
            return out
        for path in sorted(self.pages_dir.glob("p_*.json")):
            page = self.get(path.stem)
            if page and (include_archived or not page.get("archived")):
                out.append(page)
        return out

    def list(self, include_archived: bool = True) -> List[Dict[str, Any]]:
        return [_summary(p) for p in self.all(include_archived)]

    def title_of(self, page_id: str) -> str:
        page = self.get(page_id) if PAGE_ID.match(page_id or "") else None
        return (page or {}).get("title") or ""

    def _write(self, page: Dict[str, Any]) -> None:
        data = json.dumps(page, ensure_ascii=False, indent=1).encode("utf-8")
        _atomic_write(self._path(page["id"]), data)
        md = page_markdown(page, self.title_of)
        _atomic_write(self.pages_dir / f"{page['id']}.md", md.encode("utf-8"))

    def put(
        self, page: Dict[str, Any], base_rev: Optional[int] = None
    ) -> Dict[str, Any]:
        """Save a page. ``base_rev`` is the revision the client edited; when the
        stored page moved on, the stored one stays and the client's is kept as
        a conflict copy (raises :class:`Conflict`)."""
        page = dict(validate_page(page))
        now = int(time.time() * 1000)
        with self._lock:
            current = self.get(page["id"])
            if (
                current is not None
                and base_rev is not None
                and int(current.get("rev") or 0) != int(base_rev)
            ):
                copy = dict(page)
                copy["id"] = "p_" + secrets.token_hex(8)
                copy["title"] = (
                    f"{page.get('title') or 'Sin título'} (copia en conflicto)"
                )
                copy["rev"] = 1
                copy["updatedAt"] = now
                self._write(copy)
                self._changed()
                raise Conflict(current, copy["id"])
            page["rev"] = int((current or {}).get("rev") or 0) + 1
            page.setdefault("createdAt", now)
            page["updatedAt"] = int(page.get("updatedAt") or now)
            self._write(page)
        self._changed()
        return page

    def delete(self, page_id: str) -> bool:
        path = self._path(page_id)
        with self._lock:
            if not path.exists():
                return False
            self.trash_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            shutil.move(str(path), str(self.trash_dir / f"{page_id}.{stamp}.json"))
            md = self.pages_dir / f"{page_id}.md"
            if md.exists():
                md.unlink()
            self._cache.pop(page_id, None)
        self._changed()
        return True

    def empty_trash(self, days: int = TRASH_DAYS) -> int:
        if not self.trash_dir.is_dir():
            return 0
        cutoff = time.time() - days * 86400
        gone = 0
        for path in self.trash_dir.iterdir():
            if path.stat().st_mtime < cutoff:
                path.unlink()
                gone += 1
        return gone

    def _changed(self) -> None:
        if self.on_change is not None:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001 — a backup hiccup never breaks a save
                log.debug("workspace change hook failed", exc_info=True)

    # -- files --------------------------------------------------------------------
    def save_file(self, data: bytes, ext: str) -> str:
        ext = ext.lower().lstrip(".")
        if ext not in FILE_TYPES:
            raise WorkspaceError("Tipo de archivo no admitido.")
        if len(data) > MAX_FILE_BYTES:
            raise WorkspaceError("El archivo es demasiado grande (máx. 25 MB).")
        file_id = f"f_{secrets.token_hex(8)}.{ext}"
        _atomic_write(self.files_dir / file_id, data)
        self._changed()
        return file_id

    def file_path(self, file_id: str) -> Optional[Path]:
        if not FILE_ID.match(file_id or ""):
            return None
        path = self.files_dir / file_id
        return path if path.is_file() else None

    # -- search -------------------------------------------------------------------
    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Pages whose title or text contain every word (accents ignored)."""
        import unicodedata

        def plain(text: str) -> str:
            text = unicodedata.normalize("NFKD", text.lower())
            return "".join(c for c in text if not unicodedata.combining(c))

        words = [w for w in plain(query).split() if w]
        if not words:
            return []
        hits = []
        for page in self.all():
            if page.get("sealed"):
                continue
            text = page_text(page)
            hay = plain(f"{page.get('title') or ''}\n{text}")
            if all(w in hay for w in words):
                score = sum(hay.count(w) for w in words) + (
                    5 if all(w in plain(page.get("title") or "") for w in words) else 0
                )
                at = hay.find(words[0])
                start = max(0, at - 60)
                snippet = (f"{page.get('title') or ''}\n{text}")[
                    start : start + 200
                ].replace("\n", " ")
                hits.append(
                    {**_summary(page), "snippet": snippet.strip(), "score": score}
                )
        hits.sort(key=lambda h: (-h["score"], -h["updatedAt"]))
        return hits[:limit]

    # -- export -------------------------------------------------------------------
    def export_zip(self) -> bytes:
        """Every page as JSON and Markdown, plus the files: take it anywhere."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for page in self.all(include_archived=True):
                z.writestr(
                    f"pages/{page['id']}.json",
                    json.dumps(page, ensure_ascii=False, indent=1),
                )
                z.writestr(
                    f"markdown/{_slug(page.get('title') or page['id'])}-{page['id'][2:8]}.md",
                    page_markdown(page, self.title_of),
                )
            if self.files_dir.is_dir():
                for path in self.files_dir.iterdir():
                    if FILE_ID.match(path.name):
                        z.write(path, f"markdown/files/{path.name}")
            z.writestr(
                "LEEME.txt",
                "Su Workspace de Sergio.\n\npages/: cada página en JSON (todo, sin pérdidas).\n"
                "markdown/: la misma página en Markdown, para abrirla con cualquier editor.\n"
                "Las páginas cifradas siguen cifradas: ábralas en Sergio con su frase.\n",
            )
        return buf.getvalue()


def _slug(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60] or "pagina"


def page_text(page: Dict[str, Any], limit: int = 20000) -> str:
    parts: List[str] = []
    for b in page.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        if b.get("text"):
            parts.append(str(b["text"]))
        table = b.get("table") or {}
        for row in table.get("rows") or []:
            if isinstance(row, dict) and not row.get("archived"):
                parts.append(
                    " ".join(str(v) for v in (row.get("cells") or {}).values())
                )
        for node in b.get("mind") or []:
            if isinstance(node, dict):
                parts.append(str(node.get("text") or ""))
    return "\n".join(parts)[:limit]


_STORE: Optional[WorkspaceStore] = None


def default_store() -> WorkspaceStore:
    """The server's store; each change nudges the encrypted sync, if set up."""
    global _STORE
    if _STORE is None or _STORE.root != workspace_home():
        from openjarvis.backup.sync import nudge

        _STORE = WorkspaceStore(on_change=nudge)
    return _STORE


__all__ = [
    "Conflict",
    "FILE_TYPES",
    "MAX_FILE_BYTES",
    "PAGE_ID",
    "WorkspaceError",
    "WorkspaceStore",
    "default_store",
    "page_text",
    "validate_page",
    "workspace_home",
]

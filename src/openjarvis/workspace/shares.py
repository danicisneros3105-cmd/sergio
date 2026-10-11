# ruff: noqa: E501 — the share page is an inline HTML template
"""Share one part of the Workspace, and nothing else.

A share link opens a read-only copy of exactly what you chose:

* ``page``  — one page (its sub-pages stay private);
* ``block`` — one block of a page (a list, a chart, a note…);
* ``rows``  — chosen rows of one table;
* ``view``  — one table view (its filter decides which rows are seen).

The link is a long random token (``/s/<token>``); it can expire and be
revoked at any time. Nothing else of the Workspace is reachable through it:
the page is rendered on the server from the scoped blocks only, and files
are served only when the shared part shows them. Encrypted pages cannot be
shared this way (the server cannot read them).
"""

from __future__ import annotations

import html
import json
import re
import secrets
import threading
import time
from typing import Any, Dict, List, Optional

from openjarvis.workspace.store import PAGE_ID, WorkspaceError, WorkspaceStore

SCOPES = ("page", "block", "rows", "view")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{24,64}$")


class Shares:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self.path = store.root / "shares.json"
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def create(
        self,
        page_id: str,
        scope: str = "page",
        *,
        block_id: str = "",
        row_ids: Optional[List[str]] = None,
        view_id: str = "",
        days: Optional[int] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        if scope not in SCOPES:
            raise WorkspaceError("Alcance no válido.")
        if not PAGE_ID.match(page_id or ""):
            raise WorkspaceError("Identificador de página no válido.")
        page = self.store.get(page_id)
        if page is None:
            raise WorkspaceError("No encuentro esa página.")
        if page.get("sealed"):
            raise WorkspaceError("Una página cifrada no se puede compartir con enlace.")
        record = {"page": page_id, "scope": scope, "created": now or time.time()}
        if scope in ("block", "rows", "view"):
            found = next(
                (b for b in page.get("blocks") or [] if b.get("id") == block_id), None
            )
            if found is None:
                raise WorkspaceError("No encuentro ese bloque en la página.")
            if scope in ("rows", "view") and found.get("type") != "table":
                raise WorkspaceError("Solo las tablas tienen filas y vistas.")
            record["block"] = block_id
        if scope == "rows":
            if not row_ids:
                raise WorkspaceError("Elija al menos una fila.")
            record["rows"] = [str(r) for r in row_ids][:500]
        if scope == "view":
            views = (found.get("table") or {}).get("views") or []
            if not any(v.get("id") == view_id for v in views):
                raise WorkspaceError("No encuentro esa vista.")
            record["view"] = view_id
        if days:
            record["expires"] = (now or time.time()) + max(1, int(days)) * 86400
        token = secrets.token_urlsafe(24)
        with self._lock:
            data = self._load()
            data[token] = record
            self._save(data)
        return {"token": token, **record}

    def list(self, page_id: str = "") -> List[Dict[str, Any]]:
        now = time.time()
        return [
            {"token": t, **r}
            for t, r in self._load().items()
            if (not page_id or r.get("page") == page_id)
            and r.get("expires", now + 1) > now
        ]

    def revoke(self, token: str) -> bool:
        with self._lock:
            data = self._load()
            if token not in data:
                return False
            del data[token]
            self._save(data)
            return True

    def resolve(
        self, token: str, now: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        if not TOKEN.match(token or ""):
            return None
        record = self._load().get(token)
        if not record or record.get("expires", float("inf")) <= (now or time.time()):
            return None
        return record


def _view_rows(table: Dict[str, Any], view: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = [r for r in table.get("rows") or [] if not r.get("archived")]
    filt = view.get("filter") or None
    if filt:
        col, op, value = (
            filt.get("column"),
            filt.get("op"),
            str(filt.get("value") or ""),
        )

        def keep(row: Dict[str, Any]) -> bool:
            cell = str((row.get("cells") or {}).get(col, ""))
            if op == "is":
                return cell.lower() == value.lower()
            if op == "not":
                return cell.lower() != value.lower()
            if op == "contains":
                return value.lower() in cell.lower()
            try:
                a, b = float(cell.replace(",", ".")), float(value.replace(",", "."))
            except ValueError:
                return False
            return a > b if op == "gt" else a < b if op == "lt" else True

        rows = [r for r in rows if keep(r)]
    return rows


def scoped_blocks(page: Dict[str, Any], share: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Only what the share covers (copies; the page itself is untouched)."""
    blocks = [
        b
        for b in page.get("blocks") or []
        if isinstance(b, dict) and not b.get("archived")
    ]
    scope = share.get("scope")
    if scope == "page":
        return [b for b in blocks if b.get("type") != "page"]  # sub-pages stay private
    found = next((b for b in blocks if b.get("id") == share.get("block")), None)
    if found is None:
        return []
    found = json.loads(json.dumps(found))
    if scope == "rows":
        wanted = set(share.get("rows") or [])
        found["table"]["rows"] = [
            r for r in found["table"].get("rows") or [] if r.get("id") in wanted
        ]
    elif scope == "view":
        view = next(
            (
                v
                for v in found["table"].get("views") or []
                if v.get("id") == share.get("view")
            ),
            {},
        )
        found["table"]["rows"] = _view_rows(found["table"], view)
    return [found]


def shared_files(blocks: List[Dict[str, Any]]) -> set[str]:
    return {
        str((b.get("media") or {}).get("file"))
        for b in blocks
        if (b.get("media") or {}).get("file")
    }


def _inline(text: str) -> str:
    out = html.escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\[\[(.+?)\]\]", r"<span class='link'>\1</span>", out)
    return out


def render_html(page: Dict[str, Any], blocks: List[Dict[str, Any]], token: str) -> str:
    """A calm read-only page in the Digital Paper look, everything escaped."""
    parts: List[str] = []
    for b in blocks:
        kind, text = b.get("type"), str(b.get("text") or "")
        if kind in ("h1", "h2", "h3"):
            level = {"h1": 2, "h2": 3, "h3": 4}[kind]
            parts.append(f"<h{level}>{_inline(text)}</h{level}>")
        elif kind == "todo":
            mark = "☑" if b.get("checked") else "☐"
            parts.append(f"<p class='todo'>{mark} {_inline(text)}</p>")
        elif kind in ("bullet", "number"):
            parts.append(f"<p class='li'>• {_inline(text)}</p>")
        elif kind in ("quote", "callout"):
            parts.append(f"<blockquote>{_inline(text)}</blockquote>")
        elif kind == "code":
            parts.append(f"<pre>{html.escape(text)}</pre>")
        elif kind == "divider":
            parts.append("<hr>")
        elif kind == "table":
            table = b.get("table") or {}
            cols = table.get("columns") or []
            head = "".join(
                f"<th>{html.escape(str(c.get('name') or ''))}</th>" for c in cols
            )
            rows = "".join(
                "<tr>"
                + "".join(
                    f"<td>{html.escape(str((r.get('cells') or {}).get(c.get('id'), '')))}</td>"
                    for c in cols
                )
                + "</tr>"
                for r in table.get("rows") or []
                if not r.get("archived")
            )
            parts.append(
                f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
            )
        elif kind == "image" and (b.get("media") or {}).get("file"):
            name = html.escape(str(b["media"]["file"]))
            parts.append(f"<img src='/s/{token}/files/{name}' alt=''>")
        elif kind == "audio" and (b.get("media") or {}).get("file"):
            name = html.escape(str(b["media"]["file"]))
            parts.append(f"<audio controls src='/s/{token}/files/{name}'></audio>")
        elif kind == "mindmap":
            from openjarvis.workspace.markdown import mind_outline

            parts.append(
                "<pre>"
                + html.escape("\n".join(mind_outline(b.get("mind") or [])))
                + "</pre>"
            )
        elif text:
            parts.append(f"<p>{_inline(text)}</p>")
    title = html.escape(page.get("title") or "Sin título")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{title}</title><style>
body{{margin:0;background:#e4e5e2;color:#1d1d1c;font:16px/1.6 'Source Sans 3','Segoe UI',system-ui,sans-serif}}
main{{max-width:720px;margin:0 auto;padding:48px 16px}}h1{{font-weight:300;letter-spacing:.2em;text-transform:uppercase;
text-align:center;font-size:22px;margin:0 0 32px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid
rgba(29,29,28,.16);padding:6px 10px;text-align:left}}blockquote{{border-left:2px solid #1d1d1c;margin:0;padding-left:12px}}
pre{{background:#dcddda;padding:12px;overflow:auto}}img{{max-width:100%}}.link{{text-decoration:underline}}
footer{{margin-top:48px;font-size:12px;color:#858683;text-align:center}}
@media (prefers-color-scheme:dark){{body{{background:#151514;color:#ece9e2}}pre{{background:#222220}}
td,th{{border-color:rgba(236,233,226,.13)}}blockquote{{border-color:#ece9e2}}}}</style></head>
<body><main><h1>{title}</h1>{"".join(parts)}<footer>Compartido desde Sergio · solo lectura</footer></main></body></html>"""


__all__ = ["SCOPES", "Shares", "render_html", "scoped_blocks", "shared_files"]

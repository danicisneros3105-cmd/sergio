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


def _form_html(page: Dict[str, Any], b: Dict[str, Any], token: str, nonce: str) -> str:
    """A public form (Notion Forms, with conditional fields): it adds a row to
    its table. No user text ever reaches the script; it only reads data-*."""
    spec = b.get("form") or {}
    table = next(
        (
            x.get("table")
            for x in page.get("blocks") or []
            if x.get("id") == spec.get("table")
        ),
        None,
    )
    if not table:
        return ""
    cols = {c.get("id"): c for c in table.get("columns") or []}
    fields = []
    for f in (spec.get("fields") or [])[:40]:
        col = cols.get(f.get("column"))
        if not col:
            continue
        name = html.escape(str(col["id"]))
        label = html.escape(str(f.get("label") or col.get("name") or ""))
        req = " required" if f.get("required") else ""
        kind = col.get("type")
        if kind in ("select", "multi") and col.get("options"):
            opts = "".join(
                f"<option>{html.escape(str(o))}</option>" for o in col["options"][:50]
            )
            control = (
                f"<select name='{name}'{req}><option value=''></option>{opts}</select>"
            )
        elif kind == "checkbox":
            control = f"<input type='checkbox' name='{name}' value='true'>"
        else:
            itype = {
                "number": "number",
                "date": "date",
                "email": "email",
                "url": "url",
                "phone": "tel",
            }.get(kind, "text")
            control = f"<input type='{itype}' name='{name}' maxlength='2000'{req}>"
        cond = f.get("showIf") or None
        data = ""
        if cond:
            data = (
                f" data-if='{html.escape(str(cond.get('column')))}'"
                f" data-op='{html.escape(str(cond.get('op')))}'"
                f" data-v='{html.escape(str(cond.get('value') or ''))}'"
            )
        fields.append(
            f"<label class='field'{data}><span>{label}</span>{control}</label>"
        )
    title = html.escape(str(spec.get("title") or b.get("text") or "Formulario"))
    action = f"/s/{html.escape(token)}/form/{html.escape(str(b.get('id')))}"
    script = (
        f"<script nonce='{nonce}'>(()=>{{const f=document.currentScript.previousElementSibling;"
        "const val=n=>{const e=f.elements[n];if(!e)return'';if(e.type==='checkbox')return e.checked?'true':'';return (e.value||'').toLowerCase().trim()};"
        "const up=()=>f.querySelectorAll('[data-if]').forEach(l=>{const v=val(l.dataset.if),w=(l.dataset.v||'').toLowerCase().trim(),o=l.dataset.op;"
        "const ok=o==='is'?v===w:o==='not'?v!==w:o==='contains'?v.includes(w):o==='filled'?!!v:o==='empty'?!v:"
        "o==='gt'?parseFloat(v)>parseFloat(w):o==='lt'?parseFloat(v)<parseFloat(w):true;"
        "l.hidden=!ok;l.querySelectorAll('input,select').forEach(i=>i.disabled=!ok)});"
        "f.addEventListener('input',up);up()})()</script>"
    )
    return (
        f"<form class='form' method='post' action='{action}'><h3>{title}</h3>{''.join(fields)}"
        f"<button type='submit'>Enviar</button></form>{script}"
    )


def submit_form(
    page: Dict[str, Any], block_id: str, values: Dict[str, str]
) -> tuple[Dict[str, Any], Dict[str, str]]:
    """Validate a public submission and add it as a row (hidden fields drop)."""
    import secrets

    form_block = next(
        (
            b
            for b in page.get("blocks") or []
            if b.get("id") == block_id and b.get("type") == "form"
        ),
        None,
    )
    if form_block is None:
        raise WorkspaceError("Este formulario ya no existe.")
    spec = form_block.get("form") or {}
    target = next(
        (
            b
            for b in page.get("blocks") or []
            if b.get("id") == spec.get("table") and b.get("table")
        ),
        None,
    )
    if target is None:
        raise WorkspaceError("La tabla de este formulario ya no existe.")
    table = target["table"]
    cols = {c.get("id"): c for c in table.get("columns") or []}
    clean = {k: str(v)[:2000].strip() for k, v in values.items() if k in cols}

    def shown(f: Dict[str, Any]) -> bool:
        cond = f.get("showIf")
        if not cond:
            return True
        v = clean.get(str(cond.get("column")), "").lower()
        w = str(cond.get("value") or "").lower().strip()
        op = cond.get("op")
        try:
            return {
                "is": v == w,
                "not": v != w,
                "contains": w in v,
                "filled": bool(v),
                "empty": not v,
                "gt": op == "gt" and float(v or "nan") > float(w or "nan"),
                "lt": op == "lt" and float(v or "nan") < float(w or "nan"),
            }.get(op, True)
        except ValueError:
            return False

    errors: Dict[str, str] = {}
    keep: Dict[str, str] = {}
    for f in (spec.get("fields") or [])[:40]:
        col = cols.get(f.get("column"))
        if not col or not shown(f):
            continue
        v = clean.get(col["id"], "")
        if f.get("required") and not v:
            errors[col["id"]] = "Obligatorio"
        elif (
            v
            and col.get("type") == "number"
            and not re.fullmatch(r"-?\d+([.,]\d+)?", v)
        ):
            errors[col["id"]] = "Un número"
        elif (
            v
            and col.get("type") == "email"
            and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v)
        ):
            errors[col["id"]] = "Un correo válido"
        elif (
            v
            and col.get("type") == "date"
            and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)
        ):
            errors[col["id"]] = "Una fecha"
        keep[col["id"]] = v
    if errors:
        return page, errors
    if len(table.get("rows") or []) >= 5000:
        raise WorkspaceError("Este formulario ya no admite más respuestas.")
    row = {
        "id": "r_" + secrets.token_hex(6),
        "cells": {cid: keep.get(cid, "") for cid in cols},
    }
    new_page = json.loads(json.dumps(page))
    for b in new_page["blocks"]:
        if b.get("id") == target["id"]:
            b["table"]["rows"] = [*(b["table"].get("rows") or []), row]
    return new_page, {}


def render_html(
    page: Dict[str, Any], blocks: List[Dict[str, Any]], token: str, nonce: str = ""
) -> str:
    """A calm read-only page (or a small website, when the page is set as
    one), everything escaped."""
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
        elif kind == "video" and (b.get("media") or {}).get("file"):
            name = html.escape(str(b["media"]["file"]))
            parts.append(
                f"<video controls playsinline src='/s/{token}/files/{name}'></video>"
            )
        elif kind == "form" and nonce:
            parts.append(_form_html(page, b, token, nonce))
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
    if (page.get("site") or {}).get("on"):
        from openjarvis.workspace.intel import site_html

        nav = [
            {"href": f"#s{i}", "title": str(b.get("text") or "")}
            for i, b in enumerate(blocks)
            if b.get("type") in ("h1", "h2") and b.get("text")
        ]
        body = f"<h1>{title}</h1>" + "".join(parts)
        heads = iter(range(len(blocks)))
        body = re.sub(
            r"<h([23])>",
            lambda m: f"<h{m.group(1)} id='s{_next_head(blocks, heads)}'>",
            body,
        )
        return site_html(page, body + FORM_CSS, nav)
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
{FORM_CSS}<body><main><h1>{title}</h1>{"".join(parts)}<footer>Compartido desde Sergio</footer></main></body></html>"""


FORM_CSS = """<style>.form{display:flex;flex-direction:column;gap:12px;margin:24px 0;padding:20px;border-radius:16px;
border:1px solid rgba(127,127,127,.25)}.form h3{margin:0}.field{display:flex;flex-direction:column;gap:4px;font-size:14px}
.field input,.field select{font:inherit;padding:9px 12px;border-radius:10px;border:1px solid rgba(127,127,127,.35);
background:transparent;color:inherit}.form button{align-self:flex-start;font:inherit;padding:9px 18px;border-radius:999px;
border:0;background:#0d0d0d;color:#fff;cursor:pointer}video{max-width:100%;border-radius:12px}</style>"""


def _next_head(blocks: List[Dict[str, Any]], counter: Any) -> int:
    for i in counter:
        if blocks[i].get("type") in ("h1", "h2") and blocks[i].get("text"):
            return i
    return 0


__all__ = ["SCOPES", "Shares", "render_html", "scoped_blocks", "shared_files"]

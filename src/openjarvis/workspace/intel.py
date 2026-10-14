# ruff: noqa: E501  (WordprocessingML strings read better whole)
"""The Workspace's server-side helpers for what Notion falls short on.

* ``clip(url)``            web clipper: the main content of a page (not its
                           menus, ads or footers) as Workspace blocks.
* ``markdown_blocks(md)``  Markdown → blocks, so the ``.md`` twin of every
                           page can be edited in any program and come back
                           (two-way sync, see store.py).
* ``docx_bytes(page)``     a Word document of a page (headings, lists,
                           tasks, tables, quotes, code), with no extra
                           library: WordprocessingML written by hand.
* ``agenda(...)``          one calendar: the dated rows and tasks of every
                           page plus the events of every connected calendar.
* ``mail(...)``            one inbox: the recent mail of every connected
                           account (Gmail, Outlook, IMAP), newest first.
"""

from __future__ import annotations

import io
import json
import re
import secrets
import urllib.parse
import zipfile
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Callable, Dict, Iterable, List, Optional
from xml.sax.saxutils import escape as xml_escape

MAX_CLIP_BYTES = 4_000_000


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def block(kind: str, text: str = "", **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"id": _id("b"), "type": kind, "text": text}
    if kind == "todo":
        out["checked"] = bool(extra.pop("checked", False))
    out.update(extra)
    return out


# -- web clipper ---------------------------------------------------------------

_NOISE = re.compile(
    r"(nav|menu|footer|header|sidebar|comment|share|social|cookie|banner|advert|"
    r"promo|related|newsletter|subscribe|breadcrumb|popup|modal)",
    re.I,
)


def _text(el: Any) -> str:
    return re.sub(r"\s+", " ", el.text_content() or "").strip()


def _score(el: Any) -> float:
    """Readability-like: long paragraphs count, link-heavy text does not."""
    paragraphs = el.findall(".//p")
    text = sum(len(_text(p)) for p in paragraphs)
    links = sum(len(_text(a)) for a in el.findall(".//a"))
    ident = f"{el.get('class') or ''} {el.get('id') or ''}"
    penalty = 0.4 if _NOISE.search(ident) else 1.0
    return (text - links * 0.8) * penalty + 30 * len(paragraphs)


def extract(html: str, base_url: str = "") -> Dict[str, Any]:
    """Title and blocks of the main content of an HTML page."""
    from lxml import html as lhtml

    doc = lhtml.fromstring(html)
    for bad in doc.xpath(
        "//script|//style|//noscript|//iframe|//form|//svg|//nav|//footer|//aside"
    ):
        bad.drop_tree()
    title = ""
    for xp in ("//meta[@property='og:title']/@content", "//h1", "//title"):
        found = doc.xpath(xp)
        if found:
            title = found[0] if isinstance(found[0], str) else _text(found[0])
            if title:
                break
    candidates = doc.xpath("//article|//main|//*[@role='main']") or doc.xpath(
        "//div|//section"
    )
    root = max(candidates, key=_score) if candidates else doc
    blocks: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for el in root.iter("h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre", "img"):
        tag = el.tag
        if tag == "img":
            src = el.get("src") or el.get("data-src") or ""
            if src and not src.startswith("data:"):
                url = urllib.parse.urljoin(base_url, src)
                blocks.append(block("bookmark", url))
            continue
        text = _text(el)
        if not text or text in seen or len(text) < 2:
            continue
        # text already taken by an outer element of the same kind
        if tag == "p" and el.getparent() is not None and el.getparent().tag == "li":
            continue
        seen.add(text)
        if tag in ("h1", "h2", "h3", "h4"):
            if fold(text) == fold(title):
                continue
            blocks.append(block({"h1": "h1", "h2": "h2"}.get(tag, "h3"), text))
        elif tag == "li":
            parent = el.getparent()
            ordered = parent is not None and parent.tag == "ol"
            blocks.append(block("number" if ordered else "bullet", text))
        elif tag == "blockquote":
            blocks.append(block("quote", text))
        elif tag == "pre":
            blocks.append(block("code", el.text_content().strip("\n")))
        else:
            blocks.append(block("text", text))
    return {"title": title.strip()[:300], "blocks": blocks[:800]}


def fold(text: str) -> str:
    import unicodedata

    return "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    ).strip()


def clip(url: str, fetch: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
    """The page at *url*, clipped. Private addresses are refused (SSRF)."""
    if not re.match(r"^https?://", url or "", re.I):
        raise ValueError("Pegue un enlace que empiece por http:// o https://")
    if fetch is None:
        fetch = _fetch
    html = fetch(url)
    out = extract(html, url)
    out["blocks"].insert(0, block("bookmark", url))
    out["source"] = url
    return out


def _fetch(url: str) -> str:
    import httpx

    from openjarvis.security.ssrf import check_ssrf

    current = url
    for _ in range(6):
        problem = check_ssrf(current)
        if problem:
            raise ValueError("Ese enlace apunta a una red privada.")
        resp = httpx.get(
            current,
            timeout=15,
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (Sergio Workspace)"},
        )
        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get(
            "location"
        ):
            current = urllib.parse.urljoin(str(resp.url), resp.headers["location"])
            continue
        resp.raise_for_status()
        if len(resp.content) > MAX_CLIP_BYTES:
            raise ValueError("La página es demasiado grande para recortarla.")
        return resp.text
    raise ValueError("Demasiadas redirecciones.")


# -- Markdown → blocks (two-way sync) ---------------------------------------------

_TODO = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBER = re.compile(r"^\s*\d+[.)]\s+(.*)$")


def _parse_table(lines: List[str]) -> Dict[str, Any]:
    def cells(line: str) -> List[str]:
        return [
            c.strip().replace("\\|", "|") for c in line.strip().strip("|").split("|")
        ]

    head = cells(lines[0])
    columns = [
        {"id": _id("c"), "name": h or f"Columna {i + 1}", "type": "text"}
        for i, h in enumerate(head)
    ]
    rows = []
    for line in lines[2:]:
        values = cells(line)
        rows.append(
            {
                "id": _id("r"),
                "cells": {
                    c["id"]: (values[i] if i < len(values) else "")
                    for i, c in enumerate(columns)
                },
            }
        )
    view = {"id": _id("v"), "name": "Tabla", "kind": "table"}
    return {"columns": columns, "rows": rows, "views": [view], "view": view["id"]}


def markdown_blocks(md: str) -> Dict[str, Any]:
    """Front matter, title and blocks from a page's Markdown (what
    page_markdown writes, or anything a person typed in another editor)."""
    text = md.replace("\r\n", "\n")
    front: Dict[str, Any] = {}
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            for line in text[4:end].splitlines():
                key, _, value = line.partition(":")
                try:
                    front[key.strip()] = json.loads(value.strip())
                except ValueError:
                    front[key.strip()] = value.strip()
            text = text[end + 5 :]
    lines = text.split("\n")
    title = front.get("title") or ""
    blocks: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("# ") and not blocks and not title:
            title = stripped[2:].strip()
            i += 1
            continue
        if stripped.startswith("# ") and fold(stripped[2:]) == fold(str(title)):
            i += 1
            continue
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            body: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            content = "\n".join(body)
            if lang.startswith("sergio-"):
                kind = lang[len("sergio-") :]
                try:
                    blocks.append(block(kind, "", **{kind: json.loads(content)}))
                    continue
                except ValueError:
                    pass
            blocks.append(block("code", content, lang=lang))
            continue
        if stripped == "$$":
            body = []
            i += 1
            while i < len(lines) and lines[i].strip() != "$$":
                body.append(lines[i])
                i += 1
            i += 1
            blocks.append(block("equation", "\n".join(body)))
            continue
        if (
            stripped.startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1])
        ):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            blocks.append(block("table", "", table=_parse_table(rows)))
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            # page_markdown writes h1 as «##» (the «#» is the page title)
            level = (
                max(1, len(heading.group(1)) - 1) if len(heading.group(1)) > 1 else 1
            )
            blocks.append(block(f"h{min(level, 3)}", heading.group(2).strip()))
        elif stripped in ("---", "***", "___"):
            blocks.append(block("divider"))
        elif m := _TODO.match(line):
            blocks.append(block("todo", m.group(2).strip(), checked=m.group(1) != " "))
        elif m := _BULLET.match(line):
            blocks.append(block("bullet", m.group(1).strip()))
        elif m := _NUMBER.match(line):
            blocks.append(block("number", m.group(1).strip()))
        elif stripped.startswith("> **Nota:**"):
            blocks.append(block("callout", stripped[len("> **Nota:**") :].strip()))
        elif stripped.startswith(">"):
            blocks.append(block("quote", stripped.lstrip("> ").strip()))
        elif m := re.match(r"^\[\[(.+)\]\]$", stripped):
            blocks.append(block("text", f"[[{m.group(1)}]]"))
        elif m := re.match(r"^<(https?://\S+)>$", stripped):
            blocks.append(block("bookmark", m.group(1)))
        else:
            blocks.append(block("text", stripped))
        i += 1
    return {"front": front, "title": str(title), "blocks": blocks or [block("text")]}


# -- Word ------------------------------------------------------------------------------

_DOCX_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)
_DOCX_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)
_DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _style(sid: str, name: str, size: int, bold: bool = False, extra: str = "") -> str:
    return (
        f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>'
        f'<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="200" w:after="80"/>{extra}</w:pPr>'
        f'<w:rPr>{"<w:b/>" if bold else ""}<w:sz w:val="{size}"/></w:rPr></w:style>'
    )


_STYLES = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>'
    '<w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
    '<w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:style>'
    + _style("Title", "Title", 48, True)
    + _style("Heading1", "heading 1", 36, True)
    + _style("Heading2", "heading 2", 30, True)
    + _style("Heading3", "heading 3", 26, True)
    + _style("Quote", "Quote", 22, False, '<w:ind w:left="567"/>')
    + "</w:styles>"
)


def _run(
    text: str, *, bold: bool = False, mono: bool = False, strike: bool = False
) -> str:
    props = ""
    if bold:
        props += "<w:b/>"
    if strike:
        props += "<w:strike/>"
    if mono:
        props += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>'
    parts = text.split("\n")
    body = "<w:br/>".join(
        f'<w:t xml:space="preserve">{xml_escape(p)}</w:t>' for p in parts
    )
    return f"<w:r>{f'<w:rPr>{props}</w:rPr>' if props else ''}{body}</w:r>"


def _para(text: str, style: str = "", prefix: str = "", **run: Any) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{_run(prefix) if prefix else ''}{_run(text, **run)}</w:p>"


def _table(table: Dict[str, Any]) -> str:
    cols = [c for c in table.get("columns") or [] if isinstance(c, dict)]
    if not cols:
        return ""
    border = "".join(
        f'<w:{s} w:val="single" w:sz="4" w:color="BBBBBB"/>'
        for s in ("top", "left", "bottom", "right", "insideH", "insideV")
    )

    def row(values: Iterable[str], bold: bool = False) -> str:
        return (
            "<w:tr>"
            + "".join(
                f"<w:tc><w:p>{_run(str(v), bold=bold)}</w:p></w:tc>" for v in values
            )
            + "</w:tr>"
        )

    rows = [row((c.get("name") or "" for c in cols), bold=True)]
    for r in table.get("rows") or []:
        if isinstance(r, dict) and not r.get("archived"):
            cells = r.get("cells") or {}
            rows.append(row(cells.get(c.get("id"), "") for c in cols))
    return (
        f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>{border}</w:tblBorders></w:tblPr>'
        + "".join(rows)
        + "</w:tbl><w:p/>"
    )


def docx_bytes(page: Dict[str, Any]) -> bytes:
    body: List[str] = [_para(page.get("title") or "Sin título", "Title")]
    number = 0
    for b in page.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        kind, text = b.get("type"), str(b.get("text") or "")
        number = number + 1 if kind == "number" else 0
        if kind in ("h1", "h2", "h3"):
            body.append(_para(text, f"Heading{kind[1]}"))
        elif kind == "bullet":
            body.append(_para(text, prefix="•  "))
        elif kind == "number":
            body.append(_para(text, prefix=f"{number}.  "))
        elif kind == "todo":
            body.append(
                _para(
                    text,
                    prefix="☑  " if b.get("checked") else "☐  ",
                    strike=bool(b.get("checked")),
                )
            )
        elif kind in ("quote", "callout"):
            body.append(_para(text, "Quote"))
        elif kind == "code":
            body.append(_para(text, mono=True))
        elif kind == "divider":
            body.append(_para("—" * 20))
        elif kind == "table":
            body.append(_table(b.get("table") or {}))
        elif kind == "equation":
            body.append(_para(text, mono=True))
        elif text:
            body.append(_para(text))
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>'
        + "".join(body)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _DOCX_TYPES)
        z.writestr("_rels/.rels", _DOCX_RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", _STYLES)
    return buf.getvalue()


# -- one calendar, one inbox --------------------------------------------------------------

CALENDAR_SOURCES = (
    "gcalendar",
    "google_calendar",
    "outlook_calendar",
    "apple_calendar",
    "calendar",
    "caldav",
)
MAIL_SOURCES = ("gmail", "gmail_imap", "outlook", "imap", "email")


def _iso(ts: Any) -> str:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return str(ts or "")


def page_dates(pages: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dated table rows and lines that mention a date (YYYY-MM-DD)."""
    out: List[Dict[str, Any]] = []
    for p in pages:
        if p.get("archived") or p.get("sealed"):
            continue
        for b in p.get("blocks") or []:
            table = b.get("table") if isinstance(b, dict) else None
            if table:
                cols = table.get("columns") or []
                if not cols:
                    continue
                first = cols[0].get("id")
                for c in cols:
                    if c.get("type") != "date":
                        continue
                    for r in table.get("rows") or []:
                        value = str((r.get("cells") or {}).get(c.get("id"), ""))
                        if re.match(r"^\d{4}-\d{2}-\d{2}", value) and not r.get(
                            "archived"
                        ):
                            out.append(
                                {
                                    "date": value[:10],
                                    "title": (r.get("cells") or {}).get(first)
                                    or c.get("name"),
                                    "where": p.get("title") or "",
                                    "page": p.get("id"),
                                    "kind": "tarea",
                                }
                            )
            elif isinstance(b, dict):
                m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", str(b.get("text") or ""))
                if m:
                    out.append(
                        {
                            "date": m.group(1),
                            "title": str(b.get("text"))
                            .replace(m.group(1), "")
                            .strip()[:120]
                            or p.get("title"),
                            "where": p.get("title") or "",
                            "page": p.get("id"),
                            "kind": "nota",
                            "done": bool(b.get("checked")),
                        }
                    )
    return out


def _knowledge(
    query: str, sources: Iterable[str], since: datetime, top_k: int
) -> List[Dict[str, Any]]:
    try:
        from openjarvis.connectors.store import KnowledgeStore
    except Exception:  # noqa: BLE001
        return []
    out: List[Dict[str, Any]] = []
    try:
        with KnowledgeStore() as store:
            for source in sources:
                try:
                    rows = store._conn.execute(  # noqa: SLF001 — read-only listing
                        "SELECT content, source, metadata, timestamp FROM knowledge_chunks "
                        "WHERE source = ? AND deleted_at IS NULL AND timestamp >= ? "
                        "ORDER BY timestamp DESC LIMIT ?",
                        (source, since.isoformat(), top_k),
                    ).fetchall()
                except Exception:  # noqa: BLE001 — older schema
                    continue
                for row in rows:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                    content = str(row["content"] or "")
                    if query and fold(query) not in fold(
                        content + json.dumps(meta, ensure_ascii=False)
                    ):
                        continue
                    out.append(
                        {
                            "content": content,
                            "source": row["source"],
                            "meta": meta,
                            "timestamp": _iso(row["timestamp"]),
                        }
                    )
    except Exception:  # noqa: BLE001 — no knowledge base yet
        return []
    return out


def agenda(pages: Iterable[Dict[str, Any]], days: int = 30) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    items = page_dates(pages)
    for ev in _knowledge("", CALENDAR_SOURCES, now - timedelta(days=days), 300):
        meta = ev["meta"]
        start = str(meta.get("start") or meta.get("start_time") or ev["timestamp"])[:16]
        items.append(
            {
                "date": start[:10],
                "time": start[11:16] if len(start) > 11 else "",
                "title": meta.get("title") or meta.get("summary") or ev["content"][:80],
                "where": meta.get("calendar") or ev["source"],
                "kind": "evento",
            }
        )
    lo = (now - timedelta(days=days)).date().isoformat()
    hi = (now + timedelta(days=days * 3)).date().isoformat()
    return sorted(
        (i for i in items if lo <= i["date"] <= hi),
        key=lambda i: (i["date"], i.get("time", "")),
    )


def mail(query: str = "", days: int = 14, limit: int = 80) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    rows = _knowledge(query, MAIL_SOURCES, now - timedelta(days=days), limit)
    seen: set[str] = set()
    out = []
    for r in sorted(rows, key=lambda r: r["timestamp"], reverse=True):
        meta = r["meta"]
        key = str(meta.get("doc_id") or meta.get("message_id") or r["content"][:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": key,
                "account": meta.get("account") or meta.get("to") or r["source"],
                "from": meta.get("author") or meta.get("from") or "",
                "subject": meta.get("title") or meta.get("subject") or "(sin asunto)",
                "date": r["timestamp"],
                "preview": re.sub(r"\s+", " ", r["content"])[:400],
            }
        )
    return out[:limit]


def site_html(page: Dict[str, Any], body_html: str, nav: List[Dict[str, str]]) -> str:
    """A published page as a small website (theme, accent, font, navigation)."""
    site = page.get("site") or {}
    dark = site.get("theme") == "oscuro"
    accent = (
        site.get("accent")
        if re.fullmatch(r"#[0-9a-fA-F]{6}", str(site.get("accent") or ""))
        else "#0d0d0d"
    )
    font = (
        "'Josefin Sans', system-ui, sans-serif"
        if site.get("font") == "marca"
        else "system-ui, -apple-system, Segoe UI, sans-serif"
    )
    links = (
        "".join(f'<a href="{escape(n["href"])}">{escape(n["title"])}</a>' for n in nav)
        if site.get("nav")
        else ""
    )
    return (
        "<!doctype html><html lang=es><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{escape(page.get('title') or 'Sergio')}</title>"
        "<style>"
        f":root{{--bg:{'#212121' if dark else '#ffffff'};--fg:{'#ececec' if dark else '#0d0d0d'};--accent:{accent}}}"
        f"body{{margin:0;background:var(--bg);color:var(--fg);font:17px/1.65 {font}}}"
        "main{max-width:760px;margin:0 auto;padding:56px 20px}"
        "h1,h2,h3{line-height:1.25}a{color:var(--accent)}"
        "nav{display:flex;gap:18px;flex-wrap:wrap;padding:16px 20px;border-bottom:1px solid rgba(127,127,127,.2)}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid rgba(127,127,127,.3);padding:6px 10px}"
        "img{max-width:100%;border-radius:12px}"
        "</style>"
        f"{f'<nav>{links}</nav>' if links else ''}<main>{body_html}</main></html>"
    )


__all__ = [
    "agenda",
    "clip",
    "docx_bytes",
    "extract",
    "mail",
    "markdown_blocks",
    "page_dates",
    "site_html",
]


# -- teams: three-way merge (same rules as brain.ts merge3) --------------------------


def _key(b: Dict[str, Any]) -> str:
    extra = b.get("table") or b.get("chart") or b.get("mind") or b.get("media") or ""
    return f"{b.get('type')}|{b.get('text')}|{b.get('checked', '')}|{json.dumps(extra, sort_keys=True, ensure_ascii=False)}"


def merge3(
    base: List[Dict[str, Any]], mine: List[Dict[str, Any]], theirs: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], int]:
    """Edits to different blocks both stay; a block both sides changed keeps
    theirs and adds ours right after it, marked ``conflict`` — nothing lost."""
    B = {b["id"]: b for b in base if isinstance(b, dict) and "id" in b}
    M = {b["id"]: b for b in mine if isinstance(b, dict) and "id" in b}
    T = {b["id"]: b for b in theirs if isinstance(b, dict) and "id" in b}

    def changed(x: Optional[Dict[str, Any]], y: Optional[Dict[str, Any]]) -> bool:
        return x is not None and y is not None and _key(x) != _key(y)

    after: Dict[str, List[Dict[str, Any]]] = {}
    prev = ""
    for b in M.values():
        if b["id"] not in B and b["id"] not in T:
            after.setdefault(prev, []).append(b)
        prev = b["id"]
    out: List[Dict[str, Any]] = []
    placed: set[str] = set()
    conflicts = 0

    def emit(b: Dict[str, Any]) -> None:
        if b["id"] in placed:
            return
        placed.add(b["id"])
        out.append(b)
        for n in after.get(b["id"], []):
            emit(n)

    for n in after.get("", []):
        emit(n)
    for t in T.values():
        b, m = B.get(t["id"]), M.get(t["id"])
        if b is not None and m is None:
            if changed(b, t):
                emit(t)
            continue
        if b is None or m is None:
            emit(t)
            continue
        mine_changed, theirs_changed = changed(b, m), changed(b, t)
        if mine_changed and theirs_changed and changed(m, t):
            conflicts += 1
            emit(t)
            copy = {**m, "id": _id("b"), "conflict": True}
            placed.add(copy["id"])
            out.append(copy)
            for n in after.get(m["id"], []):
                emit(n)
        else:
            emit(m if mine_changed else t)
    for m in M.values():
        if (
            m["id"] not in placed
            and m["id"] in B
            and m["id"] not in T
            and changed(B[m["id"]], m)
        ):
            emit(m)
    return out, conflicts

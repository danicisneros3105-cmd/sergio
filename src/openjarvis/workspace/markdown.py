"""A Workspace page as Markdown: the portable copy kept next to the JSON.

The JSON is lossless (what the app edits); this Markdown is what any other
tool can open if Sergio is gone: headings, lists, tasks, GitHub tables,
code, and the special blocks (charts, timers) as fenced JSON.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, List


def _cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def table_markdown(table: Dict[str, Any]) -> str:
    columns = [c for c in table.get("columns") or [] if isinstance(c, dict)]
    if not columns:
        return ""
    head = "| " + " | ".join(_cell(c.get("name")) for c in columns) + " |"
    rule = "| " + " | ".join("---" for _ in columns) + " |"
    rows = []
    for row in table.get("rows") or []:
        if not isinstance(row, dict) or row.get("archived"):
            continue
        cells = row.get("cells") or {}
        rows.append("| " + " | ".join(_cell(cells.get(c.get("id"), "")) for c in columns) + " |")
    return "\n".join([head, rule, *rows])


def mind_outline(nodes: Iterable[Dict[str, Any]]) -> List[str]:
    nodes = [n for n in nodes if isinstance(n, dict)]
    lines: List[str] = []

    def walk(parent: Any, depth: int) -> None:
        if depth > 32:
            return
        for n in nodes:
            if n.get("parent") == parent:
                lines.append(f"{'  ' * depth}- {n.get('text', '')}")
                walk(n.get("id"), depth + 1)

    walk(None, 0)
    return lines


def blocks_markdown(blocks: Iterable[Dict[str, Any]], title_of: Callable[[str], str] = lambda _id: "") -> str:
    out: List[str] = []
    number = 0
    for b in blocks:
        if not isinstance(b, dict):
            continue
        kind, text = b.get("type", "text"), str(b.get("text") or "")
        number = number + 1 if kind == "number" else 0
        if kind == "h1":
            out.append(f"## {text}")
        elif kind == "h2":
            out.append(f"### {text}")
        elif kind == "h3":
            out.append(f"#### {text}")
        elif kind == "todo":
            out.append(f"- [{'x' if b.get('checked') else ' '}] {text}")
        elif kind == "bullet":
            out.append(f"- {text}")
        elif kind == "number":
            out.append(f"{number}. {text}")
        elif kind == "quote":
            out.append(f"> {text}")
        elif kind == "callout":
            out.append(f"> **Nota:** {text}")
        elif kind == "code":
            out.extend([f"```{b.get('lang') or ''}", text, "```"])
        elif kind == "divider":
            out.append("---")
        elif kind == "toggle":
            out.append(f"<details><summary>{text}</summary></details>")
        elif kind == "table":
            out.append(table_markdown(b.get("table") or {}))
        elif kind in ("chart", "pomodoro"):
            out.extend([f"```sergio-{kind}", json.dumps(b.get(kind) or {}, ensure_ascii=False), "```"])
        elif kind == "mindmap":
            out.extend(mind_outline(b.get("mind") or []))
        elif kind in ("audio", "image"):
            media = b.get("media") or {}
            if media.get("file"):
                out.append(f"[{media.get('name') or media['file']}](files/{media['file']})")
        elif kind == "page":
            out.append(f"[[{title_of(str(b.get('pageId') or '')) or text}]]")
        else:
            out.append(text)
        out.append("")
    return "\n".join(out)


def page_markdown(page: Dict[str, Any], title_of: Callable[[str], str] = lambda _id: "") -> str:
    """Front matter, the title and the blocks."""
    front = {
        "id": page.get("id"),
        "title": page.get("title") or "",
        "parent": page.get("parent"),
        "tags": page.get("tags") or [],
        "created": page.get("createdAt"),
        "updated": page.get("updatedAt"),
    }
    lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in front.items()] + ["---", ""]
    if page.get("sealed"):
        body = "_Página cifrada de extremo a extremo: solo se abre con su frase en la app._\n"
    else:
        body = blocks_markdown(page.get("blocks") or [], title_of)
    text = "\n".join(lines) + f"# {page.get('title') or 'Sin título'}\n\n" + body
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.rstrip() + "\n"


__all__ = ["blocks_markdown", "mind_outline", "page_markdown", "table_markdown"]

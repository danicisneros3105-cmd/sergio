"""What code does with a swarm's report: check it, then hand it over.

The supervisor is a model, and a model can slip in a link nobody visited or
a figure nobody found. Before you read the report, code checks it against
what the sub-agents actually brought back:

* every **link** in the report must be one a sub-agent cited;
* every **figure** (prices, percentages, amounts…) must appear in some
  sub-agent's result, in the task or in the run's own counts;
* every **document** handed in must have been read, and named in the report.

What does not check out is listed under «Comprobación automática» at the end
of the report, so it is never passed off as fact.

Then the hand-over: the report as Markdown (with its sources), its tables as
CSV, or a page in your Workspace.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

URL = re.compile(r"https?://[^\s)\]>»\"'<]+")
# A figure: 1.234,56 · 1,234.56 · 12 % · 3.5 · 600 € — digits with separators.
NUMBER = re.compile(r"(?<![\w/#])(\d{1,3}(?:[.,  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)")
SMALL = 10  # list numbers, «3 opciones»: too common to check
MAX_LISTED = 25


def urls_in(text: str) -> List[str]:
    out: List[str] = []
    for url in URL.findall(text or ""):
        url = url.rstrip(".,;:!?")
        if url not in out:
            out.append(url)
    return out


def _url_key(url: str) -> str:
    url = url.strip().rstrip("/").lower()
    url = re.sub(r"^https?://(www\.)?", "", url)
    return url.split("#", 1)[0]


def number_values(token: str) -> Set[float]:
    """Every value a written figure can mean (Spanish or English separators)."""
    token = token.replace(" ", " ").strip()
    values: Set[float] = set()
    plain = token.replace(" ", "")
    candidates = {
        plain.replace(".", "").replace(",", "."),  # 1.234,5 → 1234.5
        plain.replace(",", ""),  # 1,234.5 → 1234.5
        plain.replace(",", "."),  # 3,5 → 3.5
    }
    for c in candidates:
        try:
            values.add(round(float(c), 4))
        except ValueError:
            continue
    return values


def figures(text: str) -> List[str]:
    """The figures worth checking: not inside links, not tiny list numbers."""
    text = URL.sub(" ", text or "")
    text = re.sub(r"^\s*#+\s*\d+[.)]?", " ", text, flags=re.M)  # «## 3. Título»
    text = re.sub(r"^\s*\d+[.)]\s", " ", text, flags=re.M)  # «1. punto»
    out: List[str] = []
    for m in NUMBER.finditer(text):
        token = m.group(1)
        values = number_values(token)
        if not values or all(abs(v) <= SMALL for v in values):
            continue
        if token not in out:
            out.append(token)
    return out


def _evidence_values(texts: Iterable[str]) -> Set[float]:
    values: Set[float] = set()
    for text in texts:
        for m in NUMBER.finditer(text or ""):
            values |= number_values(m.group(1))
    return values


def verify_report(
    report: str,
    results: Sequence[str],
    sources: Iterable[str],
    documents: Sequence[Dict[str, str]] = (),
    extra_evidence: Sequence[str] = (),
) -> Dict[str, Any]:
    """Check *report* against the sub-agents' *results*.

    ``documents`` are ``{"name": …, "status": …}`` for each document's reader.
    """
    known = {_url_key(u) for u in sources}
    known |= {_url_key(u) for r in results for u in urls_in(r)}
    links = urls_in(report)
    bad_links = [u for u in links if _url_key(u) not in known]

    evidence = _evidence_values([*results, *extra_evidence])
    found = figures(report)
    unbacked = [f for f in found if not (number_values(f) & evidence)]

    low = (report or "").lower()
    missing = [d["name"] for d in documents if d.get("status") != "done"]
    unmentioned = []
    for d in documents:
        name = d["name"]
        stem = name.rsplit(".", 1)[0]
        if (
            d.get("status") == "done"
            and name.lower() not in low
            and stem.lower() not in low
        ):
            unmentioned.append(name)
    return {
        "links": len(links),
        "links_unverified": bad_links[:MAX_LISTED],
        "figures": len(found),
        "figures_unbacked": unbacked[:MAX_LISTED],
        "documents": len(documents),
        "documents_unread": missing[:MAX_LISTED],
        "documents_unmentioned": unmentioned[:MAX_LISTED],
        "ok": not (bad_links or unbacked or missing or unmentioned),
    }


def issues(checks: Dict[str, Any]) -> int:
    return sum(
        len(checks.get(k) or [])
        for k in (
            "links_unverified",
            "figures_unbacked",
            "documents_unread",
            "documents_unmentioned",
        )
    )


def check_note(checks: Dict[str, Any]) -> str:
    """The «Comprobación automática» section, or "" when all checks out."""
    if not checks or checks.get("ok"):
        return ""
    lines: List[str] = []
    if checks.get("links_unverified"):
        lines.append(
            "**Enlaces que ningún subagente citó** (no los dé por verificados): "
            + ", ".join(checks["links_unverified"])
        )
    if checks.get("figures_unbacked"):
        lines.append(
            "**Cifras que no aparecen en los resultados de los subagentes**: "
            + ", ".join(checks["figures_unbacked"])
        )
    if checks.get("documents_unread"):
        lines.append(
            "**Documentos que no se pudieron leer**: "
            + ", ".join(checks["documents_unread"])
        )
    if checks.get("documents_unmentioned"):
        lines.append(
            "**Documentos leídos que el informe no menciona**: "
            + ", ".join(checks["documents_unmentioned"])
        )
    return "\n\n---\n\n## Comprobación automática\n\n" + "\n\n".join(lines) + "\n"


# -- tables ---------------------------------------------------------------------------
def _cells(line: str) -> List[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [c.strip().replace("\\|", "|") for c in cells]


RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def tables_in(markdown: str) -> List[List[List[str]]]:
    """Every GitHub-style table in *markdown*, as rows of cells (header first)."""
    lines = (markdown or "").splitlines()
    tables: List[List[List[str]]] = []
    i = 0
    while i < len(lines) - 1:
        if "|" in lines[i] and RULE.match(lines[i + 1]):
            head = _cells(lines[i])
            rows = [head]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                row = _cells(lines[i])
                rows.append((row + [""] * len(head))[: len(head)])
                i += 1
            tables.append(rows)
        else:
            i += 1
    return tables


def tables_csv(markdown: str) -> str:
    """All the report's tables as CSV (a blank line between tables)."""
    out = io.StringIO()
    writer = csv.writer(out)
    for n, table in enumerate(tables_in(markdown)):
        if n:
            writer.writerow([])
        for row in table:
            writer.writerow([re.sub(r"\*\*|__|`", "", c) for c in row])
    return out.getvalue()


# -- Markdown -------------------------------------------------------------------------
def report_markdown(run: Dict[str, Any]) -> str:
    """The report with a header and its sources, ready to save or share."""
    title = run.get("title") or run.get("task") or "Agent Swarm"
    counts = run.get("counts") or {}
    report = (run.get("report") or "").strip()
    head = (
        f"> Agent Swarm · {len(run.get('subtasks') or [])} subagentes "
        f"({counts.get('done', 0)} terminados) · {run.get('tool_calls', 0)} llamadas a herramientas · "
        f"{run.get('elapsed', 0)} s\n> Tarea: {run.get('task', '')}"
    )
    body = report if report.lstrip().startswith("#") else f"# {title}\n\n{report}"
    first, _, rest = body.partition("\n")
    parts = [first, "", head, "", rest.strip()]
    sources = run.get("sources") or []
    if sources:
        parts += ["", "## Fuentes", ""] + [f"- {u}" for u in sources]
    return "\n".join(parts).strip() + "\n"


# -- Workspace ------------------------------------------------------------------------
def _bid() -> str:
    return "b_" + secrets.token_hex(6)


def markdown_blocks(markdown: str) -> List[Dict[str, Any]]:
    """Markdown → Workspace blocks (headings, lists, quotes, code, tables)."""
    blocks: List[Dict[str, Any]] = []
    lines = (markdown or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        text = line.strip()
        if not text:
            i += 1
            continue
        if text.startswith("```"):
            lang = text[3:].strip()
            body: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            blocks.append(
                {"id": _bid(), "type": "code", "text": "\n".join(body), "lang": lang}
            )
            i += 1
            continue
        if "|" in text and i + 1 < len(lines) and RULE.match(lines[i + 1]):
            table = tables_in("\n".join(lines[i:]))[0]
            cols = [
                {"id": f"c{n}", "name": name or f"Columna {n + 1}", "type": "text"}
                for n, name in enumerate(table[0])
            ]
            rows = [
                {
                    "id": "r_" + secrets.token_hex(4),
                    "cells": {f"c{n}": v for n, v in enumerate(r)},
                }
                for r in table[1:]
            ]
            view = {"id": "v_tabla", "name": "Tabla", "kind": "table"}
            blocks.append(
                {
                    "id": _bid(),
                    "type": "table",
                    "text": "",
                    "table": {
                        "columns": cols,
                        "rows": rows,
                        "views": [view],
                        "view": view["id"],
                    },
                }
            )
            i += len(table) + 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", text)
        if m:
            level = min(len(m.group(1)), 3)
            blocks.append(
                {"id": _bid(), "type": f"h{level}", "text": m.group(2).strip()}
            )
        elif re.match(r"^[-*]\s+\[[ xX]\]\s", text):
            blocks.append(
                {
                    "id": _bid(),
                    "type": "todo",
                    "text": text[6:].strip(),
                    "checked": text[3] in "xX",
                }
            )
        elif re.match(r"^[-*+]\s", text):
            blocks.append({"id": _bid(), "type": "bullet", "text": text[2:].strip()})
        elif re.match(r"^\d+[.)]\s", text):
            blocks.append(
                {
                    "id": _bid(),
                    "type": "number",
                    "text": re.sub(r"^\d+[.)]\s", "", text),
                }
            )
        elif text.startswith(">"):
            blocks.append(
                {"id": _bid(), "type": "quote", "text": text.lstrip("> ").strip()}
            )
        elif re.match(r"^(-{3,}|\*{3,}|_{3,})$", text):
            blocks.append({"id": _bid(), "type": "divider", "text": ""})
        else:
            blocks.append({"id": _bid(), "type": "text", "text": text})
        i += 1
    return blocks[:4900]


def workspace_page(run: Dict[str, Any], parent: Optional[str] = None) -> Dict[str, Any]:
    now = int(time.time() * 1000)
    return {
        "id": "p_" + secrets.token_hex(8),
        "title": (run.get("title") or "Agent Swarm")[:280],
        "icon": "✳️",
        "parent": parent,
        "blocks": markdown_blocks(report_markdown(run)),
        "createdAt": now,
        "updatedAt": now,
        "openedAt": now,
        "tags": ["agent-swarm"],
    }


__all__ = [
    "check_note",
    "figures",
    "issues",
    "markdown_blocks",
    "number_values",
    "report_markdown",
    "tables_csv",
    "tables_in",
    "urls_in",
    "verify_report",
    "workspace_page",
]

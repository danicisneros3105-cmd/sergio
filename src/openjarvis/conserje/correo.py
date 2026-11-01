"""E-mail at scale, as drafts: one personal draft per contact, never sent.

The owner (1 Nov 2026): «escribir correos electrónicos a gran escala». The
team rule stands: e-mail is drafts only. Sergio writes one draft per contact
from a template ({nombre}, {empresa}… from a CSV), adds a line to stop
receiving them, and saves them as .eml files the owner opens and sends from
his own mail (or as drafts in Gmail when its connector is connected). Up to
500 per batch, so no one is spammed by mistake.
"""

from __future__ import annotations

import csv
import re
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List

MAX = 500
OPT_OUT = "\n\nSi prefiere no recibir más mensajes como este, responda «no» y no le escribiré otra vez."
_FIELD = re.compile(r"\{(\w+)\}")


def read_contacts(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [
            {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            for row in csv.DictReader(f)
        ]
    return [r for r in rows if "@" in r.get("email", r.get("correo", ""))]


def fill(template: str, row: Dict[str, str]) -> str:
    return _FIELD.sub(lambda m: row.get(m.group(1).lower(), ""), template)


def drafts(
    subject: str,
    template: str,
    contacts: List[Dict[str, str]],
    out_dir: Path,
    *,
    sender: str = "",
) -> Dict[str, Any]:
    """Write the .eml drafts; returns where they are and how many."""
    if not contacts:
        raise ValueError("No hay contactos con correo en la lista.")
    out_dir.mkdir(parents=True, exist_ok=True)
    made: List[str] = []
    for i, row in enumerate(contacts[:MAX], 1):
        to = row.get("email") or row.get("correo") or ""
        msg = EmailMessage()
        msg["To"] = to
        if sender:
            msg["From"] = sender
        msg["Subject"] = fill(subject, row)
        msg["X-Unsent"] = "1"  # Outlook opens it as a draft to send
        msg.set_content(fill(template, row).strip() + OPT_OUT)
        path = out_dir / f"{i:03d}_{re.sub(r'[^a-z0-9]+', '_', to.lower())[:40]}.eml"
        path.write_bytes(bytes(msg))
        made.append(str(path))
    return {
        "borradores": len(made),
        "carpeta": str(out_dir),
        "omitidos": max(0, len(contacts) - MAX),
        "archivos": made,
    }


def gmail_drafts(items: List[Dict[str, str]], hub: Any = None) -> int:
    """The same drafts in Gmail when its connector is connected (never sent)."""
    try:
        from openjarvis.mcp.hub import get_hub

        hub = hub or get_hub()
        sid = next(
            (s["id"] for s in hub.list()
             if "gmail" in f"{s.get('name', '')} {s.get('directory_id', '')}".lower()
             and s.get("connected")),
            "",
        )  # fmt: skip
    except Exception:  # noqa: BLE001
        return 0
    if not sid:
        return 0
    made = 0
    for it in items:
        try:
            hub.call(sid, "create_draft", {"to": it["to"], "subject": it["subject"],
                                           "body": it["body"]})  # fmt: skip
            made += 1
        except Exception:  # noqa: BLE001 — the .eml files are still there
            break
    return made


__all__ = ["MAX", "OPT_OUT", "drafts", "fill", "gmail_drafts", "read_contacts"]

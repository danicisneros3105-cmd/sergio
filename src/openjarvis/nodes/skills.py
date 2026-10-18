# ruff: noqa: E501 — the templates are prose
"""Skills that are code, not prompts: fast, cheap and unable to invent.

A Node that «watches a page» or «waits for an urgent email» does not ask the
model every few minutes. Code fetches the page and compares it with the last
copy (or looks for new items from an app); only when something really
changed does the Node wake up, with the exact difference in hand. That is
how a routine stays instant, costs nothing while nothing happens, and never
reports a change that did not happen.

Also here: the templates you can start a Node from (each one a set of
instructions, rules, routines and a face).
"""

from __future__ import annotations

import difflib
import hashlib
import html
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

MAX_BYTES = 3_000_000
PRICE = re.compile(
    r"(?:(?:US\$|USD|EUR|€|\$|£)\s?(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?))"
    r"|(?:(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s?(?:€|EUR|USD|US\$|\$))"
)
_SCRIPT = re.compile(
    r"<(script|style|noscript|svg|template)[^>]*>.*?</\1>", re.S | re.I
)
_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(
    r"</?(p|div|li|tr|h[1-6]|br|section|article|header|footer|td|th)[^>]*>", re.I
)


def page_text(markup: str) -> str:
    """Visible text of an HTML page, one block per line."""
    text = _SCRIPT.sub(" ", markup or "")
    text = _BLOCK.sub("\n", text)
    text = html.unescape(_TAG.sub(" ", text))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if len(line) > 1)


def fetch_text(url: str, http: Any = None) -> str:
    if http is None:
        import httpx

        http = httpx.Client(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Sergio Node)"},
        )
    resp = http.get(url)
    resp.raise_for_status()
    body = resp.text[:MAX_BYTES]
    kind = resp.headers.get("content-type", "")
    return page_text(body) if "html" in kind or body.lstrip().startswith("<") else body


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:32]


def changes(old: str, new: str, limit: int = 20) -> Tuple[List[str], List[str]]:
    """Lines that appeared and lines that went away."""
    before, after = old.splitlines(), new.splitlines()
    added, removed = [], []
    for line in difflib.ndiff(before, after):
        if line.startswith("+ ") and line[2:].strip():
            added.append(line[2:])
        elif line.startswith("- ") and line[2:].strip():
            removed.append(line[2:])
    return added[:limit], removed[:limit]


def _number(raw: str) -> Optional[float]:
    """«1.299,00», «1,299.00», «1 299», «19,99» → a float (the last separator
    is the decimal one when 1-2 digits follow it)."""
    raw = raw.replace(" ", "")
    m = re.search(r"[.,](\d{1,2})$", raw)
    whole, cents = (raw[: m.start()], m.group(1)) if m else (raw, "")
    whole = re.sub(r"[.,]", "", whole)
    if not whole.isdigit():
        return None
    return float(f"{whole}.{cents}") if cents else float(whole)


def prices(text: str) -> List[float]:
    """Every price in a text, as numbers (1.299,00 € and $1,299.00 both work)."""
    out: List[float] = []
    for m in PRICE.finditer(text or ""):
        value = _number(m.group(1) or m.group(2) or "")
        if value is not None:
            out.append(value)
    return out


def check_page(
    url: str, last_hash: str, last_text: str, fetch: Callable[[str], str] = fetch_text
) -> Dict[str, Any]:
    """{changed, hash, text, added, removed, prices_before, prices_after}."""
    text = fetch(url)
    new_hash = digest(text)
    result: Dict[str, Any] = {
        "changed": False,
        "hash": new_hash,
        "text": text[:200_000],
    }
    if not last_hash:
        return result  # the first look only takes the reference copy
    if new_hash == last_hash:
        return result
    added, removed = changes(last_text, text)
    if not added and not removed:
        return result
    result.update(
        changed=True,
        added=added,
        removed=removed,
        prices_before=prices(last_text)[:20],
        prices_after=prices(text)[:20],
    )
    return result


def describe_page_change(url: str, check: Dict[str, Any]) -> str:
    lines = [f"La página {url} cambió (comprobado por código, no por el modelo)."]
    if check.get("added"):
        lines.append("Apareció:\n" + "\n".join(f"+ {a}" for a in check["added"]))
    if check.get("removed"):
        lines.append("Desapareció:\n" + "\n".join(f"- {r}" for r in check["removed"]))
    before, after = check.get("prices_before") or [], check.get("prices_after") or []
    if before != after and (before or after):
        lines.append(f"Precios antes: {before[:8]} · ahora: {after[:8]}")
    return "\n\n".join(lines)


# -- new items in an app (connectors) -----------------------------------------------
def knowledge_db() -> Path:
    from openjarvis.core.config import DEFAULT_CONFIG_DIR

    return Path(DEFAULT_CONFIG_DIR) / "knowledge.db"


def app_items(
    app: str,
    since_iso: str,
    keywords: List[str],
    db: Optional[Path] = None,
    limit: int = 20,
) -> List[Dict[str, str]]:
    """Documents from *app* newer than *since_iso* (and with a keyword, if
    any), read straight from the knowledge store — no model involved."""
    path = db or knowledge_db()
    if not path.is_file():
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT doc_id, title, author, timestamp, url, substr(content, 1, 400) FROM knowledge_chunks "
            "WHERE source = ? AND timestamp > ? GROUP BY doc_id ORDER BY timestamp DESC LIMIT ?",
            (app, since_iso, limit * 5),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    words = [k.lower() for k in keywords if k]
    out = []
    for doc_id, title, author, ts, url, snippet in rows:
        hay = f"{title} {snippet}".lower()
        if words and not any(w in hay for w in words):
            continue
        out.append(
            {
                "id": doc_id,
                "title": title,
                "author": author,
                "time": ts,
                "url": url,
                "snippet": snippet,
            }
        )
        if len(out) >= limit:
            break
    return out


def describe_app_items(app: str, items: List[Dict[str, str]]) -> str:
    lines = [f"Novedades en {app} (encontradas por código):"]
    for it in items:
        lines.append(
            f"- {it['time'][:16]} · {it.get('author') or ''} · {it.get('title') or ''}: {it.get('snippet', '')[:200]}"
        )
    return "\n".join(lines)


def iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))


# -- templates (Muse/Dots-style starting points) -------------------------------------
TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "vigia",
        "name": "Vigía",
        "title": "Vigila una web",
        "description": "Mira una página cada hora y le avisa solo cuando cambia algo de verdad.",
        "instructions": "Vigilas las páginas que te diga el usuario. Cuando cambien, explica en dos frases qué cambió y si importa.",
        "avatar": {
            "shape": "orb",
            "color": "#bfe6ff",
            "accessory": "none",
            "eyes": "dots",
        },
        "routines": [
            {
                "kind": "web",
                "task": "Dime qué cambió y si importa.",
                "url": "",
                "every_minutes": 60,
            }
        ],
    },
    {
        "id": "precios",
        "name": "Cazador",
        "title": "Sigue precios",
        "description": "Vigila productos y le avisa cuando bajan de precio. Nunca compra.",
        "instructions": "Sigues precios de productos. Compara con el precio anterior y avisa solo de bajadas reales. Nunca compras.",
        "avatar": {
            "shape": "dalmatian",
            "color": "#e8505b",
            "accessory": "none",
            "eyes": "happy",
        },
        "routines": [
            {
                "kind": "web",
                "task": "Si el precio bajó, dime cuánto y el enlace.",
                "url": "",
                "every_minutes": 120,
            }
        ],
    },
    {
        "id": "correo",
        "name": "Mía",
        "title": "Correo y agenda",
        "description": "Un resumen cada mañana y un aviso si llega algo urgente.",
        "instructions": "Llevas el correo y la agenda del usuario: resumes lo importante, preparas borradores de respuesta y avisas de lo urgente. Nunca envías nada.",
        "avatar": {
            "shape": "glove",
            "color": "#5b9cf6",
            "accessory": "beret",
            "eyes": "dots",
        },
        "apps": {"gmail": "read", "gcalendar": "read"},
        "routines": [
            {
                "kind": "time",
                "task": "Resumen del correo y la agenda de hoy, con lo urgente primero.",
                "at": "08:00",
                "days": [0, 1, 2, 3, 4],
            },
            {
                "kind": "app",
                "app": "gmail",
                "keywords": ["urgente", "urgent", "asap", "hoy"],
                "task": "¿Esto es urgente? Si lo es, prepárame un borrador de respuesta.",
                "every_minutes": 30,
            },
        ],
    },
    {
        "id": "noticias",
        "name": "Nora",
        "title": "Noticias de un tema",
        "description": "Cada mañana, lo que pasó en su tema, sin relleno y con enlaces.",
        "instructions": "Cada mañana buscas las noticias del tema del usuario de las últimas 24 horas, quitas lo repetido y lo resumes con enlaces.",
        "avatar": {
            "shape": "rhino",
            "color": "#a9b2c3",
            "accessory": "headphones",
            "eyes": "sleepy",
        },
        "routines": [
            {
                "kind": "time",
                "task": "Noticias de las últimas 24 horas sobre mi tema.",
                "at": "07:30",
                "days": [],
            }
        ],
    },
    {
        "id": "compras",
        "name": "Paco",
        "title": "Asistente de compras",
        "description": "Busca, compara y le deja el carrito preparado. El pago siempre lo hace usted.",
        "instructions": "Buscas y comparas productos (precio, envío, garantía, opiniones) y dejas una tabla y los enlaces. Nunca pagas ni introduces datos de pago.",
        "avatar": {
            "shape": "rhino",
            "color": "#c7b9a6",
            "accessory": "scarf",
            "eyes": "sleepy",
        },
    },
    {
        "id": "facturas",
        "name": "Bruno",
        "title": "Negociador de facturas",
        "description": "Revisa sus facturas, encuentra lo que sobra y le escribe los mensajes para negociar.",
        "instructions": "Revisas facturas y suscripciones del usuario, detectas cobros raros o caros y redactas mensajes para negociar o cancelar. Nunca los envías: los dejas como borrador.",
        "avatar": {
            "shape": "dalmatian",
            "color": "#7c5cff",
            "accessory": "crown",
            "eyes": "big",
        },
    },
    {
        "id": "salud",
        "name": "Vita",
        "title": "Patrones de salud",
        "description": "Lee sus datos de salud conectados y le muestra tendencias. No diagnostica.",
        "instructions": "Analizas los datos de salud que el usuario conectó (sueño, pasos, pulso) y explicas tendencias con números. No diagnosticas ni recetas; ante algo preocupante, recomiendas un profesional.",
        "avatar": {
            "shape": "glove",
            "color": "#5b9cf6",
            "accessory": "beret",
            "eyes": "happy",
        },
    },
    {
        "id": "redes",
        "name": "Lola",
        "title": "Redes sociales",
        "description": "Ideas, borradores de publicaciones y un calendario. Publicar lo decide usted.",
        "instructions": "Preparas ideas, borradores y un calendario de publicaciones con el tono del usuario. Nunca publicas: todo queda como borrador.",
        "avatar": {
            "shape": "glove",
            "color": "#f58ab0",
            "accessory": "beret",
            "eyes": "dots",
        },
    },
    {
        "id": "programador",
        "name": "Dev",
        "title": "Programador",
        "description": "Revisa repositorios y ejecuta los comandos que usted permita (git, pruebas).",
        "instructions": "Trabajas con código: lees repositorios, ejecutas las pruebas y comandos permitidos y propones cambios con explicación. No haces commits ni push sin permiso.",
        "avatar": {
            "shape": "orb",
            "color": "#9ff2cf",
            "accessory": "none",
            "eyes": "dots",
        },
        "rules": {"cli": "ask", "code": "allow"},
    },
    {
        "id": "organizador",
        "name": "Ordo",
        "title": "Organizador",
        "description": "Ordena notas, tareas y archivos en su computadora y su Workspace.",
        "instructions": "Ordenas tareas, notas y archivos: propones estructura, creas listas y páginas, y mantienes todo al día.",
        "avatar": {
            "shape": "rhino",
            "color": "#a9b2c3",
            "accessory": "glasses",
            "eyes": "sleepy",
        },
        "rules": {"workspace": "ask"},
    },
    {
        "id": "tutor",
        "name": "Profe",
        "title": "Tutor de estudio",
        "description": "Planes de estudio, repasos espaciados y exámenes de práctica.",
        "instructions": "Eres tutor: preparas planes de estudio, preguntas de repaso espaciadas y exámenes de práctica, y explicas con ejemplos.",
        "avatar": {
            "shape": "dalmatian",
            "color": "#3f7be8",
            "accessory": "glasses",
            "eyes": "happy",
        },
        "routines": [
            {
                "kind": "time",
                "task": "Cinco preguntas de repaso de lo que estoy estudiando.",
                "at": "19:00",
                "days": [0, 1, 2, 3, 4],
            }
        ],
    },
]


def template(template_id: str) -> Optional[Dict[str, Any]]:
    return next((t for t in TEMPLATES if t["id"] == template_id), None)


__all__ = [
    "TEMPLATES",
    "app_items",
    "changes",
    "check_page",
    "describe_app_items",
    "describe_page_change",
    "digest",
    "fetch_text",
    "iso",
    "page_text",
    "prices",
    "template",
]

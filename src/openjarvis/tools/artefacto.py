"""Artifacts: what Sergio makes that is meant to be seen or used, shown finished
in the chat.

The owner (2 Nov 2026): «Sergio tiene que usar mejor Creator y más seguido
como artefactos». A page, a poster, a chart, a diagram, a calculator, a small
game or a presentation is written by the model as one self-contained HTML file;
this tool checks it, saves it next to Creator's pictures and videos
(``creator/proyectos/artefactos``) and the chat shows it as a card with the
result live, «Abrir» and «Descargar».

It is safe to show whatever the model wrote: the card is a frame with
``sandbox="allow-scripts"`` (no access to Sergio's page, its storage or its
session) and the file carries a content policy that forbids every network
request (nothing can be sent out, nothing is loaded from elsewhere). So
**everything must be inside the file**: no links to scripts, styles, fonts or
pictures on the internet (``data:`` pictures are fine).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

MAX_BYTES = 400 * 1024
KINDS = (
    "pagina",
    "cartel",
    "grafico",
    "diagrama",
    "calculadora",
    "juego",
    "presentacion",
    "documento",
)

# The policy the file carries (a <meta> at the very top; the server adds it again
# when it serves the file, so a file edited by hand keeps it).
POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
    "img-src data: blob:; font-src data:; media-src data:; connect-src 'none'; "
    "form-action 'none'; base-uri 'none'"
)
META = f'<meta http-equiv="Content-Security-Policy" content="{POLICY}">'

_EXTERNAL = re.compile(
    r"""(?:<script[^>]+src\s*=\s*["']?\s*(?:https?:)?//"""
    r"""|<link[^>]+href\s*=\s*["']?\s*(?:https?:)?//"""
    r"""|@import\s+(?:url\()?\s*["']?\s*(?:https?:)?//"""
    r"""|url\(\s*["']?\s*(?:https?:)?//)""",
    re.I,
)
_BASE = (
    "<style>html{color-scheme:light dark}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
    "line-height:1.5}</style>"
)


def external_links(html: str) -> List[str]:
    """Places the file would load from the internet (it cannot: the policy blocks it)."""
    return sorted({m.group(0)[:60] for m in _EXTERNAL.finditer(html or "")})


def wrap(html: str, title: str = "") -> str:
    """A complete document with the policy first, whatever the model sent."""
    text = (html or "").strip()
    low = text[:400].lower()
    if "<html" not in low and "<!doctype" not in low:
        safe = re.sub(r"[<>&]", "", title)[:120] or "Artefacto"
        text = (
            f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{safe}</title>'
            f"{_BASE}</head><body>{text}</body></html>"
        )
    return inject_policy(text)


def inject_policy(html: str) -> str:
    """The policy at the very top of the file (before anything the model wrote)."""
    if META in html:
        return html
    m = re.search(r"<head[^>]*>", html, re.I)
    if m:
        return html[: m.end()] + META + html[m.end() :]
    return META + html


def problem(html: str) -> str:
    """Why a file cannot be shown ('' when it can)."""
    text = html or ""
    if len(text.strip()) < 20:
        return "El archivo está vacío: escriba la página completa."
    if len(text.encode("utf-8")) > MAX_BYTES:
        return f"Es demasiado grande (más de {MAX_BYTES // 1024} KB): hágalo más corto."
    ext = external_links(text)
    if ext:
        return (
            "Todo debe ir dentro del archivo: nada de scripts, estilos, letras o imágenes de internet "
            f"(encontré: {', '.join(ext[:3])}). Escriba el CSS y el JavaScript en la misma página; las "
            "imágenes, como data: o dibujadas en SVG."
        )
    return ""


def save(html: str, title: str = "") -> Dict[str, Any]:
    from openjarvis.creator import studio

    folder = studio.projects_root() / "artefactos"
    folder.mkdir(parents=True, exist_ok=True)
    name = studio.media_name("artefacto", ".html")
    (folder / name).write_text(wrap(html, title), "utf-8")
    return {
        "archivo": name,
        "url": f"/v1/creator/artefacto/{name}",
        "ruta": str(folder / name),
    }


def mark(name: str, title: str = "") -> str:
    """The chat turns this into the card (``ArtifactCard``); never shown as text."""
    clean = re.sub(r"[\]|\n]", " ", title).strip()[:80]
    return f"\n[[artefacto:{name}|{clean}]]"


@ToolRegistry.register("artefacto")
class ArtifactTool(BaseTool):
    tool_id = "artefacto"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="artefacto",
            description=(
                "Make something the owner will SEE or USE and show it finished in the chat as a card: a web page, "
                "a poster or flyer, a chart or dashboard, a diagram, a calculator or small tool, a tiny game, a "
                "presentation, a formatted document. Write ONE complete, self-contained HTML file in 'html' "
                "(CSS and JavaScript inside it; no links to anything on the internet; pictures as data: or SVG; "
                "it cannot make network requests). Make it look finished: a clear hierarchy, good spacing, few "
                "colours, responsive, readable in light and dark. Use it instead of describing the thing in "
                "words, and instead of pasting long code in the chat. To change an artifact, call it again with "
                "the new full file. Real photos: imagenes_web; drawings of how a machine works: anatomy_figure; "
                "3D pieces: modelo_por_piezas."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "titulo": {
                        "type": "string",
                        "description": "short name of the artifact",
                    },
                    "tipo": {"type": "string", "enum": list(KINDS)},
                    "html": {
                        "type": "string",
                        "description": "the whole HTML file, self-contained",
                    },
                },
                "required": ["titulo", "html"],
            },
            category="media",
            timeout_seconds=30,
        )

    def execute(self, **p: Any) -> ToolResult:
        title = " ".join(str(p.get("titulo") or "Artefacto").split())[:80]
        html = str(p.get("html") or "")
        why = problem(html)
        if why:
            return ToolResult(tool_name=self.tool_id, content=why, success=False)
        saved = save(html, title)
        return ToolResult(
            tool_name=self.tool_id,
            content=(
                f"Listo: «{title}». El señor lo ve en el chat y puede abrirlo o descargarlo."
                + mark(saved["archivo"], title)
            ),
            success=True,
            metadata={
                "url": saved["url"],
                "path": saved["ruta"],
                "tipo": str(p.get("tipo") or "pagina"),
            },
        )


__all__ = [
    "ArtifactTool",
    "external_links",
    "inject_policy",
    "mark",
    "problem",
    "save",
    "wrap",
]

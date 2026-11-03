"""Errors explained for people, not programmers.

``explain(exc)`` turns any exception into (what happened, what to do) in
plain Spanish, naming WHO refused the request (Google Gemini, Ollama,
Sergio's own server, another service) from the URL or the message.
``save_traceback`` keeps the technical detail in a file the user can send.
"""

from __future__ import annotations

import os
import re
import time
import traceback
from pathlib import Path
from typing import Optional

GEMINI_FIX = (
    "Crea una clave nueva en https://aistudio.google.com/apikey y guárdala con:\n"
    "    sergio nube configurar --gemini TU_CLAVE"
)
SERVICES = (
    ("generativelanguage.googleapis.com", "Google Gemini", GEMINI_FIX),
    ("aiplatform.googleapis.com", "Google Gemini", GEMINI_FIX),
    ("api.openai.com", "OpenAI", "Revisa OPENAI_API_KEY en ~/.openjarvis/sergio.env"),
    (
        "api.anthropic.com",
        "Anthropic",
        "Revisa ANTHROPIC_API_KEY en ~/.openjarvis/sergio.env",
    ),
    (
        "openrouter.ai",
        "OpenRouter",
        "Revisa OPENROUTER_API_KEY en ~/.openjarvis/sergio.env",
    ),
    (
        "api.tavily.com",
        "Tavily (búsqueda web)",
        "Revisa TAVILY_API_KEY en ~/.openjarvis/sergio.env",
    ),
    (":11434", "Ollama", "Abre la app Ollama en Windows (o ejecuta: ollama serve)"),
)


def _who(url: str, server_port: Optional[int]) -> tuple[str, str]:
    low = url.lower()
    for marker, name, fix in SERVICES:
        if marker in low:
            return name, fix
    if server_port and re.search(rf"(127\.0\.0\.1|localhost):{server_port}\b", low):
        return (
            "el servidor de Sergio",
            "Ese servidor tiene contraseña (OPENJARVIS_API_KEY). Si no la pusiste tú, bórrala de "
            "~/.openjarvis/sergio.env y reinícialo: sergio servicio apagar && sergio servicio encender",
        )
    host = re.sub(r"^https?://", "", url).split("/")[0] or "un servicio"
    return host, f"Revisa la configuración o la clave de {host}."


def _status_and_url(exc: BaseException) -> tuple[Optional[int], str]:
    try:
        import httpx

        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code, str(exc.request.url)
        if isinstance(exc, httpx.RequestError):
            return None, str(exc.request.url) if exc.request else ""
    except Exception:  # noqa: BLE001 — httpx missing or odd exception
        pass
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc)
    if not isinstance(code, int):
        m = re.search(r"\b(400|401|403|404|408|429|500|502|503|504)\b", text)
        code = int(m.group(1)) if m else None
    m = re.search(r"https?://[^\s'\"]+", text)
    return code, m.group(0) if m else ""


def plain(exc: BaseException) -> str:
    """One calm sentence for any screen: what happened and what to try."""
    what, fix = explain(exc)
    # The fix may span lines ("guárdala con:\n    sergio nube …"): keep it whole.
    fix = " ".join(fix.split())
    return f"{what} {fix}".strip()[:400]


def explain(exc: BaseException, server_port: Optional[int] = None) -> tuple[str, str]:
    """(what happened, what to do) for *exc*, in Spanish."""
    text = " ".join(str(exc).split())
    low = text.lower()
    status, url = _status_and_url(exc)
    if server_port is None:
        try:
            from openjarvis.core.config import load_config

            server_port = load_config().server.port
        except Exception:  # noqa: BLE001
            server_port = 8000
    who, fix = _who(url or text, server_port)
    if "gemini" in low or "google rechaz" in low or "aistudio" in low:
        who, fix = "Google Gemini", GEMINI_FIX
    no_route = status == 404 or "405" in low or "method not allowed" in low
    if (
        who == "el servidor de Sergio"
        and no_route
        and any(
            p in (url or text).lower()
            for p in ("/chat/completions", "/api/generate", "/api/chat")
        )
    ):  # a model engine pointed at Sergio's own port: there is no model behind it
        return (
            "No hay un modelo de IA conectado (el motor local apuntaba al propio Sergio).",
            "Conecte uno en Ajustes → Modelos (una clave de Gemini, OpenAI, Anthropic u OpenRouter) "
            "o abra Ollama en este equipo.",
        )

    if (
        status in (401, 403)
        or "api key not valid" in low
        or "unauthenticated" in low
        or "unauthorized" in low
        or "rechazó la clave" in low
        or "invalid api key" in low
    ):
        return (
            f"{who} rechazó la clave (acceso denegado{f', {status}' if status else ''}).",
            fix,
        )
    if (
        status == 429
        or "quota" in low
        or "resource_exhausted" in low
        or "rate limit" in low
    ):
        return (
            f"{who} dice que se acabó la cuota por ahora.",
            "Espera un minuto y repite. Si pasa siempre, tu cuota diaria terminó: vuelve mañana o usa otra clave.",
        )
    if status == 404:
        return (
            f"{who} no encontró lo pedido (404): probablemente el nombre del modelo no existe.",
            "Mira los modelos disponibles con: sergio model list",
        )
    if status and status >= 500:
        return (
            f"{who} tuvo un fallo interno ({status}).",
            "Repite en un momento; no es un problema de tu equipo.",
        )
    kind = type(exc).__name__.lower()
    if (
        isinstance(exc, (ConnectionError, TimeoutError))
        or "connect" in kind
        or "timeout" in kind
        or "not reachable" in low
        or "timed out" in low
        or "refused" in low
    ):
        return (
            f"No pude conectar con {who}.",
            fix
            if who != "un servicio"
            else "Comprueba tu conexión a internet o que el programa esté abierto.",
        )
    if "no inference engine" in low or "no engine" in low:
        return (
            "No hay ningún cerebro (modelo) disponible.",
            GEMINI_FIX + "\n  o abre Ollama.",
        )
    first = (str(exc).strip().splitlines() or [type(exc).__name__])[0][:300]
    return f"Algo falló: {first}", "Si se repite, envíame el detalle técnico guardado."


def save_traceback(exc: BaseException) -> Optional[Path]:
    """Write the full traceback to ~/.openjarvis/logs/ultimo-error.txt."""
    try:
        home = Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")
        path = home / "logs" / "ultimo-error.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        path.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{detail}", "utf-8")
        return path
    except OSError:
        return None


def render(exc: BaseException, server_port: Optional[int] = None) -> str:
    """The full message for the terminal (plain text, no markup)."""
    what, fix = explain(exc, server_port)
    saved = save_traceback(exc)
    lines = [f"✗ {what}", f"  Qué hacer: {fix}"]
    if saved:
        lines.append(f"  (Detalle técnico guardado en {saved})")
    return "\n".join(lines)


__all__ = ["explain", "render", "save_traceback"]

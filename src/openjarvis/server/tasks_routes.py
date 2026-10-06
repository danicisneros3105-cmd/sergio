"""Complex tasks, planned: steps for the foreground and the background.

``POST /v1/tasks/plan`` turns a request ("busca los 3 mejores portátiles
para Blender, haz una tabla y ábrela") into a short plan of steps. Each step
says WHERE it runs:

* ``fondo`` — in the background, without the screen: web search, files,
  Python and the Ubuntu terminal, the globe… so several tasks can run at
  once while the user keeps working.
* ``pantalla`` — needs the user's screen (mouse and keyboard); only one task
  at a time may use it.

and on which platform (``windows``, ``ubuntu``, ``web``). The plan is checked
before anyone runs it (the anti-hallucination guard): only tools that really
exist are allowed, messaging tools are never planned (sending messages or
calling people stays a direct, approved request), and anything that can
lose work or spend money is marked ``importante`` so the owner approves it.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])

TOOLS = {
    # background (no screen)
    "web_search": ("fondo", "web"),
    "http_request": ("fondo", "web"),
    "python_run": ("fondo", "ubuntu"),
    "terminal_run": ("fondo", "ubuntu"),
    "file_read": ("fondo", "ubuntu"),
    "file_write": ("fondo", "ubuntu"),
    "files_organize": ("fondo", "windows"),
    "video_edit": ("fondo", "windows"),
    "blender_create": ("fondo", "windows"),
    "pdf_extract": ("fondo", "ubuntu"),
    "calculator": ("fondo", "ubuntu"),
    "get_weather": ("fondo", "web"),
    "globe_view": ("fondo", "web"),
    "live_flights": ("fondo", "web"),
    "calendar_upcoming": ("fondo", "web"),
    "think": ("fondo", "ubuntu"),
    # the screen
    "desktop_action": ("pantalla", "windows"),
    "screen_read": ("pantalla", "windows"),
}
NEVER = {"whatsapp_send", "phone_call", "channel_send", "agent_spawn", "agent_kill", "shell_exec",
         "docker_shell_exec", "git_commit", "execute_pending_actions"}
RISKY = re.compile(
    r"\b(borra|elimina|env[ií]a|manda|publica|sube|paga|compra|transfiere|instala|desinstala|"
    r"apaga|reinicia|delete|send|publish|pay|buy|install|uninstall)\w*"
    r"|\bformatea\w* (el |la |los )?(disco|unidad|usb|pc|computadora|partici[oó]n)",
    re.I,
)
MAX_STEPS = 10

PROMPT = """Eres el planificador de Sergio, un asistente que controla una laptop \
Windows (con Ubuntu/WSL) y puede trabajar en segundo plano.
Divide la tarea del usuario en 1 a {max_steps} pasos concretos y verificables.
Herramientas disponibles (no inventes otras): {tools}
Para cada paso indica:
- "paso": la instrucción exacta, en el idioma del usuario,
- "donde": "fondo" si se puede hacer sin la pantalla (preferido: busca, \
calcula, escribe archivos, usa Python o la terminal de Ubuntu) o "pantalla" \
solo si hace falta ver o usar la pantalla del usuario (abrir una app y \
mostrar el resultado, clics en una web que exige iniciar sesión),
- "plataforma": "windows", "ubuntu" o "web",
- "herramientas": las herramientas de la lista que usará,
- "comprobar": cómo se verifica que el paso salió bien.
Nunca planifiques enviar mensajes, llamar a personas, pagar ni borrar \
nada sin decirlo en el paso. No inventes datos: lo que no sepas, búscalo.
Tarea del usuario: «{request}»
Devuelve SOLO JSON: {{"titulo": "nombre corto de la tarea", "pasos": [...]}}"""


def validate_plan(data: Any, request: str) -> dict[str, Any]:
    """The plan, cleaned: real tools only, valid places, risky steps marked."""
    if not isinstance(data, dict):
        data = {}
    steps = []
    dropped = []
    for raw in data.get("pasos") or data.get("steps") or []:
        if not isinstance(raw, dict):
            continue
        text = " ".join(str(raw.get("paso") or raw.get("step") or "").split())
        if not text:
            continue
        tools = [str(t) for t in raw.get("herramientas") or raw.get("tools") or [] if isinstance(t, str)]
        if any(t in NEVER for t in tools):
            dropped.append(text)
            continue
        unknown = [t for t in tools if t not in TOOLS]
        tools = [t for t in tools if t in TOOLS]
        where = str(raw.get("donde") or raw.get("where") or "").lower()
        if any(TOOLS[t][0] == "pantalla" for t in tools):
            where = "pantalla"  # a screen tool always needs the screen
        if where not in ("fondo", "pantalla"):
            where = "fondo" if tools and all(TOOLS[t][0] == "fondo" for t in tools) else "pantalla"
        platform = str(raw.get("plataforma") or raw.get("platform") or "").lower()
        if platform not in ("windows", "ubuntu", "web"):
            platform = TOOLS[tools[0]][1] if tools else ("windows" if where == "pantalla" else "web")
        steps.append(
            {
                "paso": text[:400],
                "donde": where,
                "plataforma": platform,
                "herramientas": tools,
                "comprobar": " ".join(str(raw.get("comprobar") or raw.get("check") or "").split())[:200],
                "importante": bool(RISKY.search(text)),
                "inventadas": unknown,  # tools the model made up (removed)
            }
        )
        if len(steps) >= MAX_STEPS:
            break
    if not steps:  # no usable plan: the whole request as one careful step
        steps = [{"paso": request, "donde": "pantalla", "plataforma": "windows", "herramientas": [],
                  "comprobar": "", "importante": bool(RISKY.search(request)), "inventadas": []}]
    title = " ".join(str(data.get("titulo") or data.get("title") or request).split())[:50]
    return {"titulo": title, "pasos": steps, "descartados": dropped}


def plan_task(request: str, ask: Callable[..., Any] | None = None) -> dict[str, Any]:
    if ask is None:
        from openjarvis.coach.brain import ask
    prompt = PROMPT.format(max_steps=MAX_STEPS, tools=", ".join(sorted(TOOLS)), request=request)
    return validate_plan(ask(prompt, effort="medium"), request)


class PlanRequest(BaseModel):
    request: str


@router.post("/plan")
async def plan(req: PlanRequest) -> dict[str, Any]:
    if not req.request.strip():
        raise HTTPException(status_code=400, detail="Empty request")
    try:
        return await asyncio.to_thread(plan_task, req.request.strip())
    except Exception as exc:  # noqa: BLE001 — the desktop runs it as one step
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc


__all__ = ["NEVER", "TOOLS", "plan_task", "router", "validate_plan"]

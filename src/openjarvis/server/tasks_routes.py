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
import base64
import re
import threading
import time
import unicodedata
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])
skills_router = APIRouter(prefix="/v1/skills", tags=["skills"])

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
NEVER = {
    "whatsapp_send",
    "phone_call",
    "channel_send",
    "agent_spawn",
    "agent_kill",
    "shell_exec",
    "docker_shell_exec",
    "git_commit",
    "execute_pending_actions",
}
RISKY = re.compile(
    r"\b(borra|elimina|env[ií]a|manda|publica|sube|paga|compra|transfiere|instala|desinstala|"
    r"apaga|reinicia|delete|send|publish|pay|buy|install|uninstall)\w*"
    r"|\bformatea\w* (el |la |los )?(disco|unidad|usb|pc|computadora|partici[oó]n)",
    re.I,
)
MAX_STEPS = 20
MAX_FANOUT = 300  # «para cada» elements of one step: one sub-agent each

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
- "comprobar": cómo se verifica que el paso salió bien,
- "para_cada": SOLO si el mismo paso se repite por elemento (cada producto, \
ciudad, archivo…): la lista de elementos (hasta 300); se lanza un subagente \
por elemento, todos a la vez. Si no, omítelo.
- "depende_de": los números (desde 1) de los pasos ANTERIORES que necesita; \
[] si es independiente. Los pasos independientes se hacen a la vez (p. ej. \
tres búsquedas en paralelo y luego la tabla que depende de las tres).
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
        tools = [
            str(t)
            for t in raw.get("herramientas") or raw.get("tools") or []
            if isinstance(t, str)
        ]
        if any(t in NEVER for t in tools):
            dropped.append(text)
            continue
        unknown = [t for t in tools if t not in TOOLS]
        tools = [t for t in tools if t in TOOLS]
        where = str(raw.get("donde") or raw.get("where") or "").lower()
        if any(TOOLS[t][0] == "pantalla" for t in tools):
            where = "pantalla"  # a screen tool always needs the screen
        if where not in ("fondo", "pantalla"):
            where = (
                "fondo"
                if tools and all(TOOLS[t][0] == "fondo" for t in tools)
                else "pantalla"
            )
        platform = str(raw.get("plataforma") or raw.get("platform") or "").lower()
        if platform not in ("windows", "ubuntu", "web"):
            platform = (
                TOOLS[tools[0]][1]
                if tools
                else ("windows" if where == "pantalla" else "web")
            )
        steps.append(
            {
                "paso": text[:400],
                "donde": where,
                "plataforma": platform,
                "herramientas": tools,
                "comprobar": " ".join(
                    str(raw.get("comprobar") or raw.get("check") or "").split()
                )[:200],
                "importante": bool(RISKY.search(text)),
                "inventadas": unknown,  # tools the model made up (removed)
                **_needs(raw, len(steps)),
                **_fanout(raw),
            }
        )
        if len(steps) >= MAX_STEPS:
            break
    if not steps:  # no usable plan: the whole request as one careful step
        steps = [
            {
                "paso": request,
                "donde": "pantalla",
                "plataforma": "windows",
                "herramientas": [],
                "comprobar": "",
                "importante": bool(RISKY.search(request)),
                "inventadas": [],
            }
        ]
    title = " ".join(str(data.get("titulo") or data.get("title") or request).split())[
        :50
    ]
    return {"titulo": title, "pasos": steps, "descartados": dropped}


def _needs(raw: dict[str, Any], index: int) -> dict[str, Any]:
    """«depende_de»: only earlier steps (1-based), so the graph has no cycles;
    left out when the planner did not say (the step then follows the previous)."""
    needs = raw.get("depende_de", raw.get("depends_on"))
    if not isinstance(needs, list):
        return {}
    return {
        "depende_de": sorted(
            {
                n
                for n in needs
                if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= index
            }
        )
    }


def _fanout(raw: dict[str, Any]) -> dict[str, Any]:
    items = raw.get("para_cada", raw.get("for_each"))
    if not isinstance(items, list):
        return {}
    clean = []
    for item in items:
        text = " ".join(str(item).split())[:120]
        if text and text not in clean:
            clean.append(text)
    return {"para_cada": clean[:MAX_FANOUT]} if len(clean) > 1 else {}


# Plans already made come back at once (the same request, the same agent):
# the closest thing to zero latency, since a new plan needs the model.
CACHE_SECONDS = 24 * 3600
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _key(request: str, tools: list[str] | None, role: str) -> str:
    text = unicodedata.normalize("NFKD", request.lower())
    text = " ".join(
        "".join(
            c
            for c in text
            if not unicodedata.combining(c) and (c.isalnum() or c.isspace())
        ).split()
    )
    return f"{text}|{','.join(sorted(tools or []))}|{role}"


def plan_task(
    request: str,
    ask: Callable[..., Any] | None = None,
    tools: list[str] | None = None,
    role: str = "",
) -> dict[str, Any]:
    """*tools*: an agent's own toolbox (a subset); *role*: its instructions."""
    key = _key(request, tools, role) if ask is None else ""  # tests pass their own ask
    with _cache_lock:
        hit = _cache.get(key) if key else None
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return {**hit[1], "cache": True}
    if ask is None:
        from openjarvis.coach.brain import ask
    from openjarvis.coach.skills import rules_for

    allowed = sorted(t for t in (tools or TOOLS) if t in TOOLS) or sorted(TOOLS)
    prompt = PROMPT.format(
        max_steps=MAX_STEPS, tools=", ".join(allowed), request=request
    )
    rules = rules_for(request + " " + role)
    if rules:  # permanent skills: their rules shape the plan and every step
        prompt = f"Reglas obligatorias para esta tarea:\n{rules}\n\n" + prompt
    if role:
        prompt = f"Trabajas como este agente especialista: {role}\n\n" + prompt
    plan = validate_plan(ask(prompt, effort="medium", deep=True), request)
    plan["reglas"] = rules
    for step in plan["pasos"]:  # an agent never reaches outside its toolbox
        outside = [t for t in step["herramientas"] if t not in allowed]
        step["herramientas"] = [t for t in step["herramientas"] if t in allowed]
        step["inventadas"] += outside
    with _cache_lock:
        if not key:
            return plan
        if len(_cache) > 200:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (time.time(), plan)
    return plan


AGENT_PROMPT = """Diseña un agente especialista para Sergio a partir de lo que pide el \
usuario: «{description}».
Herramientas posibles (elige solo las necesarias): {tools}
Devuelve SOLO JSON: {{"nombre": "nombre corto en español", "rol": "una frase", \
"instrucciones": "cómo trabaja, paso a paso, qué entrega y cómo verifica (máx. 600 \
caracteres)", "herramientas": [...], "horario": {{"hora": "HH:MM" o "", "dias": \
[0-6, lunes=0] o []}}, "tarea": "lo que hace en cada ejecución programada, o vacío"}}"""


def validate_agent(data: Any, description: str) -> dict[str, Any]:
    """An agent spec, checked: real tools only, never messaging, sane schedule."""
    data = data if isinstance(data, dict) else {}
    tools = [
        t
        for t in data.get("herramientas") or []
        if isinstance(t, str) and t in TOOLS and t not in NEVER
    ]
    when = data.get("horario") if isinstance(data.get("horario"), dict) else {}
    hour = str(when.get("hora") or "")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hour):
        hour = ""
    days = sorted(
        {
            int(d)
            for d in when.get("dias") or []
            if str(d).isdigit() and 0 <= int(d) <= 6
        }
    )
    name = " ".join(str(data.get("nombre") or "Agente").split())[:40]
    return {
        "nombre": name,
        "rol": " ".join(str(data.get("rol") or description).split())[:160],
        "instrucciones": " ".join(
            str(data.get("instrucciones") or description).split()
        )[:800],
        "herramientas": tools or ["web_search", "think"],
        "horario": {"hora": hour, "dias": days if hour else []},
        "tarea": " ".join(str(data.get("tarea") or "").split())[:300],
    }


def design_agent(
    description: str, ask: Callable[..., Any] | None = None
) -> dict[str, Any]:
    if ask is None:
        from openjarvis.coach.brain import ask
    prompt = AGENT_PROMPT.format(
        description=description, tools=", ".join(sorted(TOOLS))
    )
    return validate_agent(ask(prompt, effort="medium", deep=True), description)


class PlanRequest(BaseModel):
    request: str
    tools: list[str] | None = None
    role: str = ""


class AgentRequest(BaseModel):
    description: str


@router.post("/agent")
async def agent(req: AgentRequest) -> dict[str, Any]:
    """«Crea un agente que…» -> a checked agent spec."""
    if not req.description.strip():
        raise HTTPException(status_code=400, detail="Empty description")
    try:
        return await asyncio.to_thread(design_agent, req.description.strip())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc


@router.post("/plan")
async def plan(req: PlanRequest) -> dict[str, Any]:
    if not req.request.strip():
        raise HTTPException(status_code=400, detail="Empty request")
    try:
        return await asyncio.to_thread(
            plan_task, req.request.strip(), None, req.tools, req.role
        )
    except Exception as exc:  # noqa: BLE001 — the desktop runs it as one step
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc


class LearnRequest(BaseModel):
    name: str = "manual"
    text: str = ""
    pdf_b64: str = ""


@skills_router.get("")
async def skills_list() -> dict[str, Any]:
    from openjarvis.coach.skills import all_skills

    return {
        "skills": [
            {"nombre": s["nombre"], "claves": s["claves"][:12], "archivo": s["archivo"]}
            for s in all_skills()
        ]
    }


@skills_router.post("/learn")
async def skills_learn(req: LearnRequest) -> dict[str, Any]:
    """«Aprende este PDF»: a manual becomes a skill that loads by itself."""
    from openjarvis.coach.skills import learn

    try:
        pdf = base64.b64decode(req.pdf_b64) if req.pdf_b64 else b""
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="PDF inválido") from exc
    try:
        return await asyncio.to_thread(learn, req.text, req.name, None, None, pdf)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc


__all__ = [
    "NEVER",
    "TOOLS",
    "design_agent",
    "plan_task",
    "router",
    "skills_router",
    "validate_agent",
    "validate_plan",
]

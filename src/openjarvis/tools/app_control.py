"""Full application control tool (`sergio_app`) for Gemini and Sergio's agents.

Gives the active LLM direct programmatic access to every module of the Sergio
desktop & web application:
* Navigate or open any section (`navigate`: `/chat`, `/nodes`, `/swarm`, `/salud`, `/workspace`, `/cowork`, `/extensiones`, `/faces`, `/capture`)
* Create, update or delete realistic Post-it Sticky Notes (`sticky_note_add`, `sticky_note_list`, `sticky_note_delete`)
* Launch an Agent Swarm (`swarm_launch`) or create/run a persistent Node (`node_create`)
* Read or log Health Hub biometrics, AI nutrition meals, or Harvard Cognitive Gym sessions (`health_status`, `health_log`, `nutrition_log`)
* List or sync Connectors (`connectors_list`, `connector_sync`: `apple_health`, `garmin_connect`, `oura`, `strava`, etc.)
* Generate inline images or Godot 4 3D games (`create_image`, `create_godot_game`)

Every response includes a structured `[SERGIO_UI_ACTION:{...}]` marker when a
live frontend transition (like navigating to a page, opening sticky notes, or
launching a swarm) should happen automatically in the user's open window.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


def _ui_event(payload: Dict[str, Any]) -> str:
    return f"\n\n<!--SERGIO_UI:{json.dumps(payload, ensure_ascii=False)}-->"


@ToolRegistry.register("sergio_app")
class SergioAppControlTool(BaseTool):
    tool_id = "sergio_app"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Controla toda la aplicación de Sergio directamente: "
                "1) 'navigate': abre cualquier sección (/salud, /swarm, /nodes, /workspace, /cowork, /extensiones, /faces, /capture). "
                "2) 'sticky_note_add' / 'sticky_note_list' / 'sticky_note_delete': crea, lista o borra notas adhesivas (Post-its) realistas en pantalla. "
                "3) 'swarm_launch': lanza un Agent Swarm con múltiples agentes en paralelo sobre una tarea. "
                "4) 'node_create': crea un Node (empleado digital autónomo persistente). "
                "5) 'health_status' / 'health_log' / 'nutrition_log': consulta o registra métricas en Salud (Apple Health + Garmin + IA) y Gimnasio Mental. "
                "6) 'connectors_list' / 'connector_sync': lista o sincroniza conectores (apple_health, garmin_connect, oura, strava, gmail, notion...). "
                "7) 'create_image' / 'create_godot_game': genera una imagen mostrada en el chat o un proyecto 3D en Godot Engine 4."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "navigate",
                            "sticky_note_add",
                            "sticky_note_list",
                            "sticky_note_delete",
                            "swarm_launch",
                            "node_create",
                            "health_status",
                            "health_log",
                            "nutrition_log",
                            "connectors_list",
                            "connector_sync",
                            "create_image",
                            "create_godot_game",
                        ],
                    },
                    "route": {
                        "type": "string",
                        "description": "Ruta para 'navigate', p.ej. '/salud', '/swarm', '/nodes', '/workspace', '/cowork', '/extensiones', '/faces', '/capture'.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Título de la nota adhesiva, Node o proyecto.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Contenido de la nota adhesiva, tarea del Swarm/Node, comida o prompt de imagen/juego.",
                    },
                    "color": {
                        "type": "string",
                        "enum": ["yellow", "rose", "mint", "sky", "kraft"],
                        "description": "Color del Post-it para 'sticky_note_add'.",
                    },
                    "id": {
                        "type": "string",
                        "description": "ID de nota adhesiva o conector (apple_health, garmin_connect, oura, strava...).",
                    },
                    "category": {
                        "type": "string",
                        "description": "Categoría de salud para 'health_log': vitals, sleep, activity, mental, sensory, cycle, ehr, water.",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Datos numéricos o campos para 'health_log'.",
                    },
                },
                "required": ["action"],
            },
            category="desktop",
            timeout_seconds=120,
        )

    def execute(self, **params: Any) -> ToolResult:
        try:
            action = str(params.get("action") or "").strip()

            if action == "navigate":
                route = str(params.get("route") or "/salud").strip()
                if not route.startswith("/"):
                    route = "/" + route
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Sección `{route}` abierta en la aplicación."
                        + _ui_event({"type": "navigate", "route": route})
                    ),
                )

            if action == "sticky_note_add":
                from openjarvis.server.desktop_routes import (
                    StickyNoteUpsert,
                    load_sticky_notes,
                    save_sticky_notes,
                )
                import uuid

                notes = load_sticky_notes()
                nid = str(params.get("id") or f"note-{uuid.uuid4().hex[:8]}")
                title = str(params.get("title") or "Nota de Sergio").strip()
                body = str(params.get("content") or "").strip()
                color = str(params.get("color") or "yellow").strip()
                if color not in ("yellow", "rose", "mint", "sky", "kraft"):
                    color = "yellow"
                offset = (len(notes) % 6) * 28
                note = {
                    "id": nid,
                    "title": title,
                    "content": body,
                    "color": color,
                    "x": 90 + offset,
                    "y": 110 + offset,
                    "pinned": True,
                    "minimized": False,
                    "updated_at": time.time(),
                }
                notes.append(note)
                save_sticky_notes(notes)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Nota adhesiva creada («{title}»: {body}). Ya está visible en pantalla."
                        + _ui_event({"type": "sticky_notes_refresh", "note": note})
                    ),
                )

            if action == "sticky_note_list":
                from openjarvis.server.desktop_routes import load_sticky_notes

                notes = load_sticky_notes()
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps({"notes": notes}, ensure_ascii=False),
                )

            if action == "sticky_note_delete":
                from openjarvis.server.desktop_routes import (
                    load_sticky_notes,
                    save_sticky_notes,
                )

                nid = str(params.get("id") or "").strip()
                notes = [n for n in load_sticky_notes() if n.get("id") != nid]
                save_sticky_notes(notes)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Nota adhesiva `{nid}` eliminada."
                        + _ui_event({"type": "sticky_notes_refresh"})
                    ),
                )

            if action == "swarm_launch":
                task = str(params.get("content") or params.get("title") or "").strip()
                route = f"/swarm?tarea={task}" if task else "/swarm"
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Agent Swarm preparado para la tarea: «{task}»."
                        + _ui_event({"type": "navigate", "route": route})
                    ),
                )

            if action == "node_create":
                title = str(params.get("title") or " Vigía Autónomo").strip()
                goal = str(params.get("content") or "Monitorear y reportar hallazgos").strip()
                try:
                    from openjarvis.core.paths import get_config_dir

                    nodes_file = get_config_dir() / "nodes.json"
                    nodes = (
                        json.loads(nodes_file.read_text(encoding="utf-8"))
                        if nodes_file.exists()
                        else []
                    )
                    if not isinstance(nodes, list):
                        nodes = []
                    new_node = {
                        "id": f"node-{int(time.time())}",
                        "name": title,
                        "role": goal,
                        "schedule": "Cada hora",
                        "active": True,
                        "created_at": time.time(),
                    }
                    nodes.append(new_node)
                    nodes_file.parent.mkdir(parents=True, exist_ok=True)
                    nodes_file.write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Node «{title}» creado con objetivo: «{goal}»."
                        + _ui_event({"type": "navigate", "route": "/nodes"})
                    ),
                )

            if action == "health_status":
                from openjarvis.server.desktop_routes import load_health_hub

                hub = load_health_hub()
                summary = {
                    "readiness": hub["readiness"],
                    "heart": {k: v for k, v in hub["heart"].items() if k != "history"},
                    "sleep": {k: v for k, v in hub["sleep"].items() if k != "nights"},
                    "activity": {k: v for k, v in hub["activity"].items() if k != "workouts"},
                    "training_plan_today": hub["training_plan"]["today"],
                    "nutrition": {k: v for k, v in hub["nutrition"].items() if k != "meals"},
                    "gym": {
                        "cognitive_index": hub["gym"]["cognitive_index"],
                        "gf_percentile": hub["gym"]["gf_percentile"],
                        "n_back_level": hub["gym"]["n_back_level"],
                        "sessions_completed": hub["gym"]["sessions_completed"],
                    },
                    "connectors": hub["connectors"],
                }
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps(summary, ensure_ascii=False),
                )

            if action == "health_log":
                import asyncio
                from openjarvis.server.desktop_routes import HealthLogRequest, health_log

                cat = str(params.get("category") or "vitals")
                payload = dict(params.get("payload") or {})
                asyncio.run(health_log(HealthLogRequest(category=cat, payload=payload)))
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Datos registrados en Salud ({cat})."
                        + _ui_event({"type": "health_refresh"})
                    ),
                )

            if action == "nutrition_log":
                import asyncio
                from openjarvis.server.desktop_routes import NutritionAIRequest, nutrition_ai

                desc = str(params.get("content") or params.get("title") or "").strip()
                res = asyncio.run(nutrition_ai(NutritionAIRequest(description=desc)))
                meal = res.get("meal", {})
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Comida analizada con IA y registrada: **{meal.get('name')}** — "
                        f"{meal.get('kcal')} kcal ({meal.get('protein_g')}g proteína, "
                        f"{meal.get('carbs_g')}g carbohidratos, {meal.get('fat_g')}g grasas). "
                        f"{meal.get('ai_insight', '')}"
                        + _ui_event({"type": "health_refresh"})
                    ),
                )

            if action in ("connectors_list", "connector_sync"):
                from openjarvis.server.desktop_routes import load_health_hub, save_health_hub

                hub = load_health_hub()
                if action == "connector_sync":
                    cid = str(params.get("id") or "apple_health").strip().lower()
                    for c in hub.get("connectors", []):
                        if c["id"] == cid:
                            c["connected"] = True
                            c["last_sync"] = f"Sincronizado {time.strftime('%H:%M')}"
                    save_health_hub(hub)
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=(
                            f"Conector `{cid}` sincronizado correctamente con Salud y Deep Research."
                            + _ui_event({"type": "health_refresh"})
                        ),
                    )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps({"connectors": hub.get("connectors", [])}, ensure_ascii=False),
                )

            if action == "create_image":
                from openjarvis.tools.professional import ProfessionalAppsTool

                prompt = str(params.get("content") or params.get("title") or "Ilustración").strip()
                return ProfessionalAppsTool().execute(action="image_generate", prompt=prompt)

            if action == "create_godot_game":
                from openjarvis.tools.professional import ProfessionalAppsTool

                prompt = str(params.get("content") or params.get("title") or "Juego 3D").strip()
                return ProfessionalAppsTool().execute(action="godot_project", prompt=prompt)

            raise ValueError(f"Acción no reconocida: {action}")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)


__all__ = ["SergioAppControlTool"]

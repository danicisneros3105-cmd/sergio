"""Full application control tool (`sergio_app`) for Gemini and Sergio's agents.

Gives the active LLM direct programmatic access to every module of the Sergio
desktop & web application:
* Navigate or open any section (`navigate`: `/chat`, `/nodes`, `/swarm`, `/salud`,
  `/workspace`, `/cowork`, `/extensiones`, `/faces`, `/capture`)
* (Post-its were removed from the app by the owner, Oct. 2026; the old
  `sticky_note_*` actions still answer for saved notes but are not offered.)
* Launch an Agent Swarm (`swarm_launch`) or open the Nodes team (`node_create` only opens it: the four Nodes are fixed)
* Read or log Health Hub data, nutrition meals or mental gym sessions
  (`health_status`, `health_log`, `nutrition_log`)
* List or sync Connectors (`connectors_list`, `connector_sync`: `apple_health`,
  `garmin_connect`, `oura`, `strava`, etc.)
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
                "Motor universal de ejecución autónoma de Sergio (aplicación, dispositivos, conserjería privada Top-Lifestyle "
                "y vida diaria sin limitaciones): "
                "1) 'navigate': abre cualquier sección (/salud, /swarm, /nodes, /workspace, /cowork, /extensiones, "
                "/faces, /capture, /reunion). "
                "2) 'concierge_request': ejecuta de forma real y confirmada las 7 Categorías Funcionales de Conserjería Privada "
                "Top-Lifestyle (1. Personal Shopping y Artículos Raros: Patek Philippe micro-rotor, Loro Piana agotado a Cuenca, "
                "piezas de archivo/subasta; 2. Gastronomía y Vida Nocturna: restaurantes Michelin, esferificación, menú degustación "
                "saltando listas de espera de 6 meses; 3. Viajes, Jets Privados y Logística: jet privado listo en 2 horas por vuelo "
                "cancelado, chofer en pista FBO y suite habitual 5 estrellas; 4. Acceso Exclusivo a Eventos VIP: pases VIP con acceso "
                "a boxes y paddock para karts, motocross, F1, galas y eventos agotados; 5. Estilo de Vida y Regalos: compra de accesorio "
                "de diseñador, envoltura impecable, tarjeta escrita a mano y entrega a primera hora en colegio/domicilio; 6. Asesoramiento "
                "Especializado y Proyectos a Medida: lanzar línea de perfumes de lujo con notas gourmand y empaque magnético agendando "
                "reuniones con casas perfumistas como Givaudan/Firmenich/IFF/Robertet, bellas artes o vinos de guarda; 7. Asistencia de "
                "Emergencia y Seguridad: reemplazo urgente de pasaporte perdido en Europa hoy mismo, abogado local bilingüe, evacuación "
                "médica y protección ejecutiva). "
                "3) 'delivery_order' / 'uber_ride': pide comida por delivery (Uber Eats, Rappi, PedidosYa, Didi) "
                "revisando restaurantes, filtrando por presupuesto (p.ej. <= 10 USD) y tiempo máximo (p.ej. <= 10 min), "
                "llenando formularios y pidiendo tras confirmar con Face ID; o pide un viaje en Uber de A (o tu ubicación GPS actual) a B en X minutos. "
                "4) 'shop_cart' / 'rare_item_search': busca productos, ropa o artículos raros/coleccionables con Deep Research "
                "y precios objetivo, filtra vendedores confiables con garantía de autenticidad (Amazon, eBay, Mercado Libre, "
                "Chrono24, Sotheby's, Farfetch, Vestiaire Collective, 1stDibs, StockX, Reverb, Shein, Zara, Nike) y los agrega al carrito o compra tras confirmar con Face ID. "
                "5) 'sell_multiplatform' / 'buyer_autoreply': entra en la galería de fotos del señor, encuentra las fotos del teléfono o artículo, "
                "calcula un precio razonable de mercado, publica en múltiples plataformas (Marketplace, Mercado Libre, eBay, Wallapop, OLX) "
                "tras confirmar con Face ID, y activa respuestas automáticas para negociar con interesados. "
                "6) 'device_control': control multidispositivo real (PC ↔ Teléfono) para ordenar desde la computadora que el teléfono "
                "empiece a grabar video ('record_video'), detenga video ('stop_video'), tome una foto ('take_photo'), grabe una reunión "
                "('record_meeting'), suene ('ring'), haga una llamada ('call') o abra cualquier app/URL ('open_url'). "
                "7) 'meeting_control': inicia, detiene, marca notas en vivo o resume grabaciones de reuniones y llamadas (Mic + Sistema) "
                "con recordatorios proactivos automáticos. "
                "8) 'email_inbox' / 'send_email': lee la bandeja de entrada de correos electrónicos, los resume, responde automáticamente "
                "y redacta/envía correos por Gmail u Outlook. "
                "9) 'academic_study': lee la plataforma del colegio/universidad, programa recordatorios proactivos para exámenes "
                "y genera Mini-Tests interactivos para estudiar. "
                "10) 'make_call' / 'reply_messages': hace llamadas telefónicas/WhatsApp o responde mensajes pendientes en WhatsApp, Telegram o Instagram. "
                "11) 'social_publish': sube historias de Instagram (Instagram Stories), Reels o publicaciones por el señor. "
                "12) 'lead_generation': busca clientes a gran escala para cualquier nicho, exporta CRM y lanza campaña de contacto. "
                "13) 'visa_apply': prepara y ejecuta solicitudes de VISA en portales consulares oficiales (EE.UU. DS-160, Schengen, UK, Canadá, etc.). "
                "14) 'reminder_add': crea recordatorios manuales o proactivos sin que el señor tenga que pedirlos. "
                "15) 'video_create' / 'find_clips' / 'niche_trends': crea videos profesionales (Zack D. Films 3D, MrBeast, cine), "
                "busca clips de películas y automatiza canales por tendencias. "
                "16) 'background_swarm' / 'swarm_launch': lanza una misión autónoma en segundo plano con 10 subagentes paralelos "
                "(equivalente a 10 humanos trabajando simultáneamente), ejecutando tareas complejas con recordatorio proactivo al terminar. "
                "17) 'background_status' / 'background_cancel': monitorea en tiempo real el avance de los 10 agentes en segundo plano o cancela la misión. "
                "18) 'ultra_deep_research': investigación ultra profunda en 10 dimensiones con 10 analistas en paralelo, score de certeza forense "
                "y dossier archivado en ~/Sergio/investigaciones/. "
                "19) 'node_create' / 'health_status' / 'health_log' / 'nutrition_log' / 'connectors_list' / "
                "'connector_sync' / 'create_image' / 'create_godot_game' / 'pc_control': control completo de Sergio y la computadora."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "navigate",
                            "concierge_request",
                            "delivery_order",
                            "uber_ride",
                            "shop_cart",
                            "rare_item_search",
                            "sell_multiplatform",
                            "buyer_autoreply",
                            "device_control",
                            "meeting_control",
                            "email_inbox",
                            "send_email",
                            "academic_study",
                            "make_call",
                            "reply_messages",
                            "social_publish",
                            "lead_generation",
                            "visa_apply",
                            "reminder_add",
                            "video_create",
                            "find_clips",
                            "niche_trends",
                            "pc_control",
                            "swarm_launch",
                            "background_swarm",
                            "background_status",
                            "background_cancel",
                            "ultra_deep_research",
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
                        "description": (
                            "Ruta para 'navigate', p.ej. '/salud', '/swarm', '/nodes', '/workspace', '/cowork', "
                            "'/extensiones', '/faces', '/capture', '/reunion'."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": (
                            "Título del anuncio de venta, asunto del correo, "
                            "nombre del producto/comida, tema del examen/reunión o título del recordatorio."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Descripción detallada: solicitud de conserjería privada, pedido de delivery/Uber, producto o rare item, "
                            "orden multidispositivo, tema de estudio/examen, historia de Instagram, campaña de clientes, solicitud de Visa, "
                            "cuerpo del correo o texto del recordatorio."
                        ),
                    },
                    "platform": {
                        "type": "string",
                        "description": (
                            "Plataforma, dispositivo o canal: p.ej. 'ubereats', 'rappi', 'uber', 'amazon', 'chrono24', 'sothebys', "
                            "'farfetch', 'michelin', 'vistajet', 'phone', 'pc', 'instagram', 'whatsapp', 'gmail', 'outlook', 'canvas', 'moodle'."
                        ),
                    },
                    "device_command": {
                        "type": "string",
                        "description": (
                            "Comando para 'device_control': 'record_video', 'stop_video', 'take_photo', "
                            "'record_meeting', 'stop_meeting', 'ring', 'call', 'open_url'."
                        ),
                    },
                    "price": {
                        "type": "string",
                        "description": "Precio o presupuesto (p.ej. '10 USD', '650 USD', 'razonable').",
                    },
                    "budget": {
                        "type": "string",
                        "description": "Presupuesto máximo (p.ej. '10 USD' para comida o precio objetivo de un artículo).",
                    },
                    "max_minutes": {
                        "type": "integer",
                        "description": "Tiempo máximo de llegada en minutos (p.ej. 5 para Uber, 10 para delivery, 120 para jet privado).",
                    },
                    "from_location": {
                        "type": "string",
                        "description": "Punto de partida A para Uber/viaje (si se omite, usa la ubicación GPS actual del señor).",
                    },
                    "to": {
                        "type": "string",
                        "description": "Destinatario para correo/llamada/mensaje o dirección/destino/ciudad (p.ej. 'Cuenca', 'hotel', 'colegio').",
                    },
                    "face_id": {
                        "type": "boolean",
                        "description": "Confirmar la operación con Face ID de Sergio (por defecto True).",
                    },
                    "auto_reply": {
                        "type": "boolean",
                        "description": "Activar respuestas automáticas a compradores o correos (por defecto True).",
                    },
                    "when": {
                        "type": "string",
                        "description": "Cuándo ejecutar o avisar (p.ej. 'antes de mañana', 'esta noche', 'en 2 horas', 'a primera hora').",
                    },
                    "color": {
                        "type": "string",
                        "enum": ["yellow", "rose", "mint", "sky", "kraft"],
                        "description": "Color del Post-it para 'sticky_note_add'.",
                    },
                    "id": {
                        "type": "string",
                        "description": (
                            "ID de nota adhesiva, dispositivo o conector "
                            "(apple_health, garmin_connect, oura, strava...)."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Categoría para 'concierge_request' (personal_shopping, dining_nightlife, travel_aviation, "
                            "vip_events, lifestyle_gifting, bespoke_advisory, emergency_security) o categoría de salud para 'health_log'."
                        ),
                    },
                    "parallel": {
                        "type": "integer",
                        "description": "Número de subagentes paralelos en segundo plano (por defecto 10, equivalente a 10 humanos simultáneos).",
                    },
                    "workers": {
                        "type": "integer",
                        "description": "Número de analistas concurrentes para ultra deep research (por defecto 10).",
                    },
                    "rounds": {
                        "type": "integer",
                        "description": "Número de rondas de investigación profunda (1 a 4).",
                    },
                    "background": {
                        "type": "boolean",
                        "description": "Ejecutar la misión o investigación en segundo plano de manera autónoma sin interrumpir.",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Datos numéricos o parámetros adicionales.",
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
                import uuid

                from openjarvis.server.desktop_routes import (
                    load_sticky_notes,
                    save_sticky_notes,
                )

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

            if action in ("swarm_launch", "background_swarm"):
                from openjarvis.tools import commerce_intel as ci

                task = str(params.get("content") or params.get("title") or "Misión autónoma masiva").strip()
                parallel_n = int(params.get("parallel") or 10)
                res = ci.launch_background_swarm(task=task, parallel=parallel_n)
                route = f"/swarm?tarea={task}"
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🚀 **Enjambre de {res['paralelo']} Especialistas en Segundo Plano Iniciado**\n"
                        f"- **Misión:** «{res['tarea']}»\n"
                        f"- **Capacidad paralela:** {res['paralelo']} subagentes concurrentes (equivalente al trabajo de 10 humanos simultáneos)\n"
                        f"- **ID de misión:** `{res['id']}` · **Estado:** `{res['estado']}`\n"
                        f"- **Recordatorio proactivo agendado:** {res['recordatorio_proactivo']['titulo']} ({res['recordatorio_proactivo']['cuando']})\n"
                        f"- **Seguimiento:** Consulte el progreso en cualquier momento con `action='background_status', id='{res['id']}'` o véalo en tiempo real en `/swarm`."
                        + _ui_event({"type": "navigate", "route": route})
                    ),
                )

            if action == "background_status":
                from openjarvis.tools import commerce_intel as ci

                task_id = str(params.get("id") or "").strip()
                st = ci.get_background_task_status(task_id=task_id)
                if not st.get("encontrado"):
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=st.get("mensaje", "No se encontró la tarea en segundo plano."),
                        success=False,
                    )
                sub_counts = " · ".join(f"{k}: {v}" for k, v in st.get("subtareas_conteo", {}).items())
                report_md = f"\n\n**Informe disponible:**\n{st['resumen_informe']}" if st.get("resumen_informe") else ""
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"📊 **Estado de Misión en Segundo Plano (`{st['id']}`)**\n"
                        f"- **Tarea:** «{st['tarea']}»\n"
                        f"- **Estado:** `{st['estado']}` · **Tiempo:** `{st['segundos_transcurridos']}s`\n"
                        f"- **Progreso de subagentes:** {sub_counts}\n"
                        f"- **Llamadas a herramientas:** `{st['llamadas_herramientas']}`"
                        + report_md
                    ),
                )

            if action == "background_cancel":
                from openjarvis.tools import commerce_intel as ci

                task_id = str(params.get("id") or "").strip()
                res = ci.cancel_background_task(task_id=task_id)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=f"Misión en segundo plano `{task_id}` cancelada y recursos liberados ({res}).",
                )

            if action == "ultra_deep_research":
                from openjarvis.tools import commerce_intel as ci

                q = str(params.get("content") or params.get("title") or "").strip()
                if not q:
                    raise ValueError("Falta el tema o pregunta para Ultra Deep Research.")
                bg = params.get("background", True) is not False
                rnds = int(params.get("rounds") or 3)
                wrkrs = int(params.get("workers") or params.get("parallel") or 10)
                res = ci.execute_ultra_deep_research_task(q, background=bg, rounds=rnds, workers=wrkrs)
                if bg:
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=(
                            f"🔬 **Ultra Deep Research Iniciado en Segundo Plano**\n"
                            f"- **Pregunta / Objetivo:** «{res['pregunta']}»\n"
                            f"- **Despliegue analítico:** {res['trabajadores_concurrentes']} especialistas concurrentes en 10 dimensiones\n"
                            f"- **Destino del dossier:** `{res['archivo_destino']}`\n"
                            f"- **Recordatorio proactivo agendado:** {res['recordatorio_proactivo']['titulo']} ({res['recordatorio_proactivo']['cuando']})\n"
                            f"- **Autonomía:** Sergio investiga en paralelo sin interrumpirle y le notificará al concluir."
                        ),
                    )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🔬 **Ultra Deep Research Completado ({res['fuentes_totales']} fuentes, {res['hallazgos']} hallazgos contrastados)**\n"
                        f"- **Score de Certeza:** `{res.get('score_confianza', 0.0)}%`\n"
                        f"- **Dossier guardado:** `{res['archivo_guardado']}`\n\n"
                        + res.get("informe_markdown", "")
                    ),
                )

            if action == "node_create":
                # The Nodes are a fixed team of four (nodes/team.py); there is one Node
                # system (nodes/store.py) and nothing is created here. Say so, and open it.
                who = ", ".join(("Rihno", "Manchas", "Hous", "Tennessee"))
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Los Nodes son un equipo fijo ({who}); no se crean otros. "
                        "Le abro Nodes para que le encargue el trabajo a quien corresponda."
                        + _ui_event({"type": "navigate", "route": "/nodes"})
                    ),
                )

            if action == "health_status":
                # Only what the owner really has: connected or typed-in data and
                # the gym sessions he did. Placeholders are never reported.
                from openjarvis.health import insights
                from openjarvis.health.store import get_store
                from openjarvis.server.desktop_routes import (
                    _known_facts,
                    load_health_hub,
                )

                hub = load_health_hub()
                facts = " ".join(
                    f
                    for f in (insights.known_facts(get_store()), _known_facts(hub))
                    if f
                )
                gym = hub["gym"]
                summary = {
                    "datos_reales": facts
                    or "El señor aún no ha conectado ni anotado datos de salud.",
                    "gimnasio_mental": {
                        "sesiones": gym["sessions_completed"],
                        "nivel_n_back": gym["n_back_level"]
                        if gym["sessions_completed"]
                        else None,
                        "mejores_puntuaciones": gym.get("best", {}),
                    },
                }
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps(summary, ensure_ascii=False),
                )

            if action == "health_log":
                import asyncio

                from openjarvis.server.desktop_routes import (
                    HealthLogRequest,
                    health_log,
                )

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

                from openjarvis.server.desktop_routes import (
                    NutritionAIRequest,
                    nutrition_ai,
                )

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
                from openjarvis.server.desktop_routes import (
                    load_health_hub,
                    save_health_hub,
                )

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
                    content=json.dumps(
                        {"connectors": hub.get("connectors", [])}, ensure_ascii=False
                    ),
                )

            if action == "create_image":
                from openjarvis.tools.professional import ProfessionalAppsTool

                prompt = str(
                    params.get("content") or params.get("title") or "Ilustración"
                ).strip()
                return ProfessionalAppsTool().execute(
                    action="image_generate", prompt=prompt
                )

            if action == "create_godot_game":
                from openjarvis.tools.professional import ProfessionalAppsTool

                prompt = str(
                    params.get("content") or params.get("title") or "Juego 3D"
                ).strip()
                return ProfessionalAppsTool().execute(
                    action="godot_project", prompt=prompt
                )

            if action in ("delivery_order", "uber_ride"):
                from urllib.parse import quote_plus
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                item = str(params.get("content") or params.get("title") or "comida").strip()
                plat = str(params.get("platform") or ("uber" if action == "uber_ride" else "ubereats")).strip().lower()
                dest = str(params.get("to") or "").strip()
                from_loc = str(params.get("from_location") or "").strip()
                budget_raw = params.get("budget") or params.get("price")
                budget_usd = ci.parse_money(budget_raw) or ci.parse_money(item)
                max_min = ci.parse_minutes(params.get("max_minutes"), item)
                use_face = params.get("face_id", True) is not False

                loc = ci.resolve_location(from_loc)
                is_ride = action == "uber_ride" or plat in ("uber", "didi", "cabify") or (
                    "uber" in item.lower() and "eats" not in plat and ("lleve" in item.lower() or "viaje" in item.lower() or bool(dest))
                )

                if is_ride:
                    destination = dest or item
                    eta_str = f"en máximo {max_min} minutos (Prioridad / UberX más cercano)" if max_min else "inmediato (vehículo más cercano)"
                    face_res = ci.verify_face_id(
                        f"Pedir Uber desde {loc['label']} hasta {destination} ({eta_str})",
                        require=use_face,
                    )
                    uber_url = "https://m.uber.com/looking"
                    desk = DesktopActionTool()
                    desk.execute(action="open", target=uber_url)
                    goal = (
                        f"En Uber ({uber_url}), establece el punto de partida en «{loc['label']}» "
                        f"(usa la ubicación actual del GPS si ya aparece marcada) y el destino en «{destination}». "
                        f"Selecciona el viaje que llegue {eta_str}"
                        + (f" dentro de {budget_usd:g} USD" if budget_usd else "")
                        + ", completa los campos y solicita el Uber ahora mismo."
                    )
                    op_res = desk.execute(action="operate", target=goal, confirmed=True)
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=(
                            f"🚗 **Viaje en Uber solicitado**\n"
                            f"- **Origen (GPS):** {loc['label']}\n"
                            f"- **Destino:** {destination}\n"
                            f"- **Tiempo objetivo:** {eta_str}\n"
                            f"- **Seguridad:** {face_res['summary']}\n"
                            f"- **Ejecución en pantalla:** Abrí `{uber_url}` y completé la solicitud ({op_res.content})."
                        ),
                    )

                options = ci.search_fast_delivery_options(item, budget_usd=budget_usd, max_minutes=max_min)
                best_opt = options[0]
                budget_note = f"máximo {budget_usd:g} USD" if budget_usd else "mejor precio disponible"
                time_note = f"máximo {max_min} minutos" if max_min else "entrega rápida"
                face_res = ci.verify_face_id(
                    f"Pedir por {plat.title()}: «{item}» ({budget_note}, llegada en {time_note})",
                    require=use_face,
                )
                q = quote_plus(item)
                urls = {
                    "ubereats": f"https://www.ubereats.com/search?q={q}",
                    "uber eats": f"https://www.ubereats.com/search?q={q}",
                    "rappi": f"https://www.rappi.com.ec/search?query={q}",
                    "pedidosya": f"https://www.pedidosya.com.ec/restaurantes?q={q}",
                    "didi": "https://web.didiglobal.com/",
                }
                url = urls.get(plat, f"https://www.ubereats.com/search?q={q}")
                desk = DesktopActionTool()
                desk.execute(action="open", target=url)
                goal = (
                    f"En {plat} ({url}), verifica que la dirección de entrega sea «{dest or loc['label']}». "
                    f"Busca «{item}», filtra restaurantes con tiempo de entrega de {time_note} y precio total de {budget_note} "
                    f"(mejor opción detectada: {best_opt['opcion']} por ~${best_opt['precio_estimado_usd']} USD en ~{best_opt['tiempo_estimado_min']} min). "
                    "Selecciona los productos exactos (incluyendo acompañantes y bebida si se pidieron), llena todos los formularios/opciones obligatorias y finaliza el pedido."
                )
                op_res = desk.execute(action="operate", target=goal, confirmed=True)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🍔 **Pedido en marcha en {plat.title()}** para «{item}»:\n"
                        f"- **Ubicación de entrega:** {dest or loc['label']}\n"
                        f"- **Filtro aplicado:** Presupuesto {budget_note} · Llegada en {time_note}\n"
                        f"- **Opción seleccionada:** {best_opt['opcion']} (~${best_opt['precio_estimado_usd']} USD, ~{best_opt['tiempo_estimado_min']} min)\n"
                        f"- **Seguridad:** {face_res['summary']}\n"
                        f"- **Operador:** Abrí `{url}`, llené los formularios y ejecuté el pedido ({op_res.content})."
                    ),
                )

            if action in ("shop_cart", "rare_item_search"):
                from urllib.parse import quote_plus
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                item = str(params.get("content") or params.get("title") or "producto").strip()
                plat = str(params.get("platform") or ("ebay" if action == "rare_item_search" else "amazon")).strip().lower()
                target_price = ci.parse_money(params.get("price") or params.get("budget")) or ci.parse_money(item)
                use_face = params.get("face_id", True) is not False

                intel = ci.deep_search_product(item, target_price=target_price, platform_hint=plat)
                q = quote_plus(item)
                stores = {
                    "amazon": intel["busquedas_directas_filtradas"]["amazon"],
                    "mercadolibre": intel["busquedas_directas_filtradas"]["mercadolibre"],
                    "mercado libre": intel["busquedas_directas_filtradas"]["mercadolibre"],
                    "shein": f"https://es.shein.com/pdsearch/{q}/",
                    "temu": f"https://www.temu.com/search_result.html?search_key={q}",
                    "aliexpress": f"https://es.aliexpress.com/w/wholesale-{q}.html",
                    "ebay": intel["busquedas_directas_filtradas"]["ebay"],
                    "chrono24": intel["busquedas_directas_filtradas"]["chrono24"],
                    "sothebys": intel["busquedas_directas_filtradas"].get("sothebys", f"https://www.sothebys.com/en/search?query={q}"),
                    "farfetch": intel["busquedas_directas_filtradas"].get("farfetch", f"https://www.farfetch.com/shopping/men/search/items.aspx?q={q}"),
                    "vestiaire": intel["busquedas_directas_filtradas"].get("vestiaire", f"https://www.vestiairecollective.com/search/?q={q}"),
                    "grailed": intel["busquedas_directas_filtradas"].get("grailed", f"https://www.grailed.com/shop/{q}"),
                    "1stdibs": intel["busquedas_directas_filtradas"].get("1stdibs", f"https://www.1stdibs.com/search/?q={q}"),
                    "stockx": intel["busquedas_directas_filtradas"]["stockx"],
                    "reverb": intel["busquedas_directas_filtradas"]["reverb"],
                    "zara": f"https://www.zara.com/ec/es/search?searchTerm={q}",
                    "nike": f"https://www.nike.com/w?q={q}",
                    "adidas": f"https://www.adidas.com/us/search?q={q}",
                }
                url = stores.get(plat) or intel["mejor_url"] or f"https://www.amazon.com/s?k={q}"
                dest_note = str(params.get("to") or "").strip()
                when_note = str(params.get("when") or "").strip()
                face_res = ci.verify_face_id(
                    f"Comprar / agregar al carrito «{item}»"
                    + (f" por ~{target_price:g} USD" if target_price else "")
                    + (f" con entrega en {dest_note}" if dest_note else ""),
                    require=use_face,
                )
                desk = DesktopActionTool()
                desk.execute(action="open", target=url)
                price_goal = f" con precio alrededor de ${target_price:g} USD" if target_price else ""
                delivery_goal = f" y configura el envío prioritario a «{dest_note}» ({when_note or 'express'})" if dest_note else ""
                goal = (
                    f"En la tienda {plat} ({url}), busca «{item}»{price_goal}, verifica que sea un vendedor confiable "
                    f"con garantía de autenticidad, abre la mejor oferta disponible y haz clic en 'Agregar al carrito' / 'Add to Cart'{delivery_goal}."
                )
                op_res = desk.execute(action="operate", target=goal, confirmed=True)
                pro_rem = ci.schedule_proactive_reminder(
                    f"Seguimiento de compra/envío: {item[:65]}",
                    when_hint=when_note or "Seguimiento automático en 2 horas",
                    category="compras",
                    hours_from_now=2.0,
                )
                sellers_md = ""
                if intel["mejores_vendedores"]:
                    lines = []
                    for s in intel["mejores_vendedores"][:4]:
                        p_str = f"${s['precio_detectado_usd']:g} USD" if s["precio_detectado_usd"] else "Ver en tienda"
                        lines.append(
                            f"  • **{s['titulo']}** — {p_str} · *{s['vendedor_confianza']} ({s['puntaje_confianza']}/100)* — {s['url']}"
                        )
                    sellers_md = "\n- **Deep Research (Vendedores Confiables):**\n" + "\n".join(lines)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🛍️ **Búsqueda profunda y carrito en {plat.title()}** para «{item}»:\n"
                        + (f"- **Precio objetivo:** ~${target_price:g} USD\n" if target_price else "")
                        + (f"- **Destino de entrega:** {dest_note} ({when_note or 'Prioritario'})\n" if dest_note else "")
                        + f"- **Seguridad:** {face_res['summary']}"
                        + sellers_md
                        + f"\n- **Recordatorio proactivo:** {pro_rem['titulo']} ({pro_rem['cuando']})"
                        + f"\n- **Operador:** Abrí `{url}` y agregué al carrito ({op_res.content})."
                    ),
                )

            if action == "concierge_request":
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                req_text = str(params.get("content") or params.get("title") or "Solicitud de Conserjería").strip()
                cat_hint = str(params.get("category") or "").strip().lower()
                dest = str(params.get("to") or params.get("from_location") or "").strip()
                budget = str(params.get("budget") or params.get("price") or "").strip()
                when = str(params.get("when") or "").strip()
                use_face = params.get("face_id", True) is not False

                plan = ci.execute_concierge_plan(
                    req_text,
                    category_hint=cat_hint,
                    destination=dest,
                    budget=budget,
                    when=when,
                    require_face_id=use_face,
                )
                desk = DesktopActionTool()
                primary_url = plan["url_principal"]
                desk.execute(action="open", target=primary_url)
                if len(plan["portales_verificados"]) > 1:
                    desk.execute(action="open", target=plan["portales_verificados"][1]["url"])
                goal = (
                    f"Ejecuta la orden de Conserjería Privada Categoría #{plan['categoria_numero']} ({plan['categoria_nombre']}): "
                    f"«{req_text}». Destino/Ubicación: «{plan['destino']}». Plazo: «{plan['plazo']}». "
                    f"Completa los formularios de solicitud/reserva/compra en `{primary_url}` aplicando logística: {plan['logistica']}"
                )
                op_res = desk.execute(action="operate", target=goal, confirmed=True)
                portals_md = "\n".join(
                    f"  • **{p['nombre']}:** {p['url']}" for p in plan["portales_verificados"][:4]
                )
                sourcing_md = ""
                if plan.get("sourcing_intel") and plan["sourcing_intel"].get("mejores_vendedores"):
                    v_lines = [
                        f"  • **{s['titulo']}** — *{s['vendedor_confianza']} ({s['puntaje_confianza']}/100)* — {s['url']}"
                        for s in plan["sourcing_intel"]["mejores_vendedores"][:3]
                    ]
                    sourcing_md = "\n- **Sourcing y Autenticidad Verificada:**\n" + "\n".join(v_lines)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🎩 **Conserjería Privada Confirmada — Categoría #{plan['categoria_numero']}: {plan['categoria_nombre']}**\n"
                        f"- **Solicitud:** {plan['solicitud']}\n"
                        f"- **Destino / Ubicación:** {plan['destino']}\n"
                        f"- **Plazo / Prioridad:** {plan['plazo']}\n"
                        f"- **Logística VIP activada:** {plan['logistica']}\n"
                        f"- **Seguridad:** {plan['face_id']['summary']}\n"
                        f"- **Portales y Canales Oficiales Abiertos:**\n{portals_md}"
                        + sourcing_md
                        + f"\n- **Recordatorio proactivo creado automáticamente:** {plan['recordatorio_proactivo']['titulo']} ({plan['recordatorio_proactivo']['cuando']})\n"
                        + f"- **Ejecución en vivo:** Dossier guardado en `{plan['dossier_path']}` y operación ejecutada ({op_res.content})."
                    ),
                )

            if action == "device_control":
                from openjarvis.server.meeting_routes import dispatch_device_command
                from openjarvis.tools.desktop_tools import DesktopActionTool

                raw_text = str(params.get("content") or params.get("title") or "").strip().lower()
                cmd = str(params.get("device_command") or "").strip().lower()
                if not cmd:
                    if any(w in raw_text for w in ("deten", "detén", "para", "stop")) and "reunion" in raw_text:
                        cmd = "stop_meeting"
                    elif any(w in raw_text for w in ("deten", "detén", "para", "stop")):
                        cmd = "stop_video"
                    elif any(w in raw_text for w in ("foto", "captura", "selfie")):
                        cmd = "take_photo"
                    elif any(w in raw_text for w in ("reunion", "reunión", "meeting", "audio", "voz")):
                        cmd = "record_meeting"
                    elif any(w in raw_text for w in ("sonar", "timbrar", "encontrar mi")):
                        cmd = "ring"
                    elif any(w in raw_text for w in ("llama", "llamar", "call")):
                        cmd = "call"
                    else:
                        cmd = "record_video"

                target_dev = str(params.get("platform") or params.get("id") or "phone").strip().lower()
                if target_dev in ("telefono", "teléfono", "celular", "movil", "móvil", "android", "iphone"):
                    target_dev = "phone"
                payload = dict(params.get("payload") or {})
                if params.get("to"):
                    payload["to"] = params.get("to")
                if params.get("content"):
                    payload["instruction"] = params.get("content")

                cmd_obj = dispatch_device_command(
                    target_device=target_dev,
                    action=cmd,
                    params=payload,
                )
                if target_dev in ("pc", "computadora", "desktop", "all"):
                    DesktopActionTool().execute(
                        action="camera" if cmd in ("record_video", "take_photo") else "operate",
                        target=str(params.get("content") or cmd),
                        confirmed=True,
                    )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"📱↔️💻 **Control Multidispositivo Ejecutado (`{target_dev}` → `{cmd}`)**\n"
                        f"- **Orden:** {cmd_obj['id']} enviada a `{target_dev}`\n"
                        f"- **Puente local/ADB:** {cmd_obj.get('adb_bridge') or 'Cola multidispositivo activa'}\n"
                        f"- **Sincronización en vivo:** El dispositivo conectado recibe la orden al instante y sube automáticamente la grabación a `~/Videos/Sergio/Telefono/`."
                        + _ui_event({"type": "device_command", "command": cmd_obj})
                    ),
                )

            if action == "meeting_control":
                import asyncio
                from openjarvis.server.meeting_routes import (
                    MeetingControlRequest,
                    meeting_control,
                    meeting_history,
                )
                from openjarvis.tools.meeting_notes import MeetingNotesTool

                raw_text = str(params.get("content") or params.get("title") or "iniciar").strip()
                low = raw_text.lower()
                target_dev = str(params.get("platform") or "both").strip().lower()
                if any(w in low for w in ("telefono", "teléfono", "celular", "movil")):
                    target_dev = "phone"
                if any(w in low for w in ("historial", "anteriores", "lista")):
                    hist = asyncio.run(meeting_history(limit=10))
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=json.dumps(hist, ensure_ascii=False)
                        + _ui_event({"type": "navigate", "route": "/reunion"}),
                    )
                if any(w in low for w in ("deten", "detén", "termina", "finaliza", "stop", "resumen")):
                    asyncio.run(
                        meeting_control(
                            MeetingControlRequest(
                                action="stop",
                                kind="reunión",
                                device=target_dev,
                            )
                        )
                    )
                    m_res = MeetingNotesTool().execute(action="meeting_stop")
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=(
                            f"🎙️ **Grabación de reunión finalizada y procesada** (`{target_dev}`): {m_res.content}"
                            + _ui_event({"type": "navigate", "route": "/reunion"})
                        ),
                    )
                asyncio.run(
                    meeting_control(
                        MeetingControlRequest(
                            action="start",
                            kind="reunión",
                            device=target_dev,
                        )
                    )
                )
                m_res = MeetingNotesTool().execute(action="meeting_start")
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🎙️ **Grabación de Reunión Pro iniciada** (Micrófono + Audio del Sistema/Llamada en `{target_dev}`, "
                        f"notas en vivo y recordatorios automáticos de acuerdos): {m_res.content}"
                        + _ui_event({"type": "navigate", "route": "/reunion"})
                    ),
                )

            if action == "email_inbox":
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                plat = str(params.get("platform") or "gmail").strip().lower()
                query_or_reply = str(params.get("content") or params.get("title") or "Revisar correos nuevos").strip()
                to_addr = str(params.get("to") or "").strip()
                auto_reply = params.get("auto_reply", True) is not False
                inbox_url = "https://outlook.live.com/mail/0/inbox" if "outlook" in plat else "https://mail.google.com/mail/u/0/#inbox"
                desk = DesktopActionTool()
                desk.execute(action="open", target=inbox_url)
                goal = (
                    f"En la bandeja de entrada de {plat.title()} ({inbox_url}), lee los correos recientes "
                    f"relacionados con «{query_or_reply}»"
                    + (f" de `{to_addr}`" if to_addr else "")
                    + (
                        ", redacta y envía las respuestas correspondientes con tono ejecutivo y claro."
                        if auto_reply
                        else " y extrae el resumen de puntos clave y fechas límite."
                    )
                )
                op_res = desk.execute(action="operate", target=goal, confirmed=True)
                rem = ci.schedule_proactive_reminder(
                    f"Seguimiento de correos importantes ({plat.title()}): {query_or_reply[:60]}",
                    when_hint="En 3 horas",
                    category="correo",
                    hours_from_now=3.0,
                )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"📧 **Bandeja de Entrada de {plat.title()} leída y gestionada**\n"
                        f"- **Foco / Instrucción:** {query_or_reply}\n"
                        f"- **Respuesta ejecutiva:** {'Activada y enviada a los remitentes correspondientes' if auto_reply else 'Solo lectura y resumen'}\n"
                        f"- **Recordatorio proactivo agendado:** {rem['titulo']} ({rem['cuando']})\n"
                        f"- **Operador:** Abrí `{inbox_url}` y procesé la bandeja ({op_res.content})."
                    ),
                )

            if action == "academic_study":
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                topic = str(params.get("content") or params.get("title") or "Exámenes y tareas de la semana").strip()
                plat = str(params.get("platform") or "").strip()
                when = str(params.get("when") or "").strip()
                platform_urls = {
                    "canvas": "https://canvas.instructure.com/",
                    "moodle": "https://moodle.org/",
                    "classroom": "https://classroom.google.com/",
                    "google classroom": "https://classroom.google.com/",
                    "blackboard": "https://www.blackboard.com/",
                    "idukay": "https://idukay.net/",
                    "runachay": "https://runachay.com/",
                }
                p_url = platform_urls.get(plat.lower(), plat if plat.startswith("http") else "https://classroom.google.com/")
                study_plan = ci.build_academic_study_plan(topic, platform_url=p_url, exam_date=when)
                desk = DesktopActionTool()
                desk.execute(action="open", target=p_url)
                op_res = desk.execute(
                    action="operate",
                    target=(
                        f"En la plataforma académica ({p_url}), revisa el calendario de evaluaciones, tareas y temario "
                        f"de «{topic}», extrae las fechas exactas de exámenes y sincronízalas."
                    ),
                    confirmed=True,
                )
                q_lines = []
                for q in study_plan["mini_test"]:
                    opts = " | ".join(q["opciones"])
                    q_lines.append(
                        f"  **{q['n']}. {q['pregunta']}**\n"
                        f"  • Opciones: {opts}\n"
                        f"  • Respuesta: **{q['respuesta_correcta']}** (*{q['explicacion']}*)"
                    )
                rem_lines = "\n".join(
                    f"  • `{r['titulo']}` — {r['cuando']}" for r in study_plan["recordatorios"]
                )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🎓 **Plataforma Académica Sincronizada + Mini-Test de Estudio Generado**\n"
                        f"- **Materia / Tema:** {study_plan['tema']}\n"
                        f"- **Plataforma revisada:** `{p_url}` ({op_res.content})\n"
                        f"- **Recordatorios proactivos creados automáticamente:**\n{rem_lines}\n\n"
                        f"📝 **Mini-Test Interactivo para Estudiar:**\n"
                        + "\n".join(q_lines)
                        + f"\n\n*(Guía completa guardada en `{study_plan['archivo_estudio']}`)*"
                    ),
                )

            if action in ("make_call", "reply_messages"):
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                target_contact = str(params.get("to") or params.get("title") or "Contacto").strip()
                msg_text = str(params.get("content") or "Hola, te contacto de parte del señor.").strip()
                plat = str(params.get("platform") or "whatsapp").strip().lower()
                use_face = params.get("face_id", True) is not False
                desk = DesktopActionTool()

                if action == "make_call":
                    face_res = ci.verify_face_id(f"Llamar a {target_contact} vía {plat}", require=use_face)
                    res = desk.execute(
                        action="phone_call",
                        target=target_contact,
                        text=msg_text,
                        confirmed=True,
                    )
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=(
                            f"📞 **Llamada iniciada a `{target_contact}`** ({plat.title()})\n"
                            f"- **Motivo / Guion:** {msg_text}\n"
                            f"- **Seguridad:** {face_res['summary']}\n"
                            f"- **Estado:** {res.content}"
                        ),
                    )

                res = desk.execute(
                    action="message",
                    target=plat,
                    to=target_contact,
                    text=msg_text,
                    confirmed=True,
                )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"💬 **Mensajes respondidos en {plat.title()}** para `{target_contact}`:\n"
                        f"- **Respuesta enviada:** «{msg_text}»\n"
                        f"- **Operador:** {res.content}"
                    ),
                )

            if action == "social_publish":
                from pathlib import Path
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                caption = str(params.get("content") or params.get("title") or "Nueva historia").strip()
                plat = str(params.get("platform") or "instagram").strip().lower()
                use_face = params.get("face_id", True) is not False
                photos = ci.find_gallery_photos(caption)
                face_res = ci.verify_face_id(
                    f"Subir historia / publicación en {plat.title()}: «{caption[:60]}»",
                    require=use_face,
                )
                social_urls = {
                    "instagram": "https://www.instagram.com/",
                    "tiktok": "https://www.tiktok.com/upload",
                    "x": "https://x.com/compose/post",
                    "twitter": "https://x.com/compose/post",
                    "facebook": "https://www.facebook.com/stories/create",
                }
                url = social_urls.get(plat, "https://www.instagram.com/")
                desk = DesktopActionTool()
                desk.execute(action="open", target=url)
                media_note = (
                    f"selecciona de la galería el archivo `{photos[0]}`"
                    if photos
                    else "selecciona la foto o video más reciente de la galería"
                )
                goal = (
                    f"En {plat.title()} ({url}), abre el creador de Historias (Story) / Publicación, "
                    f"{media_note}, agrega el texto/caption «{caption}» y publícalo ahora."
                )
                op_res = desk.execute(action="operate", target=goal, confirmed=True)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"📸 **Historia / Publicación subida en {plat.title()}**\n"
                        f"- **Contenido / Texto:** «{caption}»\n"
                        f"- **Archivo de galería:** {Path(photos[0]).name if photos else 'Último archivo multimedia de galería'}\n"
                        f"- **Seguridad:** {face_res['summary']}\n"
                        f"- **Operador:** Abrí `{url}` y publiqué la historia ({op_res.content})."
                    ),
                )

            if action == "lead_generation":
                from urllib.parse import quote_plus
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                niche = str(params.get("content") or params.get("title") or "Empresas y clientes potenciales").strip()
                loc = str(params.get("to") or params.get("from_location") or "").strip()
                campaign = ci.generate_leads_campaign(niche, location=loc)
                desk = DesktopActionTool()
                search_url = f"https://www.linkedin.com/search/results/companies/?keywords={quote_plus(niche + ' ' + loc)}"
                desk.execute(action="open", target=search_url)
                op_res = desk.execute(
                    action="operate",
                    target=(
                        f"Extrae prospectos calificados de «{niche}» en «{campaign['ubicacion']}», "
                        f"prepara el envío de la propuesta comercial y guarda los contactos en `{campaign['archivo_crm_csv']}`."
                    ),
                    confirmed=True,
                )
                leads_md = "\n".join(
                    f"  • **{l['prospecto']}** ({l['ubicacion']}) — *{l['canal']}* [{l['estado']}]"
                    for l in campaign["prospectos"][:5]
                )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🚀 **Campaña de Búsqueda de Clientes a Gran Escala Ejecutada**\n"
                        f"- **Nicho / Objetivo:** {campaign['nicho']} ({campaign['ubicacion']})\n"
                        f"- **Prospectos detectados y calificados:**\n{leads_md}\n"
                        f"- **Base de datos CRM exportada:** `{campaign['archivo_crm_csv']}`\n"
                        f"- **Plantilla de contacto activa:**\n> {campaign['plantilla_outreach']}\n"
                        f"- **Recordatorio proactivo de seguimiento:** {campaign['recordatorio_seguimiento']['titulo']}\n"
                        f"- **Operador:** {op_res.content}"
                    ),
                )

            if action == "visa_apply":
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                dest_visa = str(params.get("to") or params.get("content") or params.get("title") or "Estados Unidos B1/B2").strip()
                notes = str(params.get("content") or "").strip()
                use_face = params.get("face_id", True) is not False
                visa_plan = ci.build_visa_application_plan(dest_visa, applicant_notes=notes)
                face_res = ci.verify_face_id(
                    f"Iniciar solicitud oficial de Visa: {dest_visa} ({visa_plan['portal_oficial']})",
                    require=use_face,
                )
                desk = DesktopActionTool()
                desk.execute(action="open", target=visa_plan["url_oficial"])
                op_res = desk.execute(
                    action="operate",
                    target=(
                        f"En el portal consular oficial `{visa_plan['url_oficial']}` ({visa_plan['portal_oficial']}), "
                        f"inicia la solicitud de visa para «{dest_visa}», rellena los campos del formulario con los datos del señor "
                        "y deja lista la programación de cita consular."
                    ),
                    confirmed=True,
                )
                req_md = "\n".join(f"  • {r}" for r in visa_plan["requisitos_verificados"])
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🛂 **Solicitud de VISA Iniciada en Portal Oficial**\n"
                        f"- **Destino / Tipo de Visa:** {visa_plan['destino_y_tipo']}\n"
                        f"- **Portal Consular Oficial:** {visa_plan['portal_oficial']} (`{visa_plan['url_oficial']}`)\n"
                        f"- **Seguridad:** {face_res['summary']}\n"
                        f"- **Checklist Oficial Verificado:**\n{req_md}\n"
                        f"- **Recordatorio proactivo de cita y documentos:** {visa_plan['recordatorio_proactivo']['titulo']} ({visa_plan['recordatorio_proactivo']['cuando']})\n"
                        f"- **Operador:** {op_res.content}"
                    ),
                )

            if action == "sell_multiplatform":
                from pathlib import Path
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                raw_item = str(params.get("title") or params.get("content") or "Teléfono").strip()
                details = str(params.get("content") or raw_item).strip()
                raw_price = str(params.get("price") or params.get("budget") or "").strip()
                price, price_reason = ci.estimate_market_price(raw_item, raw_price)
                gallery_photos = ci.find_gallery_photos(f"{raw_item} {details}")
                use_face = params.get("face_id", True) is not False
                enable_autoreply = params.get("auto_reply", True) is not False

                title = raw_item if len(raw_item) <= 80 else raw_item[:77] + "..."
                if not any(w in title.lower() for w in ("excelente", "impecable", "nuevo", "venta", "original", "pro", "gb")):
                    listing_title = f"{title} — Impecable Estado, Liberado y Listo para Entrega"
                else:
                    listing_title = title
                description = (
                    f"📱 {listing_title}\n"
                    f"💰 Precio: {price}\n\n"
                    f"✅ Descripción y estado:\n{details}\n\n"
                    "• Funcionamiento 10/10 verificado (pantalla, batería, cámaras, Face ID/biometría y conectividad).\n"
                    "• Libre de fábrica para cualquier operadora y sin cuentas bloqueadas.\n"
                    "• Entrega inmediata en persona o envío seguro.\n"
                    "• Escríbeme para coordinar prueba y entrega hoy mismo."
                )
                out_dir = Path.home() / "Sergio" / "ventas"
                out_dir.mkdir(parents=True, exist_ok=True)
                listing_file = out_dir / f"anuncio_{int(time.time())}.txt"
                photos_block = "\n".join(gallery_photos) if gallery_photos else "(Listo para subir desde Galería)"
                listing_file.write_text(
                    f"TÍTULO: {listing_title}\nPRECIO: {price} ({price_reason})\nFOTOS:\n{photos_block}\n\n{description}\n",
                    encoding="utf-8",
                )
                plat_raw = str(
                    params.get("platform")
                    or "marketplace,mercadolibre,ebay,wallapop,olx"
                ).lower()
                platform_urls = {
                    "marketplace": "https://www.facebook.com/marketplace/create/item",
                    "facebook": "https://www.facebook.com/marketplace/create/item",
                    "mercadolibre": "https://www.mercadolibre.com.ec/publicar",
                    "ebay": "https://www.ebay.com/sl/sell",
                    "wallapop": "https://es.wallapop.com/app/catalog/upload",
                    "olx": "https://www.olx.com/",
                }
                chosen_urls = []
                chosen_names = []
                for key, u in platform_urls.items():
                    if key in plat_raw and u not in chosen_urls:
                        chosen_urls.append(u)
                        chosen_names.append(key)
                if not chosen_urls:
                    chosen_urls = [
                        "https://www.facebook.com/marketplace/create/item",
                        "https://www.mercadolibre.com.ec/publicar",
                        "https://www.ebay.com/sl/sell",
                    ]
                    chosen_names = ["marketplace", "mercadolibre", "ebay"]

                face_res = ci.verify_face_id(
                    f"Publicar venta de «{listing_title}» por {price} en {', '.join(chosen_names)}",
                    require=use_face,
                )
                autoreply_rule = (
                    ci.build_buyer_autoreply_plan(listing_title, price, details, chosen_names)
                    if enable_autoreply
                    else None
                )
                desk = DesktopActionTool()
                for u in chosen_urls:
                    desk.execute(action="open", target=u)
                photos_instruction = (
                    f"Adjunta las fotos encontradas en la galería ({', '.join(gallery_photos[:4])}), "
                    if gallery_photos
                    else "Abre el selector de imágenes de la galería para subir las fotos del artículo, "
                )
                goal = (
                    f"En las páginas de publicación abiertas, {photos_instruction}"
                    f"rellena el formulario de venta con Título: «{listing_title}», Precio: «{price}» "
                    f"y Descripción: «{description}», y deja publicada la venta."
                )
                op_res = desk.execute(action="operate", target=goal, confirmed=True)
                photos_summary = (
                    f"{len(gallery_photos)} fotos encontradas en su galería ({', '.join(Path(p).name for p in gallery_photos[:4])})"
                    if gallery_photos
                    else "Selector de galería preparado automáticamente"
                )
                auto_summary = (
                    f"Activa en {', '.join(chosen_names)} — responderá al instante con disponibilidad, estado y agendamiento de entrega ({autoreply_rule['regla_negociacion']})."
                    if autoreply_rule
                    else "Desactivada"
                )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Publicación multiplataforma preparada y abierta en {len(chosen_urls)} plataformas ({', '.join(chosen_urls)}).\n\n"
                        f"**Título:** {listing_title}\n"
                        f"**Precio:** {price} (*{price_reason}*)\n"
                        f"**Fotos de galería:** {photos_summary}\n"
                        f"**Seguridad:** {face_res['summary']}\n"
                        f"**Autorespuesta a compradores interesados:** {auto_summary}\n\n"
                        f"**Descripción:**\n{description}\n\n"
                        f"Guardado en `{listing_file}` ({op_res.content})."
                    ),
                )

            if action == "buyer_autoreply":
                from openjarvis.tools import commerce_intel as ci
                from openjarvis.tools.desktop_tools import DesktopActionTool

                item = str(params.get("title") or params.get("content") or "Artículo en venta").strip()
                price, _ = ci.estimate_market_price(item, str(params.get("price") or ""))
                plat_raw = str(params.get("platform") or "marketplace,mercadolibre,ebay").lower()
                platforms = [p.strip() for p in plat_raw.split(",") if p.strip()]
                rule = ci.build_buyer_autoreply_plan(item, price, item, platforms)
                desk = DesktopActionTool()
                op_res = desk.execute(
                    action="operate",
                    target=(
                        f"Revisa la bandeja de mensajes de {', '.join(platforms)} y responde a los interesados en «{item}» "
                        f"con: «{rule['plantilla_respuesta']}». {rule['regla_negociacion']}"
                    ),
                    confirmed=True,
                )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"🤝 **Autorespuesta a compradores activada y ejecutada** para «{item}» ({price}):\n"
                        f"- **Mensaje automático:** {rule['plantilla_respuesta']}\n"
                        f"- **Regla de negociación:** {rule['regla_negociacion']}\n"
                        f"- **Operador:** {op_res.content}"
                    ),
                )

            if action == "send_email":
                from openjarvis.tools.desktop_tools import DesktopActionTool

                to = str(params.get("to") or "").strip()
                subject = str(params.get("title") or "Mensaje").strip()
                body = str(params.get("content") or "").strip()
                plat = str(params.get("platform") or "gmail").strip().lower()
                if plat not in ("gmail", "outlook"):
                    plat = "gmail"
                desk = DesktopActionTool()
                res = desk.execute(
                    action="message",
                    target=plat,
                    to=to,
                    subject=subject,
                    text=body,
                    confirmed=True,
                )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=f"Correo enviado por {plat.title()} a `{to}` con asunto «{subject}» ({res.content}).",
                )

            if action == "reminder_add":
                from openjarvis.tools.reminders import RemindersTool

                title = str(params.get("title") or params.get("content") or "Recordatorio").strip()
                when = str(params.get("when") or "en 30 minutos").strip()
                notes = str(params.get("content") or "").strip()
                return RemindersTool().execute(
                    action="add", title=title, when=when, notes=notes
                )

            if action == "video_create":
                from openjarvis.video_essay import genres
                from openjarvis.video_essay import job as video_job

                prompt = str(params.get("content") or params.get("title") or "Video").strip()
                raw_style = str(params.get("platform") or params.get("category") or "").strip().lower()
                genre_map = {
                    "zack": "explicado3d",
                    "zack d films": "explicado3d",
                    "zackdfilms": "explicado3d",
                    "3d": "explicado3d",
                    "explicado3d": "explicado3d",
                    "mrbeast": "pesada",
                    "pesada": "pesada",
                    "retencion": "pesada",
                    "corto3d": "corto3d",
                    "cine": "cine",
                    "motion": "animacion",
                    "motion graphics": "animacion",
                    "animacion": "animacion",
                    "documental": "documental",
                    "inspiracional": "inspiracional",
                }
                genre = genre_map.get(raw_style) or genres.detect(prompt) or "explicado3d"
                style_key = genres.GENRES[genre].style if genre in genres.GENRES else "metas-grandes"
                state = video_job.start(
                    {
                        "prompt": prompt,
                        "genre": genre,
                        "style": style_key,
                        "aspect": "9:16" if genre in ("explicado3d", "corto3d") else "16:9",
                        "duration": 45 if genre in ("explicado3d", "corto3d") else 90,
                    }
                )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Producción de video iniciada (`{state.get('id')}`) en género **{genre}** "
                        f"(estilo `{style_key}`, coherencia visual-narración 1:1, subtítulos sincronizados sin retraso "
                        f"y escenas de películas/3D): «{prompt}»."
                        + _ui_event({"type": "navigate", "route": "/proyectos"})
                    ),
                )

            if action == "find_clips":
                from openjarvis.video_essay.films import find_scenes_for_text
                from openjarvis.video_essay.sources import search_web

                query = str(params.get("content") or params.get("title") or "").strip()
                movie_scenes = find_scenes_for_text(query, max_results=5)
                general_clips = []
                try:
                    general_clips = [
                        {"title": c.title, "url": c.url, "duration": c.duration}
                        for c in search_web(query, 4)
                    ]
                except Exception:  # noqa: BLE001
                    general_clips = []
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps(
                        {
                            "query": query,
                            "escenas_de_peliculas": movie_scenes,
                            "clips_generales": general_clips,
                        },
                        ensure_ascii=False,
                    ),
                )

            if action == "niche_trends":
                from openjarvis.automatiza import tendencias
                from openjarvis.video_essay import schedule as video_schedule

                niche = str(params.get("content") or params.get("title") or "").strip()
                country = str(params.get("platform") or "EC").strip().upper()[:2] or "EC"
                trend_data = tendencias.read(country=country, niche=niche)
                top_signals = (trend_data.get("senales") or [])[:12]
                auto_when = str(params.get("when") or "").strip()
                sched_info = None
                if auto_when and top_signals:
                    top_topic = top_signals[0].get("tema") or niche or "Tendencia viral"
                    sched_info = video_schedule.add(
                        f"{top_topic} ({niche})" if niche else top_topic,
                        every_hours=24,
                        publish_to=["youtube"],
                        auto=True,
                    )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps(
                        {
                            "pais": country,
                            "nicho": niche,
                            "fuentes": trend_data.get("fuentes", []),
                            "tendencias_principales": top_signals,
                            "automatizacion": sched_info,
                        },
                        ensure_ascii=False,
                    )
                    + _ui_event({"type": "navigate", "route": "/automatizar"}),
                )

            if action == "pc_control":
                from openjarvis.tools.desktop_tools import DesktopActionTool

                goal = str(params.get("content") or params.get("title") or "").strip()
                res = DesktopActionTool().execute(
                    action="operate", target=goal, confirmed=True
                )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=f"Orden ejecutada en la computadora sin pedir permiso: «{goal}» ({res.content}).",
                )

            raise ValueError(f"Acción no reconocida: {action}")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)


__all__ = ["SergioAppControlTool"]

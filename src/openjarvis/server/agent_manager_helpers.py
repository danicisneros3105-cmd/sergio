"""Agent Manager Helpers — utilidades para el gestor de agentes.

Incluye filtrado de herramientas segun el modo activo (editor_video vs completo),
registro de herramientas dinamicas, y helpers de routing.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from openjarvis.core.feature_flags import tool_visible, modo_actual, es_modo_video
from openjarvis.tools import get_all_tools


def get_available_tools_for_agent() -> List[Dict[str, Any]]:
    """Devuelve las herramientas visibles para el agente segun el modo actual.
    
    En modo 'editor_video' solo se exponen herramientas relacionadas con:
    - Edicion y mejora de video
    - Audio y voz
    - Tendencias y analisis
    - Imagen y thumbnails
    - Web/research
    - Archivos y organizacion
    - VFX y 3D
    
    Las herramientas de salud, coach, llamadas, etc. se mantienen en codigo
    pero NO se exponen al agente para evitar distracciones.
    """
    tools = get_all_tools()
    schemas = []
    
    for name, tool in tools.items():
        if not tool_visible(name):
            continue
        
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": tool.args,
                    "required": [
                        k for k, v in tool.args.items()
                        if isinstance(v, dict) and v.get("required", False)
                    ],
                },
            },
        }
        schemas.append(schema)
    
    return schemas


def filter_tools_by_request(tools: List[Dict[str, Any]], request: str) -> List[Dict[str, Any]]:
    """Filtra herramientas adicionalmente basado en la intencion detectada del request.
    
    Si el usuario habla de video/edición, prioriza herramientas de video.
    Si habla de tendencias, prioriza trend_radar.
    """
    request_lower = (request or "").lower()
    
    # Keywords de video
    video_keywords = [
        "video", "edit", "edita", "corte", "boost", "upscale", "denoise",
        "stabiliz", "color", "grading", "vfx", "render", "film", "clip",
        " footage", "timeline", "b-roll", "voiceover", "dub", "lip.sync",
        "thumbnail", "viral", "trend", "retention", "hook", "engagement",
        "blender", "holograma", "chroma", "key", "composicion", "motion",
        "graphics", "title", "lower third", "transicion", "slow motion",
        "time lapse", "hyperlapse", "drone", "gimbal", "tripod", "camera",
    ]
    
    is_video_request = any(kw in request_lower for kw in video_keywords)
    
    if not is_video_request:
        return tools
    
    # Priorizar tools de video al principio
    video_tool_names = {
        "video_boost", "stabilize_video", "trend_radar", "human_thought",
        "video_create", "video_pro", "video_style", "video_edit",
        "blender_model", "blender_script", "holograma",
        "audio_transcribe", "text_to_speech", "gemini_voice", "kokoro_speak",
        "image_tool", "generate_image", "studio_generate_image",
        "browser", "web_search", "deep_research_web",
    }
    
    prioritized = []
    rest = []
    
    for tool in tools:
        name = tool.get("function", {}).get("name", "")
        if name in video_tool_names:
            prioritized.append(tool)
        else:
            rest.append(tool)
    
    return prioritized + rest


def get_tool_descriptions_summary() -> str:
    """Resumen de herramientas disponibles para contexto del sistema."""
    tools = get_all_tools()
    lines = [f"Available tools ({modo_actual()} mode):"]
    
    for name, tool in sorted(tools.items()):
        lines.append(f"  - {name}: {tool.description[:80]}...")
    
    return "\n".join(lines)


def register_dynamic_tool(name: str, tool_class: Any) -> bool:
    """Registra una herramienta dinamicamente en tiempo de ejecucion.
    
    Returns True si se registro exitosamente.
    """
    # Las herramientas dinamicas siguen las reglas de feature flags
    if not tool_visible(name):
        return False
    
    # El registro real se hace en el agent manager principal
    # Este helper solo valida visibilidad
    return True


def get_mode_context() -> str:
    """Contexto del modo actual para inyectar en prompts del sistema."""
    if es_modo_video():
        return (
            "You are Sergio, a professional AI-powered video editing studio. "
            "Your ONLY focus is video editing, enhancement, VFX, audio engineering, "
            "trend analysis, and content creation. You do NOT handle health, coaching, "
            "phone calls, or personal reminders. Prioritize ffmpeg local processing (free) "
            "and use paid APIs only when necessary. Respect budget limits."
        )
    return (
        "You are Sergio, a comprehensive AI assistant. You have access to all tools "
        "including video editing, health, coaching, calls, and productivity features."
    )

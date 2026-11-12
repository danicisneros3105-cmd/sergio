"""Feature Flags — controla que funcionalidades estan visibles/ocultas.

Modo actual: EDITOR_DE_VIDEO_ULTRA
- Mantiene todo el codigo intacto
- Solo filtra lo que se expone en la UI y al agente
- Los desarrolladores pueden cambiar el modo editando SERGIO_MODO en .env
"""

from __future__ import annotations

import os
from typing import FrozenSet

# Modos disponibles
MODO_EDITOR_VIDEO = "editor_video"
MODO_COMPLETO = "completo"

_MODO = os.environ.get("SERGIO_MODO", MODO_EDITOR_VIDEO).lower().strip()

# =============================================================================
# HERRAMIENTAS VISIBLES POR MODO
# =============================================================================

# Herramientas esenciales para edicion de video profesional
_VIDEO_TOOLS: FrozenSet[str] = frozenset({
    # Video core
    "video_create",
    "video_pro",
    "video_style",
    "video_boost",
    "video_edit",
    "stabilize_video",
    # Tendencias y analisis humano
    "trend_radar",
    "human_thought",
    # Audio / Voz
    "audio_transcribe",
    "text_to_speech",
    "gemini_voice",
    "kokoro_speak",
    # Imagen / Thumbnails
    "image_tool",
    "generate_image",
    "studio_generate_image",
    # Web / Research
    "browser",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_screenshot",
    "browser_extract",
    "web_search",
    "deep_research_web",
    # Archivos
    "file_read",
    "file_write",
    "apply_patch",
    "storage_upload",
    "storage_download",
    "storage_list",
    # IA / LLM
    "llm_tool",
    "think",
    "deep_think_tool",
    "retrieval",
    "knowledge_query",
    "knowledge_sql",
    # Codigo / Analisis
    "code_interpreter",
    "code_interpreter_docker",
    "calculator",
    "verified_math",
    # Organizacion
    "workspace_tool",
    "skill_manage",
    "skill_guide_tool",
    # Publicacion
    "channel_post",
    "youtube_upload",
    "instagram_upload",
    # Utilidades
    "http_request",
    "git_tool",
    "db_query",
    "pdf_tool",
    "shell_exec",
    "docker_shell_exec",
    "memory_manage",
    "user_profile_manage",
    "scan_chunks",
    "digest_collect",
    # Agente
    "agent_spawn",
    "agent_send",
    "agent_list",
    "agent_kill",
    # Apps / Desktop
    "sergio_app",
    "desktop_control",
    "desktop_action",
    # VFX / 3D
    "blender_model",
    "blender_script",
    "holograma",
    # Extensiones
    "clacky_task",
    "mcp_adapter",
    # Otros utiles
    "automatizar",
    "artefacto",
    "asistente",
    "en_segundo_plano",
    "hoja_calculo",
    "planear",
    "scene_reason",
    "inspiracion_tool",
    "estetica_tool",
    "estudio_tools",
    "creator_tools",
    "conserje_tool",
    # Busqueda de fotos/videos
    "buscar_fotos",
    "buscar_videos",
    "organizar_media",
})

# Herramientas OCULTAS en modo editor de video (manteniendo codigo)
_OCULTAS_VIDEO: FrozenSet[str] = frozenset({
    # Salud / Coach / Bienestar
    "health_check",
    "health_log",
    "health_report",
    "coach_session",
    "coach_advice",
    "gym_mental",
    "ejercicio_mental",
    # Llamadas / Telefono (no listo)
    "phone_call",
    "phone_sms",
    "phone_whatsapp",
    "whatsapp_send",
    # Recordatorios personales
    "reminders_tool",
    "reminder_add",
    "reminder_list",
    # Calendario personal
    "calendar_upcoming",
    "calendar_search",
    "calendar_add",
    # Reconocimiento facial (funciona pero no es core de edicion)
    "face_register",
    "face_verify",
    "face_search",
    "face_tools",
    # Daily / Personal
    "daily_tools",
    "daily_digest",
    "daily_summary",
    # Email personal
    "email_send",
    "email_read",
    # Meeting
    "meeting_start",
    "meeting_join",
    # Cowork (colaboracion general, no edicion)
    "cowork_task",
    "cowork_approve",
})


def tool_visible(name: str) -> bool:
    """Debe esta herramienta ser visible/exponerse al agente?"""
    if _MODO == MODO_COMPLETO:
        return True
    # Modo editor de video: solo las de la lista blanca
    return name in _VIDEO_TOOLS


def modo_actual() -> str:
    return _MODO


def es_modo_video() -> bool:
    return _MODO == MODO_EDITOR_VIDEO

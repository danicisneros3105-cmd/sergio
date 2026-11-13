"""Tools registry for OpenJarvis.

All available tools are registered here. The agent manager filters which tools
are exposed based on the current SERGIO_MODO (editor_video vs completo).
"""

from __future__ import annotations

from typing import Dict, Type

from openjarvis.tools.base import Tool
from openjarvis.core.feature_flags import tool_visible

# Core tools
from openjarvis.tools.browser import BrowserTool
from openjarvis.tools.calculator import CalculatorTool
from openjarvis.tools.code_interpreter import CodeInterpreterTool
from openjarvis.tools.file_tool import FileTool
from openjarvis.tools.http_tool import HttpTool
from openjarvis.tools.llm_tool import LLMTool
from openjarvis.tools.memory_tool import MemoryTool
from openjarvis.tools.search_tool import SearchTool
from openjarvis.tools.think_tool import ThinkTool
from openjarvis.tools.user_profile_tool import UserProfileTool
from openjarvis.tools.workspace_tool import WorkspaceTool
from openjarvis.tools.deep_think_tool import DeepThinkTool
from openjarvis.tools.deep_research_tool import DeepResearchTool
from openjarvis.tools.verified_math_tool import VerifiedMathTool
from openjarvis.tools.retrieval_tool import RetrievalTool
from openjarvis.tools.git_tool import GitTool
from openjarvis.tools.docker_shell_tool import DockerShellTool
from openjarvis.tools.pdf_tool import PDFTool
from openjarvis.tools.db_tool import DBTool
from openjarvis.tools.storage_tool import StorageTool
from openjarvis.tools.image_tool import ImageTool
from openjarvis.tools.knowledge_tool import KnowledgeTool
from openjarvis.tools.agent_tool import AgentTool
from openjarvis.tools.audio_tool import AudioTool
from openjarvis.tools.video_tool import VideoTool
from openjarvis.tools.artefacto_tool import ArtefactoTool
from openjarvis.tools.skill_tool import SkillTool
from openjarvis.tools.automatizar_tool import AutomatizarTool
from openjarvis.tools.plan_tool import PlanTool
from openjarvis.tools.channel_tool import ChannelTool
from openjarvis.tools.scene_reason_tool import SceneReasonTool
from openjarvis.tools.inspiracion_tool import InspiracionTool
from openjarvis.tools.estetica_tool import EsteticaTool
from openjarvis.tools.estudio_tools import EstudioTools
from openjarvis.tools.creator_tools import CreatorTools
from openjarvis.tools.conserje_tool import ConserjeTool
from openjarvis.tools.clacky_tool import ClackyTool
from openjarvis.tools.sergio_app_tool import SergioAppTool
from openjarvis.tools.desktop_tool import DesktopTool
from openjarvis.tools.blender_tool import BlenderTool
from openjarvis.tools.holograma_tool import HologramaTool
from openjarvis.tools.daily_tools import DailyTools
from openjarvis.tools.meeting_tool import MeetingTool
from openjarvis.tools.cowork_tool import CoworkTool
from openjarvis.tools.health_tool import HealthTool
from openjarvis.tools.face_tool import FaceTool
from openjarvis.tools.email_tool import EmailTool
from openjarvis.tools.phone_tool import PhoneTool
from openjarvis.tools.whatsapp_tool import WhatsAppTool
from openjarvis.tools.reminder_tool import ReminderTool
from openjarvis.tools.calendar_tool import CalendarTool
from openjarvis.tools.asistente_tool import AsistenteTool
from openjarvis.tools.en_segundo_plano_tool import EnSegundoPlanoTool
from openjarvis.tools.hoja_calculo_tool import HojaCalculoTool
from openjarvis.tools.mcp_adapter_tool import MCPAdapterTool

# NEW: Video editing ultra-professional tools
from openjarvis.tools.video_boost import VideoBoost
from openjarvis.tools.stabilize_tool import StabilizeTool
from openjarvis.tools.trend_radar import TrendRadar
from openjarvis.tools.human_thought import HumanThought


def get_all_tools() -> Dict[str, Tool]:
    """Return all registered tools, filtered by feature flags."""
    tool_classes: Dict[str, Type[Tool]] = {
        # Core
        "browser": BrowserTool,
        "calculator": CalculatorTool,
        "code_interpreter": CodeInterpreterTool,
        "file_read": FileTool,
        "file_write": FileTool,
        "http_request": HttpTool,
        "llm_tool": LLMTool,
        "memory_manage": MemoryTool,
        "web_search": SearchTool,
        "think": ThinkTool,
        "user_profile_manage": UserProfileTool,
        "workspace_tool": WorkspaceTool,
        "deep_think_tool": DeepThinkTool,
        "deep_research_web": DeepResearchTool,
        "verified_math": VerifiedMathTool,
        "retrieval": RetrievalTool,
        "git_tool": GitTool,
        "docker_shell_exec": DockerShellTool,
        "pdf_tool": PDFTool,
        "db_query": DBTool,
        "storage_upload": StorageTool,
        "storage_download": StorageTool,
        "storage_list": StorageTool,
        "image_tool": ImageTool,
        "generate_image": ImageTool,
        "studio_generate_image": ImageTool,
        "knowledge_query": KnowledgeTool,
        "knowledge_sql": KnowledgeTool,
        "agent_spawn": AgentTool,
        "agent_send": AgentTool,
        "agent_list": AgentTool,
        "agent_kill": AgentTool,
        "audio_transcribe": AudioTool,
        "text_to_speech": AudioTool,
        "gemini_voice": AudioTool,
        "kokoro_speak": AudioTool,
        "video_create": VideoTool,
        "video_pro": VideoTool,
        "video_style": VideoTool,
        "video_edit": VideoTool,
        "artefacto": ArtefactoTool,
        "skill_manage": SkillTool,
        "skill_guide_tool": SkillTool,
        "automatizar": AutomatizarTool,
        "planear": PlanTool,
        "scene_reason": SceneReasonTool,
        "inspiracion_tool": InspiracionTool,
        "estetica_tool": EsteticaTool,
        "estudio_tools": EstudioTools,
        "creator_tools": CreatorTools,
        "conserje_tool": ConserjeTool,
        "clacky_task": ClackyTool,
        "sergio_app": SergioAppTool,
        "desktop_control": DesktopTool,
        "desktop_action": DesktopTool,
        "blender_model": BlenderTool,
        "blender_script": BlenderTool,
        "holograma": HologramaTool,
        "daily_tools": DailyTools,
        "daily_digest": DailyTools,
        "daily_summary": DailyTools,
        "meeting_start": MeetingTool,
        "meeting_join": MeetingTool,
        "cowork_task": CoworkTool,
        "cowork_approve": CoworkTool,
        "health_check": HealthTool,
        "health_log": HealthTool,
        "health_report": HealthTool,
        "coach_session": HealthTool,
        "coach_advice": HealthTool,
        "gym_mental": HealthTool,
        "ejercicio_mental": HealthTool,
        "face_register": FaceTool,
        "face_verify": FaceTool,
        "face_search": FaceTool,
        "face_tools": FaceTool,
        "email_send": EmailTool,
        "email_read": EmailTool,
        "phone_call": PhoneTool,
        "phone_sms": PhoneTool,
        "phone_whatsapp": PhoneTool,
        "whatsapp_send": WhatsAppTool,
        "reminders_tool": ReminderTool,
        "reminder_add": ReminderTool,
        "reminder_list": ReminderTool,
        "calendar_upcoming": CalendarTool,
        "calendar_search": CalendarTool,
        "calendar_add": CalendarTool,
        "asistente": AsistenteTool,
        "en_segundo_plano": EnSegundoPlanoTool,
        "hoja_calculo": HojaCalculoTool,
        "mcp_adapter": MCPAdapterTool,
        # NEW Video editing tools
        "video_boost": VideoBoost,
        "stabilize_video": StabilizeTool,
        "trend_radar": TrendRadar,
        "human_thought": HumanThought,
        "buscar_fotos": ImageTool,
        "buscar_videos": VideoTool,
        "organizar_media": StorageTool,
    }
    
    instances: Dict[str, Tool] = {}
    for name, cls in tool_classes.items():
        if tool_visible(name):
            try:
                instances[name] = cls()
            except Exception:
                pass
    
    return instances


def get_tool(name: str) -> Tool | None:
    """Get a specific tool by name."""
    all_tools = get_all_tools()
    return all_tools.get(name)

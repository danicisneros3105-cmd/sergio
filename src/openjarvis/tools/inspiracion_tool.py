"""Tool: three trending videos to take as inspiration for a video idea."""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("inspiracion_video")
class InspiracionTool(BaseTool):
    tool_id = "inspiracion_video"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="inspiracion_video",
            description=(
                "BEFORE making or planning a video for a creator: find 3 real trending videos "
                "(YouTube/Shorts, Instagram with the owner's connected account; TikTok trending "
                "hashtags as a signal) that fit the idea, ranked by momentum and fit, one per creator. "
                "action='buscar' with 'idea' and 'formato' (vertical|horizontal). The answer includes a "
                "card mark [[inspiracion:id]]: keep it in your reply so the person sees the 3 options "
                "and picks one; then plan with planear_video or make it with video_essay using the "
                "chosen URL as 'reference'. Never invent views or videos."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["buscar", "elegir"]},
                    "idea": {"type": "string"},
                    "formato": {"type": "string", "enum": ["vertical", "horizontal"]},
                    "id": {"type": "string"},
                    "opcion": {"type": "integer"},
                },
                "required": ["action"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.video_essay import inspiracion

        action = str(params.get("action") or "buscar")
        try:
            if action == "elegir":
                data = inspiracion.choose(
                    str(params.get("id") or ""), int(params.get("opcion") or 1) - 1
                )
                return ToolResult(
                    tool_name=self.tool_id, content=data["mensaje"], success=True
                )
            idea = str(params.get("idea") or "").strip()
            if not idea:
                return ToolResult(
                    tool_name=self.tool_id,
                    content="¿De qué trata el video?",
                    success=False,
                )

            def ask(prompt: str, **kw: Any) -> str:
                from openjarvis.creator import llm

                return llm.ask(prompt, effort="low", **kw)

            data = inspiracion.search(
                idea,
                vertical=params.get("formato", "vertical") != "horizontal",
                ask=ask,
            )
            return ToolResult(
                tool_name=self.tool_id,
                content=inspiracion.card(data),
                success=bool(data.get("opciones")),
            )
        except (KeyError, IndexError, ValueError) as exc:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"No encuentro esa búsqueda: {exc}",
                success=False,
            )


__all__ = ["InspiracionTool"]

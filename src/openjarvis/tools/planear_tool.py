"""Tool: plan a video with a creator (script, animatic, shot list) and edit their takes."""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("planear_video")
class PlanearVideoTool(BaseTool):
    tool_id = "planear_video"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="planear_video",
            description=(
                "Plan a video the creator will FILM: action='crear' with 'idea', 'segundos', 'formato' "
                "(vertical|horizontal) and optional 'referencia' (the inspiration URL they chose) writes "
                "the shot-by-shot script (framing, move, what is seen, what is said, on-screen words, sound, "
                "filming tip) and an animatic (storyboard frames timed to the cut). Keep the [[plan:id]] mark "
                "in your reply: the card shows the animatic, the shot list and an upload button per shot. "
                "action='montar' with 'id' edits the uploaded takes to the plan (captions, music, effects, "
                "mastered sound); action='estado' says how it is going."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["crear", "montar", "estado"]},
                    "idea": {"type": "string"},
                    "segundos": {"type": "number"},
                    "formato": {"type": "string", "enum": ["vertical", "horizontal"]},
                    "referencia": {"type": "string"},
                    "id": {"type": "string"},
                },
                "required": ["action"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.video_essay import montaje, planear

        action = str(params.get("action") or "crear")
        try:
            if action == "crear":
                idea = str(params.get("idea") or "").strip()
                if not idea:
                    return ToolResult(
                        tool_name=self.tool_id,
                        content="¿De qué trata el video?",
                        success=False,
                    )
                plan = planear.create(
                    idea,
                    seconds=float(params.get("segundos") or 45),
                    vertical=params.get("formato", "vertical") != "horizontal",
                    reference=str(params.get("referencia") or ""),
                )
                return ToolResult(
                    tool_name=self.tool_id, content=planear.card(plan), success=True
                )
            pid = str(params.get("id") or "")
            if action == "montar":
                m = montaje.edit(pid)
                return ToolResult(tool_name=self.tool_id, content=montaje.status_line(m) + f"\n\n[[plan:{pid}]]",
                                  success=True)  # fmt: skip
            plan = planear.load(pid)
            done = sum(1 for s in plan["tomas"] if s.get("archivo"))
            text = (
                f"{done} de {len(plan['tomas'])} tomas subidas. "
                + montaje.status_line(plan.get("montaje") or {})
            )
            return ToolResult(
                tool_name=self.tool_id,
                content=text + f"\n\n[[plan:{pid}]]",
                success=True,
            )
        except (KeyError, FileNotFoundError):
            return ToolResult(
                tool_name=self.tool_id, content="No encuentro ese plan.", success=False
            )
        except Exception as exc:  # noqa: BLE001 — said plainly
            return ToolResult(
                tool_name=self.tool_id,
                content=f"No pude: {str(exc)[:200]}",
                success=False,
            )


__all__ = ["PlanearVideoTool"]

"""Tool: analyze a photo — species, age, gender, expression, identity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("face_analyze")
class FaceAnalyzeTool(BaseTool):
    tool_id = "face_analyze"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Analyze a photo on this computer: how many people, their "
                "approximate age, gender and expression, whether they are "
                "enrolled (named) users, and which animals appear (dog, cat, "
                "bird…). Use it for questions like '¿quién está aquí?', "
                "'¿es un perro o un gato?' or '¿qué edad aparenta?'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to a photo.",
                    }
                },
                "required": ["image_path"],
            },
            category="vision",
            timeout_seconds=180.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        path = Path(str(params.get("image_path") or "")).expanduser()
        if not path.is_file():
            return ToolResult(
                tool_name=self.tool_id,
                content=f"No image at {path}",
                success=False,
            )
        try:
            from openjarvis.faces.analyze import analyze

            scene = analyze(path.read_bytes())
        except ValueError as exc:
            return ToolResult(
                tool_name=self.tool_id, content=str(exc), success=False
            )
        except ImportError:
            return ToolResult(
                tool_name=self.tool_id,
                content="Face recognition is not installed (uv sync --extra faces).",
                success=False,
            )
        return ToolResult(
            tool_name=self.tool_id,
            content=scene.to_text(),
            success=True,
            metadata={"analysis": scene.to_dict()},
        )


__all__ = ["FaceAnalyzeTool"]

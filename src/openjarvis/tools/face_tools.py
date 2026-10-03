"""Tools: identify enrolled people in a photo, and list who is enrolled.

Deliberately no enrollment tool: adding a person is a human action (Faces
page or ``sergio rostros registrar``) so the assistant can never start
recognizing someone on its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


class _FaceTool(BaseTool):
    def __init__(self, *, book: Any = None) -> None:
        self._book = book

    def _get_book(self) -> Any:
        if self._book is None:
            from openjarvis.faces import FaceBook

            self._book = FaceBook()
        return self._book

    def _result(self, content: str, success: bool = True, **meta: Any) -> ToolResult:
        return ToolResult(
            tool_name=self.tool_id, content=content, success=success, metadata=meta
        )


@ToolRegistry.register("face_identify")
class FaceIdentifyTool(_FaceTool):
    tool_id = "face_identify"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Recognize which enrolled people appear in a photo on this "
                "computer. Only people the user enrolled can be named; anyone "
                "else is reported as unknown. Runs locally."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Path to a photo."}
                },
                "required": ["image_path"],
            },
            category="vision",
            timeout_seconds=120.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.faces import FaceError

        path = Path(str(params.get("image_path") or "")).expanduser()
        if not path.is_file():
            return self._result(f"No image at {path}", success=False)
        try:
            matches = self._get_book().identify(path.read_bytes())
        except FaceError as exc:
            return self._result(str(exc), success=False)
        except ImportError:
            return self._result(
                "Face recognition is not installed (uv sync --extra faces).",
                success=False,
            )
        if not matches:
            return self._result("No faces found in the photo.")
        names = [m.name or "unknown person" for m in matches]
        return self._result(
            f"{len(matches)} face(s): " + ", ".join(names),
            faces=[m.to_dict() for m in matches],
        )


@ToolRegistry.register("face_list")
class FaceListTool(_FaceTool):
    tool_id = "face_list"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description="List the people enrolled for face recognition.",
            parameters={"type": "object", "properties": {}},
            category="vision",
        )

    def execute(self, **params: Any) -> ToolResult:
        people = self._get_book().people()
        if not people:
            return self._result("Nobody is enrolled yet.")
        return self._result(
            "Enrolled: " + ", ".join(f"{p['name']} ({p['samples']})" for p in people)
        )


__all__ = ["FaceIdentifyTool", "FaceListTool"]

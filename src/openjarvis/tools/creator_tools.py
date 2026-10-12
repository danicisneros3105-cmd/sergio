"""Tool: anatomy figures (Creator) — isometric technical plates of machines."""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("anatomy_figure")
class AnatomyFigureTool(BaseTool):
    tool_id = "anatomy_figure"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="anatomy_figure",
            description=(
                "Isometric technical figures (the 'anatomy' skill): a technical "
                "idea drawn as a real machine, interactive, in an HTML page shown "
                "in Creator > Anatomía. action='examples' lists the plates, "
                "'build' builds one example by name, 'create' makes a NEW plate "
                "from 'request' (Sergio writes the build script with the kit and "
                "Node builds it; takes 1-3 minutes). Report only what it returns."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["examples", "build", "create"],
                    },
                    "name": {"type": "string", "description": "example name (build)"},
                    "request": {
                        "type": "string",
                        "description": "what to explain (create)",
                    },
                },
                "required": ["action"],
            },
            category="creative",
            timeout_seconds=600,
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.creator import anatomy_build as ab
        from openjarvis.creator.llm import CreatorError

        action = str(params.get("action") or "examples")
        try:
            if action == "build":
                name = str(params.get("name") or "")
                page = ab.build_example(name)
                return self._ok(
                    f"Lámina construida: {page}. Ábrala en Creator → Anatomía ({name})."
                )
            if action == "create":
                out = ab.create(str(params.get("request") or ""))
                return self._ok(
                    f"Lámina nueva «{out['title']}» construida en {out['attempts']} intento(s). "
                    f"Está en Creator → Anatomía ({out['name']})."
                )
            lines = [
                f"- {e['name']}: {e['title']} — {e['description']}"
                for e in ab.examples()
            ]
            return self._ok("Láminas disponibles:\n" + "\n".join(lines))
        except CreatorError as exc:
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)

    def _ok(self, text: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=text, success=True)


__all__ = ["AnatomyFigureTool"]

"""Tool: anatomy figures — isometric technical plates of machines.

The «Anatomy» skill is hidden (owner, 2026-10): it is not a section of the
app. Sergio uses it whenever an explanation is clearer as a drawn machine,
and the plate appears inside the chat (the web embeds any link to
``/v1/creator/anatomy/view/<name>`` found in the reply or in this result).
"""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


def view(name: str) -> str:
    return f"/v1/creator/anatomy/view/{name}"


@ToolRegistry.register("anatomy_figure")
class AnatomyFigureTool(BaseTool):
    tool_id = "anatomy_figure"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="anatomy_figure",
            description=(
                "Isometric technical figures (the hidden 'Anatomy' skill): explain "
                "how something works (a machine, an engine, a system, a technical "
                "idea) as an interactive drawing of a real machine that appears "
                "inside the chat. Use it whenever a drawing explains better than "
                "words. action='examples' lists ready plates, 'build' shows one "
                "example by name, 'create' draws a NEW plate from 'request' (takes "
                "1-3 minutes). Put the returned link in your answer as is; never "
                "mention a section called Anatomía."
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
                ab.build_example(name)
                return self._ok(
                    f"Lámina lista; aparece en el chat con este enlace: {view(name)}"
                )
            if action == "create":
                out = ab.create(str(params.get("request") or ""))
                return self._ok(
                    f"Lámina nueva «{out['title']}» dibujada en {out['attempts']} "
                    f"intento(s); aparece en el chat con este enlace: {view(out['name'])}"
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


__all__ = ["AnatomyFigureTool", "view"]

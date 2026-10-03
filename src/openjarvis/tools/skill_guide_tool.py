"""Tool: look up expert playbooks from ECC on demand (search, then read).

One small tool instead of ~350 skill tools keeps every prompt short; the full
guide only enters the conversation when Sergio decides it is useful.
"""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_NOTE = (
    "Note: ECC guides were written for coding agents such as Claude Code. Follow "
    "the method, but act with your own tools and the user's permissions."
)


@ToolRegistry.register("skill_guide")
class SkillGuideTool(BaseTool):
    tool_id = "skill_guide"

    def __init__(self, *, library: Any = None) -> None:
        self._library = library

    def _lib(self) -> Any:
        if self._library is None:
            from openjarvis.unified.ecc import Library

            self._library = Library()
        return self._library

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="skill_guide",
            description=(
                "Expert playbooks from ECC (Everything Claude Code): about 290 "
                "skills and 60 agent guides on research, writing, marketing, "
                "planning, coding, security, data and more. Use 'query' with "
                "English keywords to search (e.g. 'deep research', 'article "
                "writing', 'security review'), then 'name' to read the best match "
                "and follow it. 'file' reads an extra file listed by a skill."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "English keywords"},
                    "name": {"type": "string", "description": "guide to read"},
                    "file": {"type": "string", "description": "extra file of a skill"},
                },
            },
            category="knowledge",
        )

    def _result(self, content: str, ok: bool = True) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=content, success=ok)

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.unified.ecc import ECCError

        lib = self._lib()
        if not lib.installed:
            return self._result(
                "ECC is not downloaded yet. Ask the user to run `sergio ecc "
                "actualizar` in Ubuntu.",
                ok=False,
            )
        name = str(params.get("name") or "").strip()
        if name:
            try:
                body = lib.read(name, str(params.get("file") or ""))
            except ECCError as exc:
                return self._result(str(exc), ok=False)
            guide = lib.find(name)
            extras = lib.extra_files(guide) if guide and not params.get("file") else []
            tail = f"\n\nExtra files: {', '.join(extras)}" if extras else ""
            return self._result(f"{_NOTE}\n\n{body}{tail}")

        query = str(params.get("query") or "").strip()
        if not query:
            return self._result("Give 'query' to search or 'name' to read.", ok=False)
        hits = lib.search(query)
        if not hits:
            return self._result(
                f"No ECC guide matches {query!r}. Try other English keywords.", ok=False
            )
        lines = [f"ECC guides for {query!r} (read one with name=...):"]
        for guide in hits:
            lines.append(f"- {guide.name} [{guide.kind}]: {guide.description[:220]}")
        return self._result("\n".join(lines))


__all__ = ["SkillGuideTool"]

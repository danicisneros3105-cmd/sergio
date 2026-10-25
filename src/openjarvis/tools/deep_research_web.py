"""``investigacion_profunda``: real deep research on the web (:mod:`openjarvis.research.deep`).

For questions that need many sources and checking them («investiga a fondo…»,
«compara…», «qué dice la evidencia sobre…»). It takes minutes, not seconds:
for a quick fact ``web_search`` is the right tool.
"""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("investigacion_profunda")
class DeepResearchWebTool(BaseTool):
    tool_id = "investigacion_profunda"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Investigación profunda en la web: divide la pregunta, busca en muchas fuentes, "
                "LEE las páginas, comprueba cada dato con una cita literal, contrasta sitios "
                "distintos (confirmado / una fuente / en disputa), hace una segunda ronda por lo "
                "que falta y entrega un informe con citas [n]. Tarda unos minutos. Para un dato "
                "rápido use web_search."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "La pregunta completa.",
                    },
                    "rounds": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["question"],
            },
            category="research",
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.research.deep import research

        question = str(params.get("question") or "").strip()
        if not question:
            return ToolResult(self.tool_id, "Falta la pregunta.", False)
        try:
            report = research(question, rounds=int(params.get("rounds") or 2))
        except Exception as exc:  # noqa: BLE001 — told plainly, never a fake report
            return ToolResult(self.tool_id, f"No pude investigar: {exc}", False)
        return ToolResult(
            self.tool_id,
            report.markdown(),
            bool(report.findings),
            metadata={"stats": report.stats, "fuentes": len(report.sources)},
        )


__all__ = ["DeepResearchWebTool"]

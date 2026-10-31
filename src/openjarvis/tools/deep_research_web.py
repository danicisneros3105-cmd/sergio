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
                "Investigación profunda y Ultra Deep Research en la web (equivalente al trabajo de 10 especialistas humanos): "
                "descompone la pregunta en múltiples dimensiones (técnica, precios, fuentes primarias, críticas, "
                "benchmarks, marco legal y matriz de decisión), busca en paralelo con hasta 10 trabajadores concurrentes, "
                "LEE las páginas reales, comprueba cada dato con citas literales (descarta invenciones), contrasta sitios "
                "distintos (confirmado / una fuente / en disputa) y entrega un informe exhaustivo con score de certeza [n]. "
                "Para un dato rápido use web_search."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "La pregunta o tema completo a investigar.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["ultra", "standard"],
                        "description": "Modo de investigación: 'ultra' (10 analistas concurrentes, 10 dimensiones, 3 rondas) o 'standard' (2 rondas).",
                    },
                    "rounds": {"type": "integer", "minimum": 1, "maximum": 4},
                    "workers": {"type": "integer", "minimum": 1, "maximum": 16, "description": "Trabajadores paralelos (por defecto 10 en ultra)."},
                },
                "required": ["question"],
            },
            category="research",
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.research.deep import research, ultra_research

        question = str(params.get("question") or "").strip()
        if not question:
            return ToolResult(self.tool_id, "Falta la pregunta.", False)
        mode = str(params.get("mode") or "").strip().lower()
        workers = int(params.get("workers") or 10)
        rounds_param = params.get("rounds")
        rounds = int(rounds_param) if rounds_param else (3 if mode == "ultra" else 2)

        is_ultra = mode == "ultra" or any(
            w in question.lower()
            for w in ("ultra", "a fondo", "10 humanos", "diez humanos", "exhaustiv", "completa", "profundisima")
        )
        try:
            if is_ultra:
                report = ultra_research(question, rounds=rounds, workers=workers)
            else:
                report = research(question, rounds=rounds)
        except Exception as exc:  # noqa: BLE001 — told plainly, never a fake report
            return ToolResult(self.tool_id, f"No pude investigar: {exc}", False)
        return ToolResult(
            self.tool_id,
            report.markdown(),
            bool(report.findings),
            metadata={
                "stats": report.stats,
                "fuentes": len(report.sources),
                "confidence_score": getattr(report, "confidence_score", 0.0),
                "modo": "ultra" if is_ultra else "standard",
            },
        )


__all__ = ["DeepResearchWebTool"]

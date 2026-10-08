"""deep_think — answer a hard question with Sergio's ten reasoning layers."""

from __future__ import annotations

from typing import Any, Optional

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


class EngineTool(BaseTool):
    """A tool that needs a model. The agent's engine is injected when there is
    one (``needs_engine``); otherwise Sergio's configured model is used."""

    needs_engine = True

    def __init__(self, engine: Any = None, model: Optional[str] = None) -> None:
        self._engine = engine
        self._model = model

    def llm(self):
        from openjarvis.intelligence._llm import LLM

        if self._engine is not None and self._model:
            return LLM.from_engine(self._engine, self._model)
        return LLM.default()


@ToolRegistry.register("deep_think")
class DeepThinkTool(EngineTool):
    tool_id = "deep_think"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="deep_think",
            description=(
                "Think deeply about a hard question: picks the best reasoning strategy "
                "(self-reflection, tree of thoughts, majority voting, causal or what-if "
                "analysis), checks the answer against safety rules and reports a confidence. "
                "Use for math, logic, planning, cause/effect and high-stakes answers."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question or task."},
                    "strategy": {
                        "type": "string",
                        "enum": ["auto", "direct", "reflection", "tot", "consistency", "causal"],
                        "description": "Reasoning strategy (auto lets Sergio choose).",
                    },
                },
                "required": ["question"],
            },
            category="reasoning",
            cost_estimate=0.01,
            latency_estimate=20.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.intelligence.deep import deep_think
        from openjarvis.intelligence.uncertainty import default_calibrator
        from openjarvis.learning.meta_learner import default_learner

        question = str(params.get("question") or "").strip()
        if not question:
            return ToolResult(tool_name="deep_think", content="No question given.", success=False)
        try:
            result = deep_think(question, self.llm(), strategy=str(params.get("strategy") or "auto"),
                                learner=default_learner(), calibrator=default_calibrator())
        except Exception as exc:  # noqa: BLE001 — report to the agent, don't crash it
            return ToolResult(tool_name="deep_think", content=f"deep_think failed: {exc}", success=False)
        note = f"\n\n[strategy={result.strategy}, confidence={result.confidence:.0%}, decision={result.decision}]"
        return ToolResult(tool_name="deep_think", content=result.answer + note, success=True,
                          metadata={"strategy": result.strategy, "confidence": result.confidence,
                                    "decision": result.decision, "unknowns": result.unknowns})


__all__ = ["DeepThinkTool", "EngineTool"]

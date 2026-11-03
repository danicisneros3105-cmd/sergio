"""Tool: Sergio improves its own code (``evolution/automejora.py``).

The model proposes exact text changes to its own files with a reason; they
are tried in a separate copy, checked with ruff and the matching tests, and
applied only when everything passes (one commit, undone with
``action='deshacer'``). Never pushed to GitHub by itself.
"""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("mejorarme")
class AutomejoraTool(BaseTool):
    tool_id = "mejorarme"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="mejorarme",
            description=(
                "Improve or fix Sergio's OWN code (src/, windows/, frontend/src/, tests/). "
                "action='probar' tries 'cambios' (list of {path, old, new}: exact text to "
                "replace once; old='' creates a new file) for 'motivo' in a separate copy, "
                "runs ruff and the matching tests, and applies it only if they pass; "
                "'historial' lists past self-changes; 'lecciones' lists why recent tries were "
                "rejected (read it BEFORE retrying the same file); 'deshacer' undoes one "
                "by 'id'. Use it "
                "after an error you can explain, or when you see a clear improvement; add "
                "or update a test with the fix. Never touches key files, never pushes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["probar", "historial", "lecciones", "deshacer"],
                    },
                    "motivo": {"type": "string"},
                    "cambios": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "old": {"type": "string"},
                                "new": {"type": "string"},
                            },
                            "required": ["path", "new"],
                        },
                    },
                    "id": {"type": "string"},
                },
                "required": ["action"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.evolution import automejora as A

        action = str(params.get("action") or "")
        try:
            if action == "historial":
                rows = A.history()[-10:]
                text = (
                    "\n".join(
                        f"{r['id']} · {r['state']} · {r['reason'][:80]} · {r.get('checks', '')[:80]}"
                        for r in rows
                    )
                    or "Todavía no me he cambiado nada."
                )
                return ToolResult(tool_name=self.tool_id, content=text, success=True)
            if action == "lecciones":
                rows = A.lessons()
                text = (
                    "\n".join(
                        f"{', '.join(r['files'])} · {r['reason']} · {r['why']}"
                        for r in rows
                    )
                    or "No hay intentos rechazados que recordar."
                )
                return ToolResult(tool_name=self.tool_id, content=text, success=True)
            if action == "deshacer":
                m = A.revert(str(params.get("id") or ""))
                return ToolResult(
                    tool_name=self.tool_id,
                    content=f"Deshecha la mejora {m.id}.",
                    success=True,
                )
            if action == "probar":
                changes = [
                    A.Change(
                        str(c.get("path") or ""),
                        str(c.get("old") or ""),
                        str(c.get("new") or ""),
                    )
                    for c in params.get("cambios") or []
                ]
                before = A.failed_before([c.path for c in changes])
                m = A.improve(str(params.get("motivo") or "mejora"), changes)
                ok = m.state == "aplicada"
                head = "Aplicada" if ok else "No la apliqué"
                note = ""
                if not ok and before >= 2:
                    note = (
                        f" Ya rechacé {before} intentos sobre estos archivos: "
                        "pida 'lecciones', cambie de enfoque o dígaselo al señor."
                    )
                return ToolResult(
                    tool_name=self.tool_id,
                    content=f"{head} (id {m.id}). Comprobaciones: {m.checks[:1500]}{note}",
                    success=ok,
                )
        except A.AutomejoraError as exc:
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)
        return ToolResult(
            tool_name=self.tool_id, content="Acción desconocida.", success=False
        )


__all__ = ["AutomejoraTool"]

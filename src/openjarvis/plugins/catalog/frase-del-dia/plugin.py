"""Ejemplo de plugin para Sergio: un refrán por día, sin internet.

Un plugin define ``register(api)`` y registra sus herramientas con
``api.tool(Clase)``. Cada herramienta es una subclase de ``BaseTool``.
"""

import datetime
import json

from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_API = None


class FraseDelDia(BaseTool):
    tool_id = "frase_del_dia"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="frase_del_dia",
            description="Devuelve el refrán del día (cambia cada día).",
            parameters={"type": "object", "properties": {}},
            category="fun",
        )

    def execute(self, **params) -> ToolResult:
        frases = json.loads(_API.asset("assets/frases.json").read_text("utf-8"))
        hoy = datetime.date.today().toordinal()
        return ToolResult(
            tool_name="frase_del_dia", content=frases[hoy % len(frases)], success=True
        )


def register(api) -> None:
    global _API
    _API = api
    api.tool(FraseDelDia)


__all__ = ["FraseDelDia", "register"]

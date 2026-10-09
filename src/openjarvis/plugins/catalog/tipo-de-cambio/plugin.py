"""Ejemplo de plugin con internet: convierte entre monedas con la tasa del día.

Usa la API abierta de ExchangeRate-API (sin clave). Declara el permiso
``network:fetch`` en plugin.toml; sin él, Sergio no carga la herramienta.
"""

import httpx

from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

URL = "https://open.er-api.com/v6/latest/{base}"


class TipoDeCambio(BaseTool):
    tool_id = "tipo_de_cambio"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="tipo_de_cambio",
            description="Convierte un monto de una moneda a otra con la tasa del día (códigos ISO: USD, EUR…).",
            parameters={
                "type": "object",
                "properties": {
                    "monto": {"type": "number", "description": "Cantidad a convertir."},
                    "de": {
                        "type": "string",
                        "description": "Moneda de origen, p. ej. USD.",
                    },
                    "a": {
                        "type": "string",
                        "description": "Moneda de destino, p. ej. EUR.",
                    },
                },
                "required": ["monto", "de", "a"],
            },
            category="finance",
            required_capabilities=["network:fetch"],
        )

    def execute(self, **params) -> ToolResult:
        base = str(params.get("de", "USD")).upper()[:3]
        target = str(params.get("a", "EUR")).upper()[:3]
        try:
            amount = float(params.get("monto", 1))
            data = httpx.get(URL.format(base=base), timeout=10).json()
            rate = float(data["rates"][target])
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                tool_name="tipo_de_cambio",
                content=f"No pude consultar la tasa: {exc}",
                success=False,
            )
        when = data.get("time_last_update_utc", "hoy")
        return ToolResult(
            tool_name="tipo_de_cambio",
            content=f"{amount:,.2f} {base} = {amount * rate:,.2f} {target} (tasa {rate:.4f}, {when})",
            success=True,
        )


def register(api) -> None:
    api.tool(TipoDeCambio)


__all__ = ["TipoDeCambio", "register"]

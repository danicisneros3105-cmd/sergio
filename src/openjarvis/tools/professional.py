"""Use complete external applications; never claim detection equals integration."""

import json
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.professional.catalog import BY_ID, catalog
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("professional_apps")
class ProfessionalAppsTool(BaseTool):
    tool_id = "professional_apps"

    @property
    def spec(self):
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Detect professional programs on this server, or explicitly "
                "open a complete program on the Windows companion. Use ArtCraft "
                "for creative work, FreeCAD/Bonsai/LibreCAD for architecture "
                "and VSCodium for code. No automatic installation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"enum": ["catalog", "open"], "type": "string"},
                    "id": {"type": "string", "enum": list(BY_ID)},
                },
                "required": ["action"],
            },
            category="desktop",
            timeout_seconds=130,
        )

    def execute(self, **params: Any):
        try:
            if params.get("action") == "catalog":
                data = catalog()
                # Live responses are bounded to 4k characters. Keep the whole
                # catalogue readable instead of truncating its JSON mid-record.
                data["programs"] = [
                    {k: p[k] for k in ("id", "name", "detected", "adapter")}
                    for p in data["programs"]
                ]
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                )
            if params.get("action") != "open":
                raise ValueError("Operación no válida.")
            program = BY_ID.get(params.get("id", ""))
            if not program or not program.opens_window:
                raise ValueError("La integración requiere su configuración específica.")
            from openjarvis.tools.desktop_tools import DesktopActionTool

            result = DesktopActionTool().execute(action="open_app", target=program.name)
            return ToolResult(
                tool_name=self.tool_id, content=result.content, success=result.success
            )
        except Exception as exc:
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)


@ToolRegistry.register("opendesign")
class OpenDesignTool(BaseTool):
    tool_id = "opendesign"

    @property
    def spec(self):
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Use the locally installed full OpenDesign editor: list "
                "designs/templates/brands, create a canvas, read fields or "
                "fill a template. No publishing or deletions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "list",
                            "templates",
                            "brands",
                            "get",
                            "fields",
                            "create",
                            "fill",
                            "update",
                        ],
                    },
                    "payload_json": {
                        "type": "string",
                        "description": "JSON with id, name, width/height, canvas_json or template values.",
                    },
                },
                "required": ["operation"],
            },
        )

    def execute(self, **params: Any):
        try:
            from openjarvis.professional.opendesign import request

            raw = params.get("payload_json", "{}")
            if not isinstance(raw, str) or len(raw) > 512_000:
                raise ValueError("Payload demasiado grande o inválido.")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("El payload debe ser un objeto JSON.")
            data = request(params.get("operation", ""), payload)
            return ToolResult(
                tool_name=self.tool_id, content=json.dumps(data, ensure_ascii=False)
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"OpenDesign no completó la operación: {exc}",
                success=False,
            )


@ToolRegistry.register("kronos_forecast")
class KronosTool(BaseTool):
    tool_id = "kronos_forecast"

    @property
    def spec(self):
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Run optional local Kronos-small on validated OHLCV historical "
                "candles and explicit future market timestamps. Returns a "
                "model scenario, not guaranteed prices. Never trades. "
                "Requires installed runtime and local weights."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "minItems": 16,
                        "maxItems": 512,
                        "items": {
                            "type": "object",
                            "properties": {
                                "timestamp": {"type": "string"},
                                "open": {"type": "number"},
                                "high": {"type": "number"},
                                "low": {"type": "number"},
                                "close": {"type": "number"},
                                "volume": {"type": "number"},
                                "amount": {"type": "number"},
                            },
                            "required": ["timestamp", "open", "high", "low", "close"],
                        },
                    },
                    "future_timestamps": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 120,
                        "items": {"type": "string"},
                    },
                },
                "required": ["rows", "future_timestamps"],
            },
            timeout_seconds=130,
        )

    def execute(self, **params: Any):
        try:
            from openjarvis.professional.kronos import forecast

            out = forecast(params.get("rows", []), params.get("future_timestamps", []))
            return ToolResult(
                tool_name=self.tool_id, content=json.dumps(out, ensure_ascii=False)
            )
        except Exception as exc:
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)


__all__ = ["KronosTool", "OpenDesignTool", "ProfessionalAppsTool"]

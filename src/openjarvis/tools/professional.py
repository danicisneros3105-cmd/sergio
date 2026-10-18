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
                "Detect professional programs on this server ('catalog'), explicitly "
                "open a complete program on the Windows companion ('open'), or run "
                "Sergio's internal Creator engines: 2D CAD floor plans ('plan_dxf'), "
                "3D BIM building models ('plan_ifc'), Canva-style design layouts "
                "('design_layout'), image generation ('image_generate'), generative "
                "image editing ('image_edit'), and local neural background removal "
                "('image_cutout'). Use ArtCraft for creative work, "
                "FreeCAD/Bonsai/LibreCAD for architecture and VSCodium for code. "
                "No automatic installation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "enum": [
                            "catalog",
                            "open",
                            "plan_dxf",
                            "plan_ifc",
                            "design_layout",
                            "image_generate",
                            "image_edit",
                            "image_cutout",
                        ],
                        "type": "string",
                    },
                    "id": {"type": "string", "enum": list(BY_ID)},
                    "walls": {
                        "type": "array",
                        "description": (
                            "Walls in metres for plan_dxf / plan_ifc: "
                            "[{x1, y1, x2, y2, thickness, height}]."
                        ),
                        "items": {"type": "object"},
                    },
                    "openings": {
                        "type": "array",
                        "description": (
                            "Doors/windows in metres for plan_dxf / plan_ifc: "
                            "[{x, y, width, angle, kind: 'puerta'|'ventana'}]."
                        ),
                        "items": {"type": "object"},
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Design/image prompt or edit instruction.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Local file path to read or save.",
                    },
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                },
                "required": ["action"],
            },
            category="desktop",
            timeout_seconds=130,
        )

    def execute(self, **params: Any):
        try:
            action = params.get("action")
            if action == "catalog":
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
            if action in ("plan_dxf", "plan_ifc"):
                from pathlib import Path

                from openjarvis.creator import bim, programs, studio

                walls = list(params.get("walls") or [])
                openings = list(params.get("openings") or [])
                ext = "ifc" if action == "plan_ifc" else "dxf"
                raw = (
                    bim.plan_ifc(walls, openings)
                    if ext == "ifc"
                    else studio.plan_dxf(walls, openings)
                )
                raw_path = str(params.get("path") or "").strip()
                out_path = (
                    Path(raw_path).expanduser().resolve()
                    if raw_path
                    else studio.projects_root() / "planos" / f"plano-sergio.{ext}"
                )
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(raw)
                pid = str(params.get("id") or "").strip().lower()
                msg = f"Plano {ext.upper()} guardado en {out_path} ({len(raw)} bytes)."
                if pid in programs.OPENS.get(ext, ()):
                    msg += " " + programs.open_in_windows(pid, out_path.name, raw)
                return ToolResult(tool_name=self.tool_id, content=msg)
            if action == "design_layout":
                from openjarvis.creator import studio

                w = int(params.get("width") or 1080)
                h = int(params.get("height") or 1080)
                layout = studio.design_layout(str(params.get("prompt") or ""), w, h)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps(layout, ensure_ascii=False),
                )
            if action == "image_generate":
                from pathlib import Path

                from openjarvis.creator import programs, studio

                png = studio.generate_image(str(params.get("prompt") or ""))
                raw_path = str(params.get("path") or "").strip()
                out_path = (
                    Path(raw_path).expanduser().resolve()
                    if raw_path
                    else studio.projects_root() / "imagenes" / "imagen-sergio.png"
                )
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(png)
                msg = f"Imagen generada en {out_path}."
                if str(params.get("id") or "").lower() == "artcraft":
                    msg += " " + programs.open_in_windows("artcraft", out_path.name, png)
                return ToolResult(tool_name=self.tool_id, content=msg)
            if action in ("image_edit", "image_cutout"):
                from pathlib import Path

                from openjarvis.creator import studio

                src = Path(str(params.get("path") or "")).expanduser().resolve()
                if not src.is_file():
                    raise ValueError("El archivo de imagen indicado no existe.")
                raw_bytes = src.read_bytes()
                if action == "image_cutout":
                    png, method = studio.cutout_detail(raw_bytes)
                    out_path = src.with_name(f"{src.stem}-recorte.png")
                    out_path.write_bytes(png)
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=f"Fondo recortado ({method}) guardado en {out_path}.",
                    )
                png = studio.edit_image(raw_bytes, str(params.get("prompt") or ""))
                out_path = src.with_name(f"{src.stem}-editada.png")
                out_path.write_bytes(png)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=f"Imagen editada guardada en {out_path}.",
                )
            if action != "open":
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

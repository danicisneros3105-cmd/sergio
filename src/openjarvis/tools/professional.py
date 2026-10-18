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
                "3D BIM building models ('plan_ifc'), 3D/2D Godot 4 game & simulation "
                "projects ('godot_project'), Canva-style design layouts "
                "('design_layout'), image generation ('image_generate'), generative "
                "image editing ('image_edit'), and local neural background removal "
                "('image_cutout'). Generated images include a markdown image link "
                "![...](/v1/creator/media/...) that renders inline in chat."
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
                            "godot_project",
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
                        "description": "Design/image/game prompt or edit instruction.",
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
            if action == "godot_project":
                import re as _re
                import time as _time
                from pathlib import Path
                from openjarvis.creator import programs, studio

                prompt = str(params.get("prompt") or "Exploración 3D en mundo abierto con iluminación global").strip()
                slug = _re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")[:32] or "juego-3d"
                proj_dir = studio.projects_root() / "godot" / f"{slug}-{int(_time.time()) % 10000}"
                (proj_dir / "scenes").mkdir(parents=True, exist_ok=True)
                (proj_dir / "scripts").mkdir(parents=True, exist_ok=True)
                project_godot = (
                    "; Engine configuration file.\n"
                    "config_version=5\n\n"
                    "[application]\n"
                    f'config/name="Sergio Creator - {prompt[:48]}"\n'
                    'run/main_scene="res://scenes/main.tscn"\n'
                    'config/features=PackedStringArray("4.3", "Forward Plus")\n\n'
                    "[rendering]\n"
                    "anti_aliasing/quality/msaa_3d=2\n"
                )
                main_tscn = (
                    '[gd_scene load_steps=6 format=3 uid="uid://sergio3dmain"]\n\n'
                    '[ext_resource type="Script" path="res://scripts/player_controller.gd" id="1_player"]\n\n'
                    '[sub_resource type="ProceduralSkyMaterial" id="SkyMat"]\n'
                    '[sub_resource type="Sky" id="Sky_1"]\n'
                    'sky_material = SubResource("SkyMat")\n'
                    '[sub_resource type="Environment" id="Env_1"]\n'
                    'background_mode = 2\n'
                    'sky = SubResource("Sky_1")\n'
                    'sdfgi_enabled = true\n'
                    'glow_enabled = true\n\n'
                    '[sub_resource type="BoxMesh" id="FloorMesh"]\n'
                    'size = Vector3(60, 0.5, 60)\n\n'
                    '[node name="MainWorld" type="Node3D"]\n\n'
                    '[node name="WorldEnvironment" type="WorldEnvironment" parent="."]\n'
                    'environment = SubResource("Env_1")\n\n'
                    '[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]\n'
                    'transform = Transform3D(0.866, -0.353, 0.353, 0, 0.707, 0.707, -0.5, -0.612, 0.612, 0, 12, 0)\n'
                    'shadow_enabled = true\n\n'
                    '[node name="ArenaFloor" type="CSGBox3D" parent="."]\n'
                    'use_collision = true\n'
                    'size = Vector3(60, 0.5, 60)\n\n'
                    '[node name="Player3D" type="CharacterBody3D" parent="."]\n'
                    'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0)\n'
                    'script = ExtResource("1_player")\n\n'
                    '[node name="Camera3D" type="Camera3D" parent="Player3D"]\n'
                    'transform = Transform3D(1, 0, 0, 0, 0.96, 0.28, 0, -0.28, 0.96, 0, 1.7, 3.5)\n'
                )
                player_gd = (
                    "extends CharacterBody3D\n"
                    f"# Generado por Sergio Creator para: {prompt}\n\n"
                    "const SPEED = 7.5\n"
                    "const JUMP_VELOCITY = 5.2\n"
                    "var gravity: float = ProjectSettings.get_setting('physics/3d/default_gravity')\n\n"
                    "func _physics_process(delta: float) -> void:\n"
                    "\tif not is_on_floor():\n"
                    "\t\tvelocity.y -= gravity * delta\n"
                    "\tif Input.is_action_just_pressed('ui_accept') and is_on_floor():\n"
                    "\t\tvelocity.y = JUMP_VELOCITY\n"
                    "\tvar input_dir := Input.get_vector('ui_left', 'ui_right', 'ui_up', 'ui_down')\n"
                    "\tvar direction := (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()\n"
                    "\tif direction:\n"
                    "\t\tvelocity.x = direction.x * SPEED\n"
                    "\t\tvelocity.z = direction.z * SPEED\n"
                    "\telse:\n"
                    "\t\tvelocity.x = move_toward(velocity.x, 0, SPEED)\n"
                    "\t\tvelocity.z = move_toward(velocity.z, 0, SPEED)\n"
                    "\tmove_and_slide()\n"
                )
                proj_file = proj_dir / "project.godot"
                proj_file.write_text(project_godot, encoding="utf-8")
                (proj_dir / "scenes" / "main.tscn").write_text(main_tscn, encoding="utf-8")
                (proj_dir / "scripts" / "player_controller.gd").write_text(player_gd, encoding="utf-8")
                msg = (
                    f"Proyecto 3D de Godot Engine 4 creado en `{proj_dir}` "
                    "(`project.godot`, `scenes/main.tscn` con iluminación global SDFGI y cielo físico, "
                    "`scripts/player_controller.gd`)."
                )
                try:
                    msg += " " + programs.open_in_windows("godot", "project.godot", project_godot.encode("utf-8"))
                except Exception:
                    pass
                return ToolResult(tool_name=self.tool_id, content=msg)
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
                import time as _time
                from pathlib import Path

                from openjarvis.creator import programs, studio

                prompt_str = str(params.get("prompt") or "Ilustración editorial")
                png = studio.generate_image(prompt_str)
                fname = f"imagen-sergio-{int(_time.time() * 1000) % 1000000}.png"
                media_dir = studio.projects_root() / "imagenes"
                media_dir.mkdir(parents=True, exist_ok=True)
                media_path = media_dir / fname
                media_path.write_bytes(png)
                raw_path = str(params.get("path") or "").strip()
                if raw_path:
                    out_path = Path(raw_path).expanduser().resolve()
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(png)
                else:
                    out_path = media_path
                url = f"/v1/creator/media/{fname}"
                msg = (
                    f"Imagen generada en {out_path}.\n\n"
                    f"![{prompt_str[:60]}]({url})"
                )
                if str(params.get("id") or "").lower() == "artcraft":
                    msg += "\n" + programs.open_in_windows("artcraft", out_path.name, png)
                return ToolResult(tool_name=self.tool_id, content=msg)
            if action in ("image_edit", "image_cutout"):
                import time as _time
                from pathlib import Path

                from openjarvis.creator import studio

                src = Path(str(params.get("path") or "")).expanduser().resolve()
                if not src.is_file():
                    raise ValueError("El archivo de imagen indicado no existe.")
                raw_bytes = src.read_bytes()
                media_dir = studio.projects_root() / "imagenes"
                media_dir.mkdir(parents=True, exist_ok=True)
                if action == "image_cutout":
                    png, method = studio.cutout_detail(raw_bytes)
                    out_path = src.with_name(f"{src.stem}-recorte.png")
                    out_path.write_bytes(png)
                    fname = f"recorte-{int(_time.time() * 1000) % 1000000}.png"
                    (media_dir / fname).write_bytes(png)
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=(
                            f"Fondo recortado ({method}) guardado en {out_path}.\n\n"
                            f"![Recorte]({f'/v1/creator/media/{fname}'})"
                        ),
                    )
                png = studio.edit_image(raw_bytes, str(params.get("prompt") or ""))
                out_path = src.with_name(f"{src.stem}-editada.png")
                out_path.write_bytes(png)
                fname = f"editada-{int(_time.time() * 1000) % 1000000}.png"
                (media_dir / fname).write_bytes(png)
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Imagen editada guardada en {out_path}.\n\n"
                        f"![Imagen editada]({f'/v1/creator/media/{fname}'})"
                    ),
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

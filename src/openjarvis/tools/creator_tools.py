"""Tool: anatomy figures — isometric technical plates of machines.

The «Anatomy» skill is hidden (owner, 2026-10): it is not a section of the
app. Sergio uses it whenever an explanation is clearer as a drawn machine,
and the plate appears inside the chat (the web embeds any link to
``/v1/creator/anatomy/view/<name>`` found in the reply or in this result).
"""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


def view(name: str) -> str:
    return f"/v1/creator/anatomy/view/{name}"


@ToolRegistry.register("anatomy_figure")
class AnatomyFigureTool(BaseTool):
    tool_id = "anatomy_figure"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="anatomy_figure",
            description=(
                "Isometric technical figures (the hidden 'Anatomy' skill): explain "
                "how something works (a machine, an engine, a system, a technical "
                "idea) as an interactive drawing of a real machine that appears "
                "inside the chat. Use it whenever a drawing explains better than "
                "words. action='examples' lists ready plates, 'build' shows one "
                "example by name, 'create' draws a NEW plate from 'request' (takes "
                "1-3 minutes). Put the returned link in your answer as is; never "
                "mention a section called Anatomía."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["examples", "build", "create"],
                    },
                    "name": {"type": "string", "description": "example name (build)"},
                    "request": {
                        "type": "string",
                        "description": "what to explain (create)",
                    },
                },
                "required": ["action"],
            },
            category="creative",
            timeout_seconds=600,
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.creator import anatomy_build as ab
        from openjarvis.creator.llm import CreatorError

        action = str(params.get("action") or "examples")
        try:
            if action == "build":
                name = str(params.get("name") or "")
                ab.build_example(name)
                return self._ok(
                    f"Lámina lista; aparece en el chat con este enlace: {view(name)}"
                )
            if action == "create":
                out = ab.create(str(params.get("request") or ""))
                return self._ok(
                    f"Lámina nueva «{out['title']}» dibujada en {out['attempts']} "
                    f"intento(s); aparece en el chat con este enlace: {view(out['name'])}"
                )
            lines = [
                f"- {e['name']}: {e['title']} — {e['description']}"
                for e in ab.examples()
            ]
            return self._ok("Láminas disponibles:\n" + "\n".join(lines))
        except CreatorError as exc:
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)

    def _ok(self, text: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=text, success=True)


@ToolRegistry.register("modelo_por_piezas")
class TakeApartModelTool(BaseTool):
    """3D models that take apart inside the chat (creator/despiece.py)."""

    tool_id = "modelo_por_piezas"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="modelo_por_piezas",
            description=(
                "A detailed 3D model the person can turn, take apart and see piece "
                "by piece INSIDE the chat (each part named, with what it does). "
                "Use it when someone asks for a 3D model, a car, an engine, a "
                "machine, a building or anything to see «por piezas». "
                "action='crear' draws it from 'request' with real measurements "
                "(1-3 minutes; very detailed); 'buscar' finds free CC0 models on "
                "the internet (never game mods or ripped assets) and 'descargar' "
                "gets one by 'id'; 'abrir' shows a .glb/.gltf on this computer "
                "('path'); 'nube' makes a professional, very detailed model from "
                "'request' (a description) or 'image' (a photo on this computer) "
                "with the cloud 3D services the professionals use (Meshy, Tripo, "
                "fal.ai Hunyuan3D/TRELLIS), 2-10 minutes. Put the returned link in "
                "the answer as is."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["crear", "nube", "buscar", "descargar", "abrir"],
                    },
                    "request": {
                        "type": "string",
                        "description": "what to model (crear) or search (buscar)",
                    },
                    "id": {
                        "type": "string",
                        "description": "model id from buscar (descargar)",
                    },
                    "path": {
                        "type": "string",
                        "description": ".glb/.gltf file (abrir)",
                    },
                    "image": {
                        "type": "string",
                        "description": "a photo on this computer to turn into 3D (nube)",
                    },
                },
                "required": ["action"],
            },
            category="creative",
            timeout_seconds=600,
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.creator import despiece
        from openjarvis.creator.llm import CreatorError

        action = str(params.get("action") or "crear")
        try:
            if action == "buscar":
                hits = despiece.search_cc0(str(params.get("request") or ""))
                if not hits:
                    return self._ok(
                        "No encontré modelos libres (CC0) con eso. Puedo dibujarlo yo: action='crear'."
                    )
                lines = [f"- {h['id']}: {h['nombre']} (CC0)" for h in hits]
                return self._ok("Modelos libres encontrados:\n" + "\n".join(lines))
            if action == "descargar":
                meta = despiece.download(str(params.get("id") or ""))
            elif action == "abrir":
                meta = despiece.register_file(str(params.get("path") or ""))
            elif action == "nube":
                from pathlib import Path

                from openjarvis.creator import nube3d

                photo = str(params.get("image") or "").strip()
                picture = Path(photo).expanduser().read_bytes() if photo else b""
                try:
                    meta = nube3d.generate(str(params.get("request") or ""), picture)
                except nube3d.Nube3DError as exc:
                    return ToolResult(
                        tool_name=self.tool_id, content=str(exc), success=False
                    )
            else:
                meta = despiece.create(str(params.get("request") or ""))
        except CreatorError as exc:
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)
        except Exception as exc:  # noqa: BLE001 — the internet, a broken file
            return ToolResult(
                tool_name=self.tool_id,
                content=f"No pude preparar el modelo: {exc}",
                success=False,
            )
        parts = f" con {meta['piezas']} piezas" if meta.get("piezas") else ""
        credit = f" Fuente: {meta['fuente']}" + (
            f", licencia {meta['licencia']}." if meta.get("licencia") else "."
        )
        return self._ok(
            f"Modelo «{meta['titulo']}» listo{parts}; aparece en el chat con este enlace: "
            f"{despiece.view(meta['name'])}.{credit}"
        )

    def _ok(self, text: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=text, success=True)


__all__ = ["AnatomyFigureTool", "TakeApartModelTool", "view"]

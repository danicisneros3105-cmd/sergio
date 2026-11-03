"""Tool: Sergio's aesthetic judgement (the 25 superskills) and measuring an image."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("criterio_estetico")
class CriterioEsteticoTool(BaseTool):
    tool_id = "criterio_estetico"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="criterio_estetico",
            description=(
                "Art direction with Sergio's 25 aesthetic superskills (negative space, balance, light, "
                "materials, glass, metal, packaging, typography, industrial design, lamps, still life, "
                "minimalism, system, curation). action='guia' with 'encargo' returns the 2-3 that fit, "
                "with their parameters, rejection patterns and 1-100 matrices: read it BEFORE designing an "
                "image, artifact, packaging or layout. action='evaluar' with 'ruta' (an image file or a "
                "/v1/creator/media/… address) measures it (negative space, mass, golden lines, light, "
                "palette, tonal steps) and scores the measurable criteria; judge the rest yourself and "
                "approve only at 85+. action='estado' says whether the owner's Pinterest profile exists."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["guia", "evaluar", "estado"]},
                    "encargo": {"type": "string"},
                    "ruta": {"type": "string"},
                },
                "required": ["action"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.estetica import medir, pinterest, superskills

        action = str(params.get("action") or "")
        if action == "guia":
            brief = str(params.get("encargo") or "")
            skills = superskills.all_skills()
            picked = superskills.pick(brief, 2)
            parts = []
            for k in picked:
                s = skills[k]
                if k == 25:
                    parts.append(f"## Superskill 25: {s['nombre']}\n{s['parametros']}")
                else:
                    parts.append(
                        f"## Superskill {k}: {s['nombre']}\nParámetros: {s['parametros']}\n"
                        f"Rechazo: {s['rechazo']}\nMatriz: {s['matriz']}"
                    )
            return ToolResult(
                tool_name=self.tool_id, content="\n\n".join(parts), success=True
            )
        if action == "evaluar":
            path = self._path(str(params.get("ruta") or ""))
            if path is None:
                return ToolResult(
                    tool_name=self.tool_id,
                    content="No encuentro esa imagen.",
                    success=False,
                )
            m = medir.measure(path)
            ranges = pinterest.owner_ranges()
            out = {
                "medidas": m,
                "puntos_medibles": medir.score(m, ranges),
                "rangos": "los de sus tableros de Pinterest"
                if ranges
                else "los de las superskills (aún sin sus tableros)",
                "nota": "Solo una parte de cada matriz se mide; la composición y el relato se juzgan mirando.",
            }
            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(out, ensure_ascii=False),
                success=True,
            )
        if action == "estado":
            prof = pinterest.home() / "perfil.json"
            if prof.is_file():
                data = json.loads(prof.read_text("utf-8"))
                text = f"Perfil de sus tableros: {data.get('imagenes', 0)} imágenes medidas."
            else:
                text = (
                    "Todavía no hay perfil de sus tableros: `sergio estetica pinterest` "
                    "en su PC (con PINTEREST_TOKEN)."
                )
            return ToolResult(tool_name=self.tool_id, content=text, success=True)
        return ToolResult(
            tool_name=self.tool_id, content="Acción desconocida.", success=False
        )

    @staticmethod
    def _path(ref: str) -> Path | None:
        if ref.startswith("/v1/creator/media/"):
            from openjarvis.creator import studio

            name = ref.rsplit("/", 1)[-1]
            for p in (
                studio.projects_root() / "imagenes" / name,
                studio.projects_root() / name,
            ):
                if p.is_file():
                    return p
            return None
        p = Path(ref).expanduser()
        return p if p.is_file() else None


__all__ = ["CriterioEsteticoTool"]

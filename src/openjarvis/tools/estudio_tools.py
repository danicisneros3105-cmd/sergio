"""The four studio programs as four tools, one job each (``openjarvis/estudio/``)."""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


def _run(tool_id: str, fn: Any) -> ToolResult:
    try:
        return ToolResult(tool_name=tool_id, content=fn(), success=True)
    except Exception as exc:  # noqa: BLE001 — plain words, never a crash
        return ToolResult(
            tool_name=tool_id,
            content=f"No pude hacerlo: {str(exc)[:240]}",
            success=False,
        )


@ToolRegistry.register("clips_cine")
class FilmClipsTool(BaseTool):
    tool_id = "clips_cine"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="clips_cine",
            description=(
                "ONLY for finding scenes of real films and series on the internet for a video: "
                "names real scenes that show the idea and finds official clips of each (never "
                "full movies), plus public-domain films. Returns links; nothing is downloaded."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tema": {
                        "type": "string",
                        "description": "what the video or the shot says",
                    },
                    "cuantas": {"type": "integer", "description": "scenes (default 5)"},
                },
                "required": ["tema"],
            },
            category="media",
            timeout_seconds=300,
        )

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.estudio import clips_cine

        n = max(1, min(int(p.get("cuantas") or 5), 10))
        return _run(
            self.tool_id,
            lambda: clips_cine.texto(clips_cine.buscar(str(p.get("tema") or ""), n)),
        )


@ToolRegistry.register("miniaturas")
class ThumbnailsTool(BaseTool):
    tool_id = "miniaturas"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="miniaturas",
            description=(
                "ONLY for video thumbnails: from a video or picture file, picks the best frames "
                "(sharp, contrast, faces), puts 2-4 big words on the free side, checks they read "
                "at phone size, and saves 3 variants for an A/B test. Nothing is uploaded."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "archivo": {
                        "type": "string",
                        "description": "video or picture path",
                    },
                    "texto": {"type": "string", "description": "2-4 words (optional)"},
                    "titulo": {
                        "type": "string",
                        "description": "the video's title, to take words from",
                    },
                    "acento": {
                        "type": "string",
                        "description": "brand colour #rrggbb (optional)",
                    },
                },
                "required": ["archivo"],
            },
            category="media",
            timeout_seconds=300,
        )

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.estudio import miniaturas

        return _run(self.tool_id, lambda: miniaturas.texto_de(miniaturas.crear(
            str(p.get("archivo") or ""), str(p.get("texto") or ""), str(p.get("titulo") or ""),
            acento=str(p.get("acento") or ""))))  # fmt: skip


@ToolRegistry.register("titulos_video")
class TitlesTool(BaseTool):
    tool_id = "titulos_video"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="titulos_video",
            description=(
                "ONLY for titles of videos and hooks of reels: writes many candidates from "
                "different angles and scores each by code (length for the platform, topic first, "
                "specific, curiosity without lies, no shouting), returns the best with reasons "
                "and an A/B pair. Optionally uses real trend words."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tema": {"type": "string"},
                    "plataforma": {
                        "type": "string",
                        "enum": ["youtube", "shorts", "reels", "tiktok"],
                    },
                    "con_tendencias": {
                        "type": "boolean",
                        "description": "add words trending now",
                    },
                    "pais": {"type": "string"},
                },
                "required": ["tema"],
            },
            category="media",
            timeout_seconds=180,
        )

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.estudio import titulos

        def go() -> str:
            trend: list = []
            if p.get("con_tendencias"):
                from openjarvis.automatiza import tendencias

                data = tendencias.read(
                    str(p.get("pais") or "EC"), str(p.get("tema") or "")
                )
                trend = [s["tema"] for s in (data.get("senales") or [])[:20]]
            return titulos.texto(titulos.generar(str(p.get("tema") or ""), str(p.get("plataforma") or "youtube"),
                                                 tendencias=trend))  # fmt: skip

        return _run(self.tool_id, go)


@ToolRegistry.register("radar_tendencias")
class TrendRadarTool(BaseTool):
    tool_id = "radar_tendencias"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="radar_tendencias",
            description=(
                "ONLY for researching trends, the platform algorithm and the audience of a niche: "
                "reads Google Trends, Wikipedia, Reddit, YouTube, what people type in YouTube and "
                "Google search, the top videos of the niche and their title patterns, and what "
                "YouTube/Instagram/TikTok said publicly about ranking; returns opportunities each "
                "tied to real data. 'profundo': also deep web research on the audience."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "nicho": {"type": "string"},
                    "pais": {
                        "type": "string",
                        "description": "two letters, e.g. EC, MX, ES, US",
                    },
                    "plataforma": {
                        "type": "string",
                        "enum": ["youtube", "instagram", "tiktok"],
                    },
                    "profundo": {"type": "boolean"},
                },
                "required": [],
            },
            category="media",
            timeout_seconds=900,
        )

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.estudio import radar

        return _run(self.tool_id, lambda: radar.texto(radar.analizar(
            str(p.get("nicho") or ""), str(p.get("pais") or "EC"), str(p.get("plataforma") or "youtube"),
            profundo=bool(p.get("profundo")))))  # fmt: skip


__all__ = ["FilmClipsTool", "ThumbnailsTool", "TitlesTool", "TrendRadarTool"]

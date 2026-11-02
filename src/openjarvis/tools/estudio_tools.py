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


@ToolRegistry.register("escuela_video")
class VideoSchoolTool(BaseTool):
    tool_id = "escuela_video"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="escuela_video",
            description=(
                "Sergio's school of the owner's reference videos and channels (the latest 20 of a "
                "channel): downloads each one (only to study it), measures every second by code, at "
                "30 fps for channels (cuts, shot length, light, contrast, shadows, warm or cool grade, "
                "camera movement and shake, flashes, words on screen, faces, sound hits) and reads how "
                "the script is written (pace, hook, sentences, questions, turns, open loops, ending), "
                "watches it with a model, and writes one superskill per category that every later "
                "video of that kind follows. 'agregar' also takes a channel link (youtube.com/@name). "
                "action 'estudiar' (all, or 'categoria'), 'estado', 'agregar' ('links' and "
                "'categoria'), 'superskill' ('categoria': read it), 'ficha' ('video': everything measured "
                "about one reference, second by second). To recreate one exactly, call video_essay "
                "with 'molde' = its link. Runs in the background."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "estudiar",
                            "estado",
                            "agregar",
                            "superskill",
                            "ficha",
                        ],
                    },
                    "categoria": {"type": "string"},
                    "links": {"type": "array", "items": {"type": "string"}},
                    "video": {
                        "type": "string",
                        "description": "ficha: the studied reference's link",
                    },
                },
                "required": ["action"],
            },
            category="media",
            timeout_seconds=120,
        )

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.video_essay import escuela

        def go() -> str:
            action = str(p.get("action") or "estado")
            cat = str(p.get("categoria") or "").strip()
            if action == "agregar":
                r = escuela.add(list(p.get("links") or []), cat or "mis-referencias")
                return (
                    f"Agregué {r['agregados']} enlaces a «{r['categoria']}». "
                    "Diga «estudia las referencias» para aprenderlos."
                )
            if action == "ficha":
                return escuela.ficha(str(p.get("video") or (p.get("links") or [""])[0]))
            if action == "superskill":
                return (
                    escuela.skill_text(cat)
                    or "Esa categoría todavía no tiene superskill: falta estudiarla."
                )
            if action == "estudiar":
                refs = escuela.references()
                cats = [cat] if cat in refs else None
                if not escuela.start(cats):
                    return "Ya estoy estudiando las referencias; le aviso al terminar (ver «En marcha»)."
                n = sum(
                    len(refs[c]["links"])
                    + sum(
                        int(x.get("ultimos") or 20)
                        for x in refs[c].get("canales") or []
                    )
                    for c in (cats or refs)
                )
                return (f"Empecé a estudiar {n} videos de referencia segundo a segundo, en segundo plano. "
                        "Cada uno tarda unos minutos; al final escribo la superskill de cada categoría.")  # fmt: skip
            st = escuela.status()
            lines = []
            if st["en_curso"]:
                lines.append(f"Estudiando ahora: {st['en_curso'].get('que', '')}")
            for k, c in st["categorias"].items():
                done = "con superskill" if c["superskill"] else "sin superskill aún"
                lines.append(
                    f"- {c['nombre']}: {c['estudiados']}/{c['videos']} estudiados, {done}."
                )
            for f in (st["ultimo"] or {}).get("fallos", [])[:6]:
                lines.append(
                    f"  No pude: {f.get('url') or f.get('categoria')}: {f['por_que']}"
                )
            return "\n".join(lines)

        return _run(self.tool_id, go)


__all__ = [
    "FilmClipsTool",
    "ThumbnailsTool",
    "TitlesTool",
    "TrendRadarTool",
    "VideoSchoolTool",
]

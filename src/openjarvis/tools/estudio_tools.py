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
                if cat and cat not in refs:
                    return f"No existe la categoría «{cat}». Para Ricks Clips use «shorts-animados»."
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
                        "Al terminar indicaré cuántos pude medir y qué perfiles se actualizaron.")  # fmt: skip
            st = escuela.status()
            lines = []
            if st["en_curso"]:
                lines.append(f"Estudiando ahora: {st['en_curso'].get('que', '')}")
            for k, c in st["categorias"].items():
                if cat and cat != k:
                    continue
                done = "con superskill" if c["superskill"] else "sin superskill aún"
                cohort = st["ultimo"].get("cohortes", {}).get(k)
                if cohort:
                    profile = "perfil actualizado" if cohort["perfil_actualizado"] else "perfil sin actualizar"
                    lines.append(
                        f"- {c['nombre']}: última tanda: {cohort['medidos']}/{cohort['solicitados']} "
                        f"a {cohort['fps']} FPS; {cohort['encontrados']} enlaces encontrados, {profile}."
                    )
                    continue
                if k == "shorts-animados":
                    lines.append(f"- {c['nombre']}: sin tanda de 20 verificada aún; {done}.")
                    continue
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


@ToolRegistry.register("recortes_video")
class ClipFinderTool(BaseTool):
    tool_id = "recortes_video"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="recortes_video",
            description=(
                "ONLY for turning a LONG video of the person (podcast, stream, class, vlog) into "
                "shorts. action='buscar' (archivo = path of the video): transcribes it and returns "
                "the best 20-60 s moments that stand alone, each with start/end, its hook line, a "
                "0-100 score and why (hook, concrete facts, open question, pace, filler words). "
                "action='cortar' (archivo, momentos = the list returned by buscar, or the numbers "
                "chosen): cuts them as 9:16 files with burned captions next to the video. Nothing "
                "is posted."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["buscar", "cortar"]},
                    "archivo": {"type": "string"},
                    "cuantos": {"type": "integer"},
                    "min_s": {"type": "number"},
                    "max_s": {"type": "number"},
                    "momentos": {"type": "array", "items": {"type": "object"}},
                    "elegidos": {"type": "array", "items": {"type": "integer"}},
                    "formato": {"type": "string", "enum": ["9:16", "1:1", "16:9"]},
                    "idioma": {"type": "string"},
                },
                "required": ["action", "archivo"],
            },
            category="media",
            timeout_seconds=1800,
        )

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.estudio import recortes

        path = str(p.get("archivo") or "")
        lang = str(p.get("idioma") or "es")

        def go() -> str:
            if p.get("action") == "cortar":
                picks = [m for m in (p.get("momentos") or []) if isinstance(m, dict)]
                if not picks:
                    found = recortes.find(
                        path, n=int(p.get("cuantos") or 5), language=lang
                    )
                    picks = found["momentos"]
                chosen = {int(n) for n in (p.get("elegidos") or [])}
                if chosen:
                    picks = [m for m in picks if int(m.get("n") or 0) in chosen]
                files = recortes.cut(
                    path, picks, aspect=str(p.get("formato") or "9:16"), language=lang
                )
                return "Recortes listos (no se publicó nada):\n" + "\n".join(
                    f"- {f}" for f in files
                )
            found = recortes.find(path, n=int(p.get("cuantos") or 5), min_s=float(p.get("min_s") or 20),
                                  max_s=float(p.get("max_s") or 60), language=lang)  # fmt: skip
            return recortes.texto(found)

        return _run(self.tool_id, go)


@ToolRegistry.register("calendario_contenido")
class ContentCalendarTool(BaseTool):
    tool_id = "calendario_contenido"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="calendario_contenido",
            description=(
                "ONLY for a content calendar: N weeks of posts about the person's topic, spread over "
                "the week, formats rotating, each with a hook judged by code (flags the weak ones). "
                "Optional real trend words. Never invents a 'best hour'. guardar=true saves an .xlsx "
                "in Documents/Sergio. Nothing is posted."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tema": {"type": "string"},
                    "semanas": {"type": "integer"},
                    "por_semana": {"type": "integer"},
                    "plataforma": {"type": "string"},
                    "con_tendencias": {"type": "boolean"},
                    "pais": {"type": "string"},
                    "guardar": {"type": "boolean"},
                },
                "required": ["tema"],
            },
            category="media",
            timeout_seconds=180,
        )

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.estudio import calendario

        def go() -> str:
            trend: list = []
            if p.get("con_tendencias"):
                from openjarvis.automatiza import tendencias

                data = tendencias.read(
                    str(p.get("pais") or "EC"), str(p.get("tema") or "")
                )
                trend = [s["tema"] for s in (data.get("senales") or [])[:20]]
            result = calendario.plan(
                str(p.get("tema") or ""),
                semanas=int(p.get("semanas") or 4),
                por_semana=int(p.get("por_semana") or 3),
                plataforma=str(p.get("plataforma") or "shorts"),
                tendencias=trend,
            )
            out = calendario.texto(result)
            if p.get("guardar"):
                out += f"\nGuardado en {calendario.save_xlsx(result)}"
            return out

        return _run(self.tool_id, go)


@ToolRegistry.register("motion_design")
class MotionDesignTool(BaseTool):
    """Fixed, inspectable Blender templates; never generated arbitrary Python."""

    tool_id = "motion_design"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Create an editable animated 2D title or 3D product reveal in Blender. "
                "Requires installed Blender. Returns a .blend and preview; does not publish."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "modo": {"type": "string", "enum": ["2d", "3d"]},
                },
                "required": ["titulo"],
            },
            category="media",
            timeout_seconds=300,
        )

    def execute(self, **p: Any) -> ToolResult:
        def go():
            import uuid
            from pathlib import Path

            from openjarvis.core.config import get_config_dir
            from openjarvis.vfx import build_scene, run

            folder = Path(get_config_dir()) / "motion" / uuid.uuid4().hex
            folder.mkdir(parents=True, exist_ok=True)
            blend, preview = folder / "motion.blend", folder / "preview.png"
            script = build_scene(
                [
                    (
                        "motion_graphics",
                        {
                            "title": str(p.get("titulo") or ""),
                            "mode": p.get("modo", "3d"),
                        },
                    )
                ],
                save=str(blend),
                preview=str(preview),
                frames=(1, 36, 72),
            )
            result = run(script, timeout=240)
            previews = [Path(f) for f in result.info.get("previews", [])]
            if (
                not result.ok
                or not blend.is_file()
                or not previews
                or not all(f.is_file() for f in previews)
            ):
                raise RuntimeError(
                    "No pude verificar el render. Instale Blender y revise su configuración."
                )
            return (
                f"Animación editable (3 s, 24 fps): {blend}\nVistas previas: "
                + ", ".join(map(str, previews))
            )

        return _run(self.tool_id, go)

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
                "with the cloud 3D services the professionals use (Tripo, Meshy, "
                "Rodin/Hyper3D, fal.ai Hunyuan3D/TRELLIS), 2-10 minutes; "
                "'comparar': true asks each service for its own version (spends "
                "each one's credits; only when asked). Put the returned link in "
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
                    "comparar": {
                        "type": "boolean",
                        "description": "nube: one version from every 3D service",
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
                    meta = nube3d.generate(
                        str(params.get("request") or ""),
                        picture,
                        compare=bool(params.get("comparar")),
                    )
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
        others = "".join(
            f"\n- Versión de {v['fuente']}: {despiece.view(v['name'])}"
            for v in (meta.get("versiones") or [])[1:]
        )
        return self._ok(
            f"Modelo «{meta['titulo']}» listo{parts}; aparece en el chat con este enlace: "
            f"{despiece.view(meta['name'])}.{credit}{others}"
        )

    def _ok(self, text: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=text, success=True)


@ToolRegistry.register("juego_unreal")
class UnrealGameTool(BaseTool):
    """A game in Unreal Engine 5 from a description (``creator/unreal.py``)."""

    tool_id = "juego_unreal"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="juego_unreal",
            description=(
                "Create a video game project in Unreal Engine 5 from 'idea' (and 'nombre', "
                "'genero': tercera persona | primera persona | plataformas | carreras | puzle | "
                "mundo abierto). It places 3D models in the first level: 'modelos' (names already "
                "made with modelo_por_piezas) and 'crear_modelos' (descriptions made now by the "
                "cloud 3D services: Tripo, Meshy, Rodin, fal). Character motion: 'movimientos' "
                "(sentences, e.g. 'salta un muro y aterriza rodando') become body animations with "
                "Kimodo (FBX in Content/Animaciones); 'locomocion': true adds MotionBricks' "
                "real-time walk/run/crouch model. Faces from voice: Audio2Face in Unreal. Opens "
                "the project in Unreal on the owner's PC."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "idea": {"type": "string"},
                    "nombre": {"type": "string"},
                    "genero": {"type": "string"},
                    "modelos": {"type": "array", "items": {"type": "string"}},
                    "crear_modelos": {"type": "array", "items": {"type": "string"}},
                    "movimientos": {"type": "array", "items": {"type": "string"}},
                    "locomocion": {"type": "boolean"},
                },
                "required": ["idea"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.creator import despiece, programs, unreal
        from openjarvis.creator.llm import CreatorError

        placed, files = [], {}
        for i, name in enumerate(params.get("modelos") or []):
            try:
                meta = despiece.meta(str(name))
                rel = next(
                    (
                        f
                        for f in (meta.get("files") or [meta.get("file", "")])
                        if str(f).endswith(".glb")
                    ),
                    "",
                )
                path = despiece.file_path(str(name), rel or "modelo.glb")
            except CreatorError:
                continue
            fname = f"{despiece.slug(str(name))}.glb"
            files[fname] = path.read_bytes()
            placed.append({"file": fname, "x": 400 * (i + 1), "y": 0})
        notes: list = []
        made_now = self._cloud_models(
            params.get("crear_modelos") or [], files, placed, notes
        )
        extra = self._motion(params, notes)
        try:
            data = unreal.build(
                str(params.get("nombre") or ""),
                str(params.get("idea") or ""),
                genre=str(params.get("genero") or ""),
                models=placed,
                model_files=files,
                extra_files=extra,
                notes=notes,
            )
        except unreal.UnrealError as exc:
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)
        key = unreal.slug(str(params.get("nombre") or params.get("idea") or ""))
        try:
            said = programs.open_in_windows("unreal", f"{key}.zip", data)
        except Exception as exc:  # noqa: BLE001 — no desktop: tell him where it is
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Proyecto «{key}» creado, pero no pude abrirlo en su PC: {exc}",
                success=False,
            )
        what = f" con {len(placed)} modelos en el nivel" if placed else ""
        if made_now:
            what += f" ({made_now} hechos ahora en la nube)"
        anims = sum(
            1 for k in extra if k.startswith("Animaciones/") and k.endswith(".fbx")
        )
        if anims:
            what += f", {anims} animaciones"
        tail = (" " + " ".join(notes)) if notes else ""
        return ToolResult(
            tool_name=self.tool_id,
            content=f"Juego «{key}» creado{what}. {said}{tail}",
            success=True,
        )

    @staticmethod
    def _cloud_models(wanted: list, files: dict, placed: list, notes: list) -> int:
        """Each description, made now by the first cloud 3D service with a key."""
        from openjarvis.creator import despiece, nube3d

        made = 0
        for text in [str(w).strip() for w in wanted if str(w).strip()][:8]:
            try:
                meta = nube3d.generate(text)
            except nube3d.Nube3DError as exc:
                notes.append(f"«{text}» no se pudo modelar: {exc}")
                continue
            name = str(meta.get("name") or "")
            rel = next(
                (
                    f
                    for f in (meta.get("files") or [meta.get("file", "")])
                    if str(f).endswith(".glb")
                ),
                "",
            )
            try:
                path = despiece.file_path(name, rel or "modelo.glb")
            except Exception:  # noqa: BLE001
                continue
            fname = f"{despiece.slug(name)}.glb"
            files[fname] = path.read_bytes()
            placed.append({"file": fname, "x": 400 * (len(placed) + 1), "y": 0})
            made += 1
        return made

    @staticmethod
    def _motion(params: dict, notes: list) -> dict:
        """Kimodo animations and MotionBricks' model, when installed."""
        import tempfile
        from pathlib import Path

        from openjarvis.creator import movimiento

        extra: dict = {}
        wanted = [
            str(m).strip() for m in params.get("movimientos") or [] if str(m).strip()
        ][:12]
        if not wanted and not params.get("locomocion"):
            return extra
        with tempfile.TemporaryDirectory() as tmp:
            for text in wanted:
                try:
                    res = movimiento.texto_a_movimiento(
                        text, out_dir=Path(tmp) / "anim"
                    )
                except movimiento.MovimientoError as exc:
                    notes.append(str(exc))
                    break  # the same reason for every other one
                best = res.get("fbx") or res.get("bvh") or (res.get("npz") or [""])[0]
                if best:
                    extra[f"Animaciones/{Path(best).name}"] = Path(best).read_bytes()
                if res.get("aviso"):
                    notes.append(res["aviso"])
            if params.get("locomocion"):
                try:
                    res = movimiento.motionbricks_onnx(Path(tmp) / "mb")
                    for f in res["onnx"]:
                        extra[f"MotionBricks/{Path(f).name}"] = Path(f).read_bytes()
                    notes.append(
                        "MotionBricks: modelo de locomoción (caminar, correr, lateral, agachado) "
                        "en Content/MotionBricks."
                    )
                except movimiento.MovimientoError as exc:
                    notes.append(str(exc))
        if extra:
            notes.append(
                "Las animaciones usan el esqueleto SOMA de NVIDIA: en Unreal, el IK Retargeter las pasa a su personaje."
            )
        return extra


@ToolRegistry.register("cine_ia")
class CinematicAIVideoTool(BaseTool):
    """Cinematic AI short films, shot by shot (``creator/cine_ia.py``)."""

    tool_id = "cine_ia"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="cine_ia",
            description=(
                "Cinematic AI video for creators, directors and animators: a short film "
                "made shot by shot with real camera moves (dolly, crane, orbit, FPV, "
                "whip pan…), made for the owner's audience, platform and brand. It uses "
                "the owner's Higgsfield account (its marketplace of presets and video "
                "models, with his credits) when that connector is connected, otherwise "
                "Sergio's own AI video (Veo or fal.ai). action='plan' writes the shot "
                "list and shows what it costs (spends nothing); 'crear' makes it (several "
                "minutes; spends credits); 'catalogo' searches the Higgsfield marketplace "
                "('idea' = what to look for). Show the plan first, then make it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["plan", "crear", "catalogo"]},
                    "idea": {"type": "string"},
                    "audiencia": {"type": "string"},
                    "plataforma": {
                        "type": "string",
                        "description": "reels, tiktok, shorts, youtube largo, cuadrado",
                    },
                    "marca": {
                        "type": "string",
                        "description": "brand or personal style",
                    },
                    "tomas": {"type": "integer", "minimum": 1, "maximum": 8},
                },
                "required": ["action"],
            },
            category="creative",
            timeout_seconds=1800,
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.creator import cine_ia

        action = str(params.get("action") or "plan")
        idea = str(params.get("idea") or "")
        try:
            if action == "catalogo":
                items = cine_ia.catalog(idea)
                if not items:
                    return self._say("No encontré presets con eso en Higgsfield.")
                lines = [
                    f"- {i['nombre'] or i['id']} ({i['tipo'] or 'preset'})"
                    for i in items
                ]
                return self._say("Del mercado de Higgsfield:\n" + "\n".join(lines))
            film = cine_ia.brief(
                idea,
                audience=str(params.get("audiencia") or ""),
                platform=str(params.get("plataforma") or "reels"),
                brand=str(params.get("marca") or ""),
                shots=int(params.get("tomas") or 4),
            )
            shots = "\n".join(
                f"{n}. [{s.beat}] {s.action} — cámara {s.camera}, {s.lens}, {s.seconds} s"
                for n, s in enumerate(film.shots, 1)
            )
            if action == "plan":
                try:
                    price = cine_ia.cost(film)
                except Exception as exc:  # noqa: BLE001 — the plan still helps
                    price = f"No pude consultar el precio: {str(exc)[:120]}"
                return self._say(
                    f"Plan ({film.aspect}, {film.look or 'look cinematográfico'}):\n"
                    f"{shots}\n{price}\nSi le parece, lo hago con action='crear'."
                )
            film = cine_ia.render(film)
        except cine_ia.CineError as exc:
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)
        except Exception as exc:  # noqa: BLE001 — the connector, the internet
            return ToolResult(
                tool_name=self.tool_id,
                content=f"No pude hacer el video: {str(exc)[:200]}",
                success=False,
            )
        return self._say(
            f"Video listo con {film.engine}: {film.output} ({len(film.files)} de "
            f"{len(film.shots)} tomas).\n{shots}\nNo lo publiqué."
        )

    def _say(self, text: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=text, success=True)


@ToolRegistry.register("movimiento_personaje")
class CharacterMotionTool(BaseTool):
    """Character motion for games (``creator/movimiento.py``)."""

    tool_id = "movimiento_personaje"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="movimiento_personaje",
            description=(
                "Character motion for games with NVIDIA's open models on the owner's PC (needs an "
                "NVIDIA GPU). action 'texto' ('texto', 'segundos'): Kimodo turns a sentence into a "
                "body animation (FBX/BVH for Unreal). 'cara' ('audio'): Audio2Face moves the face "
                "from a voice line. 'vista': opens MotionBricks' real-time locomotion preview. "
                "'estado', 'instalar' (several GB, in the background)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["texto", "cara", "vista", "estado", "instalar"],
                    },
                    "texto": {"type": "string"},
                    "segundos": {"type": "number"},
                    "audio": {"type": "string"},
                },
                "required": ["action"],
            },
            timeout_seconds=1800,
        )

    def execute(self, **params: Any) -> ToolResult:
        from pathlib import Path

        from openjarvis.creator import movimiento, studio

        action = str(params.get("action") or "estado")
        try:
            if action == "instalar":
                text = movimiento.instalar()
            elif action == "vista":
                text = movimiento.motionbricks_vista()
            elif action == "texto":
                out = studio.projects_root() / "animaciones"
                res = movimiento.texto_a_movimiento(
                    str(params.get("texto") or ""),
                    float(params.get("segundos") or 5),
                    out_dir=out,
                )
                made = res.get("fbx") or res.get("bvh") or (res.get("npz") or [""])[0]
                text = f"Animación lista con Kimodo: {made}." + (
                    f" {res['aviso']}" if res.get("aviso") else ""
                )
            elif action == "cara":
                out = studio.projects_root() / "animaciones" / "caras"
                res = movimiento.cara_desde_audio(
                    Path(str(params.get("audio") or "")), out
                )
                text = (
                    f"Expresiones de la cara listas (Audio2Face): {res['blendshapes']}."
                )
            else:
                st = movimiento.estado()
                g = st["gpu"]
                gpu = (
                    f"{g['nombre']} ({g['vram_gb']} GB)" if g else "sin tarjeta NVIDIA"
                )
                have = [n for n in ("kimodo", "motionbricks", "audio2face") if st[n]]
                text = (
                    f"Tarjeta: {gpu}. Instalados: {', '.join(have) or 'ninguno'}."
                    + ("" if have else " Diga «instala los movimientos» para ponerlos.")
                )
        except movimiento.MovimientoError as exc:
            return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)
        return ToolResult(tool_name=self.tool_id, content=text, success=True)


__all__ = [
    "AnatomyFigureTool",
    "CharacterMotionTool",
    "CinematicAIVideoTool",
    "TakeApartModelTool",
    "UnrealGameTool",
    "view",
]

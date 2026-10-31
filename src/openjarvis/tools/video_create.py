"""«Haz un video sobre…»: a short video from an idea, made on this computer.

There is no video model on the owner's key (no Veo), and the editors
(``video_edit``, ``video_pro``) need clips he already has. This one starts
from nothing:

1. Gemini writes the script: a few scenes, each with one spoken sentence and
   a picture to show.
2. Each picture comes from ``studio.generate_image`` (Gemini, then the other
   services).
3. Sergio reads the script in his own voice (``gemini_voice``); without it
   the video still has the sentences on screen.
4. ffmpeg (``imageio-ffmpeg``) puts it together: a slow zoom on each
   picture, the sentence as a caption, the voice under it. The result opens
   in the chat to review. It is never published from here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

SCRIPT_PROMPT = """Write the script of a short video (Spanish) about: «{topic}».
{n} scenes. For each: "say", one sentence the narrator says (8-22 words, \
natural spoken Spanish, no emojis), and "picture", a detailed description in \
English of a single striking image that literally and coherently shows the exact \
subject and action spoken in "say" at that moment (1:1 visual-narration coherence, \
no text in the image, no logos, no real people's faces). Also a short "title" (max 6 words).
Answer ONLY JSON: {{"title": "...", "scenes": [{{"say": "...", "picture": "..."}}]}}"""

SIZES = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1080, 1080)}
FPS = 25

RESULTA_QUE_SCRIPT_PROMPT = """Write a viral, high-retention short vertical video script (Spanish, 9:16) \
in the ultra-engaging style of @resultaaquee (curiosities, hidden everyday science and technology, but with 3D schematic dissection).
Topic: «{topic}».
{n} scenes. Follow this exact neuro-retention formula:
1. Scene 1 (Hook, 0-2.5s): Start with a pattern-interrupting paradox or question that breaks the scroll (e.g. "¿Por qué la pantalla de tu móvil nota tu dedo pero un bolígrafo plástico no hace nada?").
2. Scene 2 (Common Myth): Debunk the intuitive assumption that most people wrongly believe.
3. Scene 3 (The Reveal): Deliver the core insight starting with or emphasizing "Resulta que..." with an ultra-clear everyday analogy.
4. Scene 4+ (3D Cutaway / X-Ray Dissection): Explain the invisible physics, engineering, or biological mechanism step-by-step. The "picture" MUST be a stylized 3D render, isometric cutaway cross-section, or X-ray schematic with glowing neon accents on a sleek dark studio background.
5. Final Scene (Dopamine Wrap-up & Seamless Loop): End with a surprising twist or practical takeaway, and craft the final spoken sentence so it loops seamlessly back into the very first hook sentence when repeated!

For each scene:
- "say": one punchy sentence in spoken Spanish (8-20 words, confident, crisp, no emojis).
- "picture": detailed prompt in English for 3D schematic/cross-section image generation with neon callouts on dark background (1:1 visual coherence with "say", no text inside image).

Answer ONLY JSON:
{{"title": "...", "scenes": [{{"say": "...", "picture": "..."}}]}}"""



def ffmpeg_exe() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return ""


def _font() -> str:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        if Path(path).is_file():
            return path
    return ""


def plan(topic: str, scenes: int, ask: Any = None, style: str = "") -> dict[str, Any]:
    """The script: {"title", "scenes": [{"say", "picture"}]}."""
    from openjarvis.creator.llm import ask as gemini_ask

    def check(text: str) -> dict[str, Any]:
        data = json.loads(text)
        items = [
            {"say": str(s["say"]).strip(), "picture": str(s["picture"]).strip()}
            for s in data["scenes"]
            if str(s.get("say", "")).strip() and str(s.get("picture", "")).strip()
        ]
        if len(items) < 2:
            raise ValueError("pocas escenas")
        return {"title": str(data.get("title") or topic)[:60], "scenes": items[:10]}

    is_rq = style in ("resultaaquee", "resulta_que", "resultaque", "resulta que") or any(
        w in topic.lower() for w in ("resultaaquee", "resulta que", "curiosidad cotidiana", "por que la pantalla", "por que el ", "por que los ")
    )
    prompt_tpl = RESULTA_QUE_SCRIPT_PROMPT if is_rq else SCRIPT_PROMPT
    raw = (ask or gemini_ask)(
        prompt_tpl.format(topic=topic, n=scenes), json_mode=True, check=check
    )
    return check(raw)


def _wav_seconds(data: bytes) -> float:
    import io

    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / float(w.getframerate() or 1)


def _caption(text: str, width: int) -> str:
    """The sentence broken into lines that fit the frame."""
    per_line = max(18, width // 30)
    words, lines, line = text.split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > per_line:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return "\n".join(lines[:4])



def build_social_pack(topic: str, title: str, scenes: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a viral social publication pack for Instagram Reels, TikTok and Shorts."""
    hook = scenes[0]["say"] if scenes else topic
    hashtags = [
        "#curiosidades",
        "#resultaque",
        "#ciencia",
        "#sabiasque",
        "#datoscuriosos",
        "#tecnologia",
        "#aprendeconmigo",
        "#reelsviral",
        "#tiktokviral",
        "#shorts",
    ]
    loop_hint = scenes[-1]["say"] if scenes else ""
    clean_topic = topic.replace("Por qué", "").replace("por que", "").replace("¿", "").replace("?", "").strip()
    return {
        "titulo_viral": f"¿Por qué {clean_topic}?"[:50],
        "copy_publicacion": (
            f"🤯 {hook}\n\n"
            f"¿Alguna vez te lo habías preguntado? Resulta que la explicación real te va a volar la cabeza. "
            f"Mira el video hasta el final para ver la animación 3D del interior. 👇\n\n"
            f"{' '.join(hashtags)}"
        ),
        "comentario_fijado": (
            "💬 ¿Tú ya sabías esto o también creías que era por otra razón? "
            "Déjamelo en los comentarios. 👇"
        ),
        "bucle_infinito": f"La última frase ('{loop_hint[:35]}...') conecta gramaticalmente con el gancho inicial para retención >100%.",
        "hashtags": hashtags,
    }


def render(
    pictures: list[bytes],
    sentences: list[str],
    durations: list[float],
    out: Path,
    *,
    aspect: str = "16:9",
    voice: bytes = b"",
    ffmpeg: str = "",
    accent: str = "",
) -> Path:
    """Stills + captions (+ voice) -> an mp4 with a slow zoom on each picture.

    Captions move (video_essay/captions.py: a few words at a time, the word
    being said lit up); an ffmpeg without libass gets the old boxed lines."""
    try:
        return _render(pictures, sentences, durations, out, aspect=aspect, voice=voice,
                       ffmpeg=ffmpeg, animated=True, accent=accent)  # fmt: skip
    except subprocess.CalledProcessError:
        return _render(pictures, sentences, durations, out, aspect=aspect, voice=voice,
                       ffmpeg=ffmpeg, animated=False, accent=accent)  # fmt: skip


def _render(
    pictures: list[bytes],
    sentences: list[str],
    durations: list[float],
    out: Path,
    *,
    aspect: str,
    voice: bytes,
    ffmpeg: str,
    animated: bool,
    accent: str = "",
) -> Path:
    exe = ffmpeg or ffmpeg_exe()
    if not exe:
        raise RuntimeError("falta ffmpeg (se instala con la actualización de Sergio)")
    width, height = SIZES.get(aspect, SIZES["16:9"])
    font = "" if animated else _font()
    with tempfile.TemporaryDirectory(prefix="sergio-video-") as tmp:
        work = Path(tmp)
        parts = []
        for i, (pic, text, seconds) in enumerate(zip(pictures, sentences, durations)):
            src = work / f"p{i}.img"
            src.write_bytes(pic)
            frames = max(FPS, int(seconds * FPS))
            zoom = (
                f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
                f"crop={width * 2}:{height * 2},"
                f"zoompan=z='min(zoom+0.0009,1.12)':d={frames}"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={FPS}"
            )
            if font and text:
                caption = work / f"c{i}.txt"
                caption.write_text(_caption(text, width), encoding="utf-8")
                zoom += (
                    f",drawtext=fontfile='{font}':textfile='{caption}':fontcolor=white"
                    f":fontsize={max(26, width // 34)}:line_spacing=8"
                    ":box=1:boxcolor=black@0.45:boxborderw=18"
                    ":x=(w-text_w)/2:y=h-text_h-h/10"
                )
            part = work / f"s{i}.mp4"
            subprocess.run(
                [exe, "-y", "-loglevel", "error", "-loop", "1", "-i", str(src),
                 "-vf", zoom, "-frames:v", str(frames), "-pix_fmt", "yuv420p",
                 "-c:v", "libx264", "-preset", "veryfast", str(part)],
                check=True, capture_output=True, timeout=600,
            )  # fmt: skip
            parts.append(part)
        listing = work / "list.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [exe, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
               "-i", str(listing)]  # fmt: skip
        if voice:
            narration = work / "voz.wav"
            narration.write_bytes(voice)
            cmd += ["-i", str(narration), "-c:a", "aac", "-b:a", "160k", "-shortest"]
        if animated and any(sentences):
            from openjarvis.video_essay.captions import ass_document, filter_for

            subs = work / "subtitulos.ass"
            subs_kwargs = {"accent": accent} if accent else {}
            subs.write_text(
                ass_document(sentences, durations, width, height, **subs_kwargs), encoding="utf-8"
            )
            cmd += ["-vf", filter_for(subs), "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-pix_fmt", "yuv420p"]  # fmt: skip
        else:
            cmd += ["-c:v", "copy"]
        cmd += ["-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    return out


@ToolRegistry.register("video_create")
class VideoCreateTool(BaseTool):
    """A short narrated video from an idea, shown in the chat."""

    tool_id = "video_create"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="video_create",
            description=(
                "Make a short video from an idea, with nothing else needed: "
                "«haz un video sobre la contaminación». Sergio writes the script, "
                "makes a picture for each scene, narrates it in his voice and "
                "shows the video in the chat to review. 'seconds' 15-90 (default "
                "30); 'aspect' 16:9, 9:16 (Shorts, Reels, TikTok) or 1:1. To edit "
                "the user's own clips use video_pro instead. Never publish it "
                "without the user's OK."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "What it is about."},
                    "seconds": {"type": "number"},
                    "aspect": {"type": "string", "enum": ["16:9", "9:16", "1:1"]},
                    "style": {
                        "type": "string",
                        "description": "Editing/narrative style: 'resultaaquee' (or 'resulta_que') for viral curiosity 3D cutaway reels in 9:16, 'standard'.",
                    },
                    "voice": {
                        "type": "boolean",
                        "description": "Narrate (default yes).",
                    },
                },
                "required": ["topic"],
            },
            category="media",
            timeout_seconds=1800,
            required_capabilities=["network:fetch"],
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.creator import studio
        from openjarvis.creator.llm import CreatorError

        topic = " ".join(str(params.get("topic") or "").split())[:400]
        if len(topic) < 3:
            return self._fail("Dígame de qué trata el video.")
        raw_style = str(params.get("style") or params.get("platform") or "").lower().strip()
        is_rq = raw_style in ("resultaaquee", "resulta_que", "resultaque", "resulta que") or any(
            w in topic.lower() for w in ("resultaaquee", "resulta que", "curiosidad cotidiana", "por que la pantalla")
        )
        chosen_style = "resultaaquee" if is_rq else raw_style
        seconds = min(90.0, max(15.0, float(params.get("seconds") or (40 if is_rq else 30))))
        aspect = str(params.get("aspect") or ("9:16" if is_rq else "16:9"))
        if aspect not in SIZES:
            aspect = "9:16" if is_rq else "16:9"
        if not ffmpeg_exe():
            return self._fail(
                "Falta el programa de video (ffmpeg). Actualice Sergio y vuelva a pedirlo."
            )
        try:
            script = plan(topic, max(3, min(8, round(seconds / 6))), style=chosen_style)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"No pude escribir el guion: {str(exc)[:200]}")
        scenes = script["scenes"]
        pictures = []
        for scene in scenes:
            try:
                pictures.append(studio.generate_image(scene["picture"]))
            except CreatorError as exc:
                return self._fail(f"No pude hacer las imágenes del video. {exc}")
        voice = b""
        sentences = [s["say"] for s in scenes]
        if params.get("voice", True):
            try:
                from openjarvis.speech import gemini_voice

                voice = gemini_voice.speak(
                    " ".join(sentences), gemini_voice.sergio_voice("")
                )
            except Exception:  # noqa: BLE001 — captions alone still tell it
                voice = b""
        if voice:
            import re as _re

            total = max(0.5, _wav_seconds(voice))
            weights = [
                max(
                    1,
                    sum(len(_re.sub(r"\W", "", w)) + 2 for w in s.split()),
                )
                for s in sentences
            ]
            durations = [total * w / sum(weights) for w in weights]
        else:
            durations = [max(3.0, seconds / len(scenes))] * len(scenes)
        name = studio.media_name("video", ".mp4")
        out = studio.projects_root() / "videos" / name
        try:
            render(pictures, sentences, durations, out, aspect=aspect, voice=voice, accent="&H00A3FF00" if is_rq else "")
        except Exception as exc:  # noqa: BLE001
            detail = getattr(exc, "stderr", b"") or b""
            text = (
                detail.decode("utf-8", "replace")[-300:] if detail else str(exc)[:300]
            )
            return self._fail(f"No pude montar el video: {text}")
        url = f"/v1/creator/media/{name}"
        note = (
            ""
            if voice
            else " (sin voz: hoy no hubo cuota de voz; lleva el texto en pantalla)"
        )
        social_md = ""
        social_pack = {}
        if is_rq:
            social_pack = build_social_pack(topic, script["title"], scenes)
            try:
                pack_path = out.parent / f"{out.stem}_pack.json"
                pack_path.write_text(json.dumps(social_pack, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            social_md = (
                f"\n\n📱 **Ficha de Publicación para Redes (Reels / TikTok / Shorts):**\n"
                f"- **Título sugerido:** «{social_pack['titulo_viral']}»\n"
                f"- **Comentario fijado (Engagement):** «{social_pack['comentario_fijado']}»\n"
                f"- **Bucle infinito:** {social_pack['bucle_infinito']}\n"
                f"- **Hashtags:** `{' '.join(social_pack['hashtags'][:5])}`"
            )

        return ToolResult(
            tool_name=self.tool_id,
            content=(
                f"Video listo: «{script['title']}», {len(scenes)} escenas{note}. "
                f"Guardado en {out}.\n\n![{script['title']}]({url})"
                + social_md
            ),
            metadata={"url": url, "path": str(out), "title": script["title"], "social_pack": social_pack},
        )

    def _fail(self, text: str) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=text, success=False)


__all__ = ["VideoCreateTool", "ffmpeg_exe", "plan", "render"]

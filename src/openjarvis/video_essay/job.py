"""A video essay as a long job: it takes hours, survives a restart and says
where it is.

Each job lives in ``~/.openjarvis/video_jobs/<id>/``. Every stage saves what
it made before the next one starts, so a job that stopped (the PC slept, the
server restarted) picks up at the stage it was in, without paying again for
what was done:

1. ``estudio`` — the reference is studied shot by shot (only when given);
2. ``guion`` — the script in the reference's structure (or the owner's own);
3. ``voz`` — Sergio narrates it;
4. ``tiempos`` — when each word is said;
5. ``plan`` — the shots, built on the words;
6. ``imagenes`` — what each shot shows (his clips, free stock, pictures);
7. ``revision`` — passes of an editor looking at the cut and fixing it;
8. ``sonido`` — effects, music and the mix;
9. ``render`` — the final video, in the chat's folder;
10. ``listo`` — Hous posts it in his chat. It is never published.
"""

from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

STAGES = (
    "estudio",
    "guion",
    "voz",
    "tiempos",
    "plan",
    "imagenes",
    "revision",
    "sonido",
    "render",
    "acabado",
    "listo",
)
LABELS = {
    "estudio": "Estudiando la referencia toma por toma",
    "guion": "El director escribe el tratamiento",
    "voz": "Narrando con la voz de Sergio",
    "tiempos": "Midiendo cuándo se dice cada palabra",
    "plan": "Planeando las tomas",
    "imagenes": "Buscando y creando las imágenes",
    "revision": "El editor y el director revisan el montaje",
    "sonido": "Mezclando efectos y música",
    "render": "Renderizando el video final",
    "acabado": "Color, máster y paquete para publicar",
    "listo": "Listo",
}

_running: Dict[str, threading.Thread] = {}
_cancel: Dict[str, threading.Event] = {}
_lock = threading.Lock()


class Cancelled(Exception):
    pass


def jobs_dir() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "video_jobs"


class Job:
    """One essay on disk: its order, its state and what each stage made."""

    def __init__(self, folder: Path) -> None:
        self.dir = folder
        self.id = folder.name
        self._last_write = 0.0

    # -- state ---------------------------------------------------------------------
    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    def state(self) -> Dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def update(self, **fields: Any) -> Dict[str, Any]:
        data = {**self.state(), **fields, "updated": time.time()}
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self.state_path)
        self._last_write = time.time()
        return data

    def progress(self, stage: str, fraction: float, note: str = "") -> None:
        if time.time() - self._last_write < 2 and fraction < 1:
            return
        self.update(
            stage=stage, stage_progress=round(min(1.0, fraction), 3), note=note[:200]
        )

    def log(self, text: str) -> None:
        with (self.dir / "registro.txt").open("a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + text + "\n")

    def done(self, stage: str) -> bool:
        return stage in (self.state().get("done") or [])

    def finish(self, stage: str) -> None:
        done = list(self.state().get("done") or [])
        if stage not in done:
            done.append(stage)
        self.update(done=done, stage_progress=1.0)
        self.log(f"terminado: {stage}")

    # -- files ---------------------------------------------------------------------
    def read(self, name: str) -> Any:
        return json.loads((self.dir / name).read_text("utf-8"))

    def write(self, name: str, data: Any) -> None:
        (self.dir / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), "utf-8"
        )


def create(params: Dict[str, Any], root: Optional[Path] = None) -> Job:
    root = root or jobs_dir()
    folder = root / f"ensayo-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    folder.mkdir(parents=True, exist_ok=True)
    job = Job(folder)
    job.update(
        id=job.id,
        params=params,
        status="en curso",
        stage=STAGES[0],
        stage_progress=0.0,
        done=[],
        created=time.time(),
        passes=[],
    )
    return job


class Deps:
    """What a job calls out to (real services by default; fakes in tests)."""

    def __init__(self, **over: Any) -> None:
        self.ask: Optional[Callable[..., str]] = over.get("ask")  # the editor (text)
        self.direct: Optional[Callable[..., str]] = over.get("direct") or over.get(
            "ask"
        )  # the director
        self.review: Optional[Callable[..., str]] = over.get(
            "review"
        )  # the editor's eyes
        self.direct_review: Optional[Callable[..., str]] = over.get(
            "direct_review"
        ) or over.get("review")
        self.choose: Optional[Callable[..., str]] = over.get("choose") or over.get(
            "review"
        )
        self.speak: Optional[Callable[[str], bytes]] = over.get("speak")
        self.recognise: Optional[Callable[[bytes, str], list]] = over.get("recognise")
        self.make_image: Optional[Callable[[str], bytes]] = over.get("make_image")
        self.watcher: Optional[Callable[[str], Dict[str, Any]]] = over.get("watcher")
        self.stock: bool = over.get("stock", True)  # False: no internet searches at all
        self.searches: Optional[Dict[str, Callable[..., list]]] = over.get("searches")
        self.fetch: Optional[Callable[..., Optional[str]]] = over.get("fetch")
        self.ai_provider: Optional[Callable[..., str]] = over.get("ai_provider")
        self.blender: Optional[Callable[..., str]] = over.get("blender")
        self.notify: Optional[Callable[[str, Dict[str, Any]], None]] = over.get(
            "notify"
        )
        # music from the internet (music.py): searches, a named song, the download
        self.music_searches: Optional[Dict[str, Callable[..., list]]] = over.get(
            "music_searches"
        )
        self.song: Optional[Callable[..., list]] = over.get("song")
        self.music_fetch: Optional[Callable[..., Optional[str]]] = over.get(
            "music_fetch"
        )
        self.videos: Optional[Path] = over.get("videos")
        self.styles: Optional[Path] = over.get("styles")


def _counted(
    fn: Optional[Callable[..., str]], budget: Any, save: Callable[[], None]
) -> Optional[Callable[..., str]]:
    """A test or injected model call that still counts against the budget."""
    if fn is None:
        return None

    def call(*a: Any, **kw: Any) -> str:
        budget.spend("llm")
        save()
        return fn(*a, **kw)

    return call


def _specialist(job: Job, style_key: str, brief: str) -> str:
    """The film or creator specialist's advice for this video (its own fly
    brain); remembered so it can learn from how the video turned out."""
    if not brief.strip():
        return ""
    try:
        from openjarvis.video_essay import specialists

        kind = specialists.which(style_key, brief)
        advice = specialists.advise(kind, brief)
    except Exception as exc:  # noqa: BLE001 — a video never fails for its advisers
        job.log(f"sin especialista: {exc}")
        return ""
    job.update(
        specialist={
            "kind": kind,
            "brief": brief[:500],
            "techniques": [a[0] for a in advice],
        }
    )
    job.log(f"especialista {kind}: {', '.join(a[0] for a in advice)}")
    return specialists.prompt_block(advice, kind)


def _specialist_learns(state: Dict[str, Any]) -> None:
    """Its dopamine: the final review's score on the techniques it advised."""
    sp = state.get("specialist") or {}
    notes = [p for p in state.get("passes") or [] if p.get("score") is not None]
    if not sp.get("techniques") or not notes:
        return
    try:
        from openjarvis.video_essay import specialists

        specialists.learn_from_video(
            sp["kind"], sp.get("brief", ""), sp["techniques"], notes[-1]["score"]
        )
    except Exception:  # noqa: BLE001 — learning is a bonus, never a failure
        pass


def run(job: Job, deps: Optional[Deps] = None) -> Dict[str, Any]:
    """Do (or finish) every stage of *job*; returns its final state."""
    import numpy as np

    from openjarvis.video_essay import (
        assets,
        audio,
        director,
        films,
        finish,
        genres,
        render,
        review,
        script,
        style,
    )
    from openjarvis.video_essay import modes as M
    from openjarvis.video_essay import plan as P
    from openjarvis.video_essay.media import Filler

    deps = deps or Deps()
    st = job.state()
    params = st.get("params") or {}
    mode = M.get(str(params.get("mode") or "basic"))
    budget = M.Budget.from_dict(
        st.get("budget") or {}, mode, float(params.get("seconds") or 60)
    )
    stop = _cancel.setdefault(job.id, threading.Event())
    job.update(
        mode=mode.key,
        budget=budget.to_dict(),
        attempts=int(st.get("attempts") or 0) + 1,
    )

    def save() -> None:
        job.update(budget=budget.to_dict())

    strong = mode.director_strong
    direct = _counted(deps.direct, budget, save) or director.asker(strong, budget)
    edit = _counted(deps.ask, budget, save) or director.asker(
        False, budget, max_tokens=60000
    )
    look_edit = _counted(deps.review, budget, save) or director.vision_asker(
        False, budget
    )
    look_direct = _counted(deps.direct_review, budget, save) or director.vision_asker(
        strong, budget
    )
    look_choose = deps.choose or director.vision_asker(
        False, None
    )  # the filler counts these itself

    def stage(name: str) -> bool:
        if stop.is_set():
            raise Cancelled()
        if job.done(name):
            return False
        job.update(stage=name, stage_progress=0.0, note="", budget=budget.to_dict())
        job.log(f"empieza: {name}")
        return True

    try:
        # 1. the reference (or the style asked for)
        if stage("estudio"):
            ref = str(params.get("reference") or "").strip()
            if ref:
                budget.spend("llm")
                profile = style.learn(
                    ref,
                    str(params.get("style_name") or ""),
                    folder=deps.styles,
                    watcher=deps.watcher,
                )
                job.update(style_key=profile["key"], style_fixed=True)
            elif params.get("style"):
                job.update(
                    style_key=style.load(str(params["style"]), deps.styles)["key"],
                    style_fixed=True,
                )
            job.finish("estudio")

        # 2. the director's treatment (or the owner's own script)
        if stage("guion"):
            fixed = (
                job.state().get("style_key", "")
                if job.state().get("style_fixed")
                else ""
            )
            if params.get("script"):
                sc = script.from_text(
                    str(params["script"]), str(params.get("title") or "")
                )
                sc.update(
                    narration="voice",
                    style=fixed or style.DEFAULT,
                    characters=[],
                    sources=[],
                )
            else:
                # The genre the brief asks for (a short film, animation, a
                # heavy retention edit…) picks the style unless one is fixed.
                brief0 = str(params.get("prompt") or params.get("topic") or "")
                genre = genres.for_style(fixed) if fixed else genres.detect(brief0)
                if genre and not fixed:
                    wanted = genres.GENRES[genre].style
                    if any(s["key"] == wanted for s in style.available(deps.styles)):
                        fixed = wanted
                job.update(genre=genre)
                keys = [s["key"] for s in style.available(deps.styles)]
                profiles = [style.load(k, deps.styles) for k in dict.fromkeys(keys)]
                brief = str(params.get("prompt") or params.get("topic") or "")
                sc = director.treatment(
                    str(params.get("prompt") or params.get("topic") or ""),
                    profiles,
                    float(params.get("seconds") or 60),
                    direct,
                    language=str(params.get("language") or "Spanish"),
                    fixed_style=fixed,
                    words_per_second=script.WORDS_PER_SECOND,
                    advice=_specialist(job, fixed, brief)
                    + _skills("guion", brief, job.state().get("genre", ""))
                    + genres.notes(job.state().get("genre", "")),
                )
            job.write("script.json", sc)
            job.update(
                title=sc["title"], style_key=sc.get("style") or fixed or style.DEFAULT
            )
            job.finish("guion")
        sc = job.read("script.json")
        profile = style.load(job.state().get("style_key", ""), deps.styles)
        narration = sc.get("narration") or profile.get("narration_mode") or "voice"
        profile = {**profile, "narration_mode": narration}
        if sc.get("look"):
            profile["look"] = sc["look"]

        # 3. the voice (none for films carried by pictures or a song)
        wav_path = job.dir / "narracion.wav"
        if stage("voz"):
            voiced = False
            if narration == "voice" and sc.get("text"):
                try:
                    beats = sc.get("beats") or []
                    if any((b.get("delivery") or {}).get("tone") for b in beats):
                        # performed: each part in its tone, real pauses
                        wav = script.narrate_beats(beats, speak=deps.speak)
                    else:
                        wav = script.narrate(sc["text"], speak=deps.speak)
                    wav_path.write_bytes(wav)
                    voiced = True
                except Exception as exc:  # noqa: BLE001 — words on screen still carry it
                    job.update(voice_error=str(exc)[:200])
                    job.log(f"sin voz: {exc}")
            if not voiced:
                total = _silent_length(
                    sc, float(params.get("seconds") or 60), script.WORDS_PER_SECOND
                )
                wav_path.write_bytes(
                    audio.write_wav(np.zeros(int(total * audio.SR), dtype=np.float32))
                )
            job.update(voice=voiced)
            job.finish("voz")
        wav = wav_path.read_bytes()

        # 4. word timings
        if stage("tiempos"):
            if job.state().get("voice"):
                words, how = script.timings(sc["text"], wav, recogniser=deps.recognise)
            else:
                total = len(audio.read_wav(wav)) / audio.SR
                words, how = _beat_words(sc, total), "ritmo"
            job.write("words.json", [w.__dict__ for w in words])
            job.update(timing=how)
            job.finish("tiempos")
        words = [P.Word(**w) for w in job.read("words.json")]

        genre = job.state().get("genre") or genres.for_style(
            job.state().get("style_key", "")
        )
        allowed = genres.sources(
            genre,
            _allowed_sources(
                sc.get("sources") or profile.get("sources") or [], params, mode
            ),
        )
        profile = {**profile, "search_words": genres.search_words(genre)}

        # 5. the editor's plan
        if stage("plan"):
            shots = P.plan_shots(
                words,
                profile,
                ask=lambda p: edit(p, json_mode=True),
                sources=allowed,
                extra=_beat_notes(sc)
                + genres.notes(genre)
                + _skills(
                    "motion",
                    f"{sc.get('title', '')} {sc.get('look', '')} {profile.get('name', '')}",
                    genre,
                )
                + _specialist(
                    job,
                    job.state().get("style_key", ""),
                    str(params.get("prompt") or params.get("topic") or sc["title"]),
                ),
            )
            if params.get("film", True) and profile.get("production") not in (
                "3d",
                "ai",
                "animation",
            ):
                share = genres.GENRES[genre].film_share if genre else P.FILM_SHARE
                P.add_film(shots, share, allowed=allowed)
            genres.finish(shots, words, genre)
            try:  # a named scene of a real film for every film shot
                films.plan_scenes(
                    shots,
                    words,
                    sc.get("title", ""),
                    str(sc.get("logline") or params.get("prompt") or ""),
                    lambda p: edit(p, json_mode=True),
                )
            except Exception:  # noqa: BLE001 — they keep their own search
                job.log("escenas de cine: no se pudieron elegir")
            if narration != "voice":
                for s in shots:
                    if all(w.text == "·" for w in words[s.first : s.last]):
                        s.text_style = "none"
            job.write("plan.json", P.to_json(shots))
            job.finish("plan")
        shots = P.from_json(job.read("plan.json"))

        aspect = str(params.get("aspect") or "16:9")
        aspect = aspect if aspect in render.SIZES else "16:9"
        library = assets.Library(_own_folders(params))
        filler = Filler(
            job.dir / "imagenes",
            mode,
            budget,
            ffmpeg=render.ffmpeg(),
            style=profile,
            characters=sc.get("characters") or [],
            preferred=allowed,
            library=library,
            aspect=aspect,
            searches=deps.searches if deps.stock else {},
            fetch=deps.fetch,
            make_image=deps.make_image,
            ai_provider=deps.ai_provider,
            blender=deps.blender or _blender_maker(edit, profile, sc, aspect),
            choose_ask=look_choose if mode.candidates > 1 else None,
            allow_web=_web_allowed(params),
            on_spend=save,
        )
        filler.credits = list(job.state().get("credits") or [])

        def fill(label: str) -> None:
            filler.fill(shots, progress=lambda f, n: job.progress(label, f, n))
            job.write("plan.json", P.to_json(shots))
            job.update(credits=filler.credits, budget=budget.to_dict())

        def dress() -> None:
            """Typefaces, places, accents (typo.py, color.py) once the
            pictures are known; kept in the plan, safe to run again."""
            from openjarvis.video_essay import typo

            small = render.DRAFT_SIZES[aspect]
            small = (small[0] // 3, small[1] // 3)

            def still(shot: Any) -> Any:
                return next(iter(render.background_for(shot, small).frames(1)), None)

            from openjarvis.video_essay import color

            touched = typo.dress(shots, words, still, profile)
            touched += color.unify(shots, still)  # one colour across the shots
            if touched:
                job.write("plan.json", P.to_json(shots))

        # 6. the pictures
        if stage("imagenes"):
            fill("imagenes")
            dress()
            job.finish("imagenes")

        # 7. review passes: the editor first, the director has the last word
        if stage("revision"):
            passes = list(job.state().get("passes") or [])
            want = min(mode.passes, int(params.get("passes", mode.passes)))
            draft = render.DRAFT_SIZES[aspect]
            while len(passes) < want and budget.can("llm"):
                if stop.is_set():
                    raise Cancelled()
                k = len(passes)
                last = k == want - 1 and mode.director_strong
                stills = []
                for i, shot in enumerate(shots):
                    stills.append(render.still_of(shot, words, draft))
                    job.progress(
                        "revision",
                        (k + i / len(shots) / 2) / max(1, want),
                        f"pasada {k + 1}",
                    )
                board = review.contact_sheet(stills)
                board.save(job.dir / f"revision-{k + 1}.jpg", quality=82)
                try:
                    notes = review.ask_review(
                        board, shots, profile, ask=look_direct if last else look_edit
                    )
                except Exception as exc:  # noqa: BLE001 — a missed review is not a failed video
                    passes.append(
                        {
                            "score": None,
                            "verdict": f"sin revisión: {str(exc)[:120]}",
                            "applied": 0,
                        }
                    )
                    job.update(passes=passes)
                    break
                shots, applied = review.apply(shots, words, notes, profile)
                score = notes.get("score")
                passes.append(
                    {"score": score, "verdict": str(notes.get("verdict") or "")[:200], "applied": applied,
                     "by": "director" if last else "editor"}
                )  # fmt: skip
                job.update(passes=passes)
                job.write("plan.json", P.to_json(shots))
                job.log(f"pasada {k + 1}: nota {score}, {applied} cambios")
                if applied:
                    fill("revision")
                    dress()
                good = isinstance(score, (int, float)) and score >= 9
                if not applied or good:
                    break  # nothing left to fix: no more paying for reviews
            job.finish("revision")

        # 8. the sound
        mix_path = job.dir / "mezcla.wav"
        if stage("sonido"):
            from openjarvis.video_essay import pro

            voice = audio.read_wav(wav)
            if job.state().get("voice"):  # the narration as a broadcast voice
                voice = pro.voice_chain(voice, render.ffmpeg(), audio.SR)
            total = max(shots[-1].end if shots else 0, len(voice) / audio.SR)
            music = None
            beats: List[float] = []
            if params.get("music") != "ninguna":
                music = _music(str(params.get("music") or ""), total, job.dir)
                if music is None and deps.stock:
                    music = _music_online(job, deps, params, profile, total, filler)
                if music is None:
                    music = audio.music_bed(total)
                    beats = pro.bed_beats(total, 84.0)
                else:
                    beats = pro.beat_times(music, audio.SR)
            if beats and len(shots) > 1:  # the cuts land on the beat
                cuts = pro.snap_cuts(
                    [s.start for s in shots[1:]],
                    beats,
                    [(w.start, w.end) for w in words],
                )
                for prev, shot, cut in zip(shots, shots[1:], cuts):
                    prev.end = shot.start = cut
            events = []
            for s in shots:
                sfx = (
                    s.sfx
                    if s.sfx != "none"
                    else ("whoosh" if s.transition == "whip" else "none")
                )
                if sfx != "none":
                    events.append((s.start, sfx))
            fx = audio.effects_track(events, total)
            level = 0.32 if job.state().get("voice") else 0.8
            mix_path.write_bytes(
                audio.write_wav(audio.mix(voice, music, fx, music_level=level))
            )
            _loudness(mix_path)
            job.finish("sonido")

        # 9. the render
        out = job.dir / "final.mp4"
        if stage("render"):
            size = (
                render.DRAFT_SIZES[aspect]
                if params.get("draft")
                else render.size_for(aspect, mode.size)
            )
            render.render_video(
                shots, words, out, size=size, audio=mix_path,
                preset=str(params.get("preset") or mode.preset),
                progress=lambda f: job.progress("render", f),
            )  # fmt: skip
            job.finish("render")

        # 10. finishing with Creator's tools, and the posting package
        if stage("acabado"):
            ff = render.ffmpeg()
            delivered = out
            extras: Dict[str, Any] = {}
            if mode.finishing:
                try:
                    delivered = finish.grade(
                        out,
                        job.dir / "final-color.mp4",
                        ff,
                        lut=str(params.get("lut") or ""),
                    )
                except Exception as exc:  # noqa: BLE001 — the ungraded cut is still good
                    job.log(f"sin color: {exc}")
            if mode.master:
                m = finish.master(delivered, ff, mode.master)
                if m:
                    extras["master"] = str(m)
            from openjarvis.video_essay import pro

            try:  # what a finishing editor checks before delivery
                cards = [(s.start, s.end) for s in shots if s.kind == "card"]
                extras["control"] = pro.quality_check(delivered, ff, cards)
                if not extras["control"]["ok"]:
                    job.log("control: " + "; ".join(extras["control"]["problemas"]))
            except Exception as exc:  # noqa: BLE001
                job.log(f"sin control de calidad: {exc}")
            from openjarvis.creator import studio

            name = studio.media_name("video", ".mp4")
            videos = deps.videos or studio.projects_root() / "videos"
            videos.mkdir(parents=True, exist_ok=True)
            shutil.copy2(delivered, videos / name)
            subs = videos / (Path(name).stem + ".srt")
            subs.write_text(pro.srt(words), encoding="utf-8")
            extras["subtitulos"] = f"/v1/creator/media/{subs.name}"
            if mode.package:  # the same video for the other screens
                others = [a for a in ("9:16", "1:1", "16:9") if a != aspect]
                formats = {}
                for other in others[:2]:
                    try:
                        cut = pro.reframe(
                            videos / name, other, ff, ff.replace("ffmpeg", "ffprobe")
                        )
                    except Exception as exc:  # noqa: BLE001
                        job.log(f"sin formato {other}: {exc}")
                        cut = None
                    if cut:
                        formats[other] = f"/v1/creator/media/{cut.name}"
                if formats:
                    extras["formatos"] = formats
            result = {
                "url": f"/v1/creator/media/{name}",
                "path": str(videos / name),
                "shots": len(shots),
                **extras,
            }
            if mode.package:
                from openjarvis.video_essay import sources as S

                chapters = _chapters(sc, shots, words)
                ask_pkg = edit if budget.can("llm") else None
                pkg = director.package(
                    sc.get("title", ""), sc.get("logline", ""), chapters, S.credits_text(filler.credits), ask_pkg,
                    language=str(params.get("language") or "Spanish"),
                )  # fmt: skip
                best = (
                    max(shots, key=lambda s: s.dur if s.kind != "card" else 0)
                    if shots
                    else None
                )
                if best is not None:
                    cover_name = studio.media_name("portada", ".jpg")
                    finish.cover(
                        render.still_of(best, words, render.SIZES[aspect]),
                        pkg["thumbnail_text"],
                        videos / cover_name,
                    )
                    pkg["cover_url"] = f"/v1/creator/media/{cover_name}"
                pkg["capitulos"] = pro.chapters_text(chapters)
                job.write("publicar.json", pkg)
                result["package"] = pkg
            job.update(result=result)
            job.finish("acabado")

        # 11. tell him
        if stage("listo"):
            final = job.update(
                status="listo", finished=time.time(), budget=budget.to_dict()
            )
            _specialist_learns(final)
            (deps.notify or _tell_hous)(job.id, final)
            job.finish("listo")
        return job.state()
    except Cancelled:
        job.log("cancelado")
        return job.update(status="cancelado", budget=budget.to_dict())
    except M.OverBudget as exc:
        job.log(f"tope: {exc}")
        return job.update(
            status="error",
            error=f"Me detuve para no gastar de más ({exc}).",
            budget=budget.to_dict(),
        )
    except Exception as exc:  # noqa: BLE001 — kept for «reintentar»
        job.log(traceback.format_exc()[-2000:])
        return job.update(status="error", error=str(exc)[:400], budget=budget.to_dict())
    finally:
        with _lock:
            _running.pop(job.id, None)


def _own_folders(params: Dict[str, Any]) -> List[str]:
    from openjarvis.video_essay.sources import own_folders

    return own_folders([str(params.get("clips") or "")])


def _web_allowed(params: Dict[str, Any]) -> bool:
    from openjarvis.video_essay.sources import web_allowed

    return bool(params.get("web_clips", True)) and web_allowed()


def _allowed_sources(
    preferred: List[str], params: Dict[str, Any], mode: Any
) -> List[str]:
    """The director's sources, minus what this mode or order does not use."""
    out = [
        s
        for s in preferred
        if s in ("library", "stock", "web", "film", "archive", "ai", "3d", "image")
    ]
    for s in ("library", "stock", "web", "film", "archive", "image"):
        if s not in out:
            out.append(s)
    if not params.get("ai_video") and mode.limits.get("ai_seconds", 0) <= 0:
        out = [s for s in out if s != "ai"]
    if mode.limits.get("blender", 0) <= 0:
        out = [s for s in out if s != "3d"]
    if not _web_allowed(params):
        out = [s for s in out if s not in ("web", "film")]
    return ["library"] + [s for s in out if s != "library"]


def _blender_maker(
    ask: Callable[..., str], profile: Dict[str, Any], sc: Dict[str, Any], aspect: str
) -> Optional[Callable[..., str]]:
    from openjarvis.video_essay import aivideo, blender3d, render

    if blender3d.blender_cmd() is None:
        return None

    def make(shot: Any, folder: Path) -> str:
        folder.mkdir(parents=True, exist_ok=True)
        code = blender3d.script_for(
            f"{shot.visual or shot.text}. Camera: {shot.camera or 'cinematic, motivated move'}",
            max(1.0, shot.dur), str(profile.get("look") or ""), aivideo.bible_text(sc.get("characters") or []), ask,
        )  # fmt: skip
        out = folder / f"toma-{abs(hash(code)) % 10**10}.mp4"
        size = render.size_for(aspect, "720")
        return blender3d.render_shot(
            code, out, max(1.0, shot.dur), size, render.ffmpeg()
        )

    return make


def _silent_length(sc: Dict[str, Any], seconds: float, wps: float) -> float:
    beats = sc.get("beats") or []
    told = sum(float(b.get("seconds") or 0) for b in beats)
    if told >= 5:
        return told + 0.8
    words = len(str(sc.get("text") or "").split())
    return max(seconds, words / wps) + 0.8


def _beat_words(sc: Dict[str, Any], total: float) -> List[Any]:
    """Words for a film without narration: each beat's words (or a hidden
    mark) spread over the beat's seconds."""
    from openjarvis.video_essay.plan import Word

    beats = sc.get("beats") or [{"text": sc.get("text", ""), "seconds": total}]
    told = [float(b.get("seconds") or 0) for b in beats]
    if sum(told) < 1:
        told = [total / len(beats)] * len(beats)
    scale = (total - 0.8) / sum(told)
    out, at = [], 0.0
    for b, secs in zip(beats, told):
        secs *= scale
        tokens = str(b.get("text") or "").split() or ["·"]
        step = secs / len(tokens)
        for t in tokens:
            out.append(Word(t, round(at, 3), round(at + step * 0.9, 3)))
            at += step
    return out


def _loudness(path: Path) -> None:
    """The mix at the platforms' loudness (−14 LUFS, peaks under −1.5 dBTP):
    a quiet video sounds weak next to the others in the feed."""
    from openjarvis.video_essay import audio, render

    out = path.with_suffix(".norm.wav")
    try:
        subprocess.run(
            [render.ffmpeg(), "-y", "-v", "error", "-i", str(path), "-af",
             "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(audio.SR), "-ac", "1", str(out)],
            check=True, capture_output=True, timeout=600,
        )  # fmt: skip
        out.replace(path)
    except Exception:  # noqa: BLE001 — the mix as it was
        out.unlink(missing_ok=True)


def _skills(kind: str, about: str, genre: str = "") -> str:
    """The GitHub skills that fit (script or motion), never in the way: the
    genre's own three when it has them."""
    try:
        from openjarvis.video_essay import skillbook

        return "\n" + skillbook.guidance(kind, about, genre=genre) + "\n"
    except Exception:  # noqa: BLE001
        return ""


def _beat_notes(sc: Dict[str, Any]) -> str:
    rows = [
        f"- {b.get('beat', '')}: {b.get('visual', '')}"
        for b in sc.get("beats") or []
        if b.get("visual")
    ]
    chars = sc.get("characters") or []
    text = ""
    if sc.get("title") or sc.get("logline"):
        text += (
            f"THE VIDEO: «{sc.get('title', '')}» — {sc.get('logline', '')}. Every shot "
            "serves this story; the visual of each shot shows what is being said NOW.\n"
        )
    if sc.get("look"):
        text += f"ONE LOOK FOR THE WHOLE VIDEO: {str(sc['look'])[:400]}\n"
    if rows:
        text += (
            "DIRECTOR'S VISUALS, beat by beat (use them):\n"
            + "\n".join(rows[:80])
            + "\n"
        )
    if chars:
        text += "CHARACTERS (same look in every shot): " + "; ".join(
            f"{c.get('name')}: {c.get('look')}" for c in chars
        )
    return text


def _chapters(sc: Dict[str, Any], shots: List[Any], words: List[Any]) -> List[tuple]:
    """(seconds, beat) at the first word of each beat."""
    out, i = [], 0
    for b in sc.get("beats") or []:
        n = len(str(b.get("text") or "").split()) or 1
        if i < len(words):
            out.append(
                (words[i].start, str(b.get("beat") or "").capitalize() or "Parte")
            )
        i += n
    return out


def _music(path: str, total: float, folder: Path) -> Any:
    """The owner's song as 48 kHz mono samples (None when it is not a file)."""
    from openjarvis.video_essay import audio, render

    src = Path(path).expanduser()
    if not path or not src.is_file():
        return None
    out = folder / "musica.wav"
    try:
        subprocess.run(
            [render.ffmpeg(), "-y", "-v", "error", "-i", str(src), "-ac", "1",
             "-ar", str(audio.SR), "-t", str(total + 1), str(out)],
            check=True, capture_output=True, timeout=600,
        )  # fmt: skip
        return audio.read_wav(out.read_bytes())
    except Exception:  # noqa: BLE001 — Sergio's own bed instead
        return None


def _music_online(
    job: Any,
    deps: Deps,
    params: Dict[str, Any],
    profile: Dict[str, Any],
    total: float,
    filler: Any,
) -> Any:
    """Free music for the mood (or the song he named) from the internet,
    credited; None when none could be had (Sergio's own bed then)."""
    from openjarvis.video_essay import audio, music, render

    wish = str(params.get("music") or "")
    try:
        track = music.pick(
            wish, profile, job.dir / "musica", total, render.ffmpeg(),
            for_money=params.get("monetize", True) is not False,
            searches=deps.music_searches, song=deps.song, fetcher=deps.music_fetch,
        )  # fmt: skip
        if track is None or not track.path:
            return None
        samples = audio.read_wav(Path(track.path).read_bytes())
    except Exception as exc:  # noqa: BLE001 — Sergio's own bed instead
        job.log(f"música de internet: {str(exc)[:120]}")
        return None
    filler.credits.append(track.credit())
    job.update(music=track.to_dict(), credits=filler.credits)
    job.log(f"música: {track.title or track.url} ({track.licence})")
    return samples


def summary(st: Dict[str, Any]) -> str:
    """One line a person understands."""
    title = st.get("title") or (st.get("params") or {}).get("topic") or "Video ensayo"
    status = st.get("status")
    if status == "listo":
        res = st.get("result") or {}
        notes = [p for p in st.get("passes") or [] if p.get("score")]
        who = (
            "del director"
            if notes and notes[-1].get("by") == "director"
            else "del editor"
        )
        score = f" Nota final {who}: {notes[-1]['score']}/10." if notes else ""
        pkg = res.get("package") or {}
        extra = (
            f"\nListo para publicar: «{pkg.get('title')}» (título, descripción, créditos y portada)."
            if pkg
            else ""
        )
        if pkg.get("note"):
            extra += " " + pkg["note"]
        return f"«{title}» está listo ({res.get('shots', 0)} tomas).{score}{extra}\n\n![{title}]({res.get('url', '')})"
    if status == "error":
        where = LABELS.get(st.get("stage", ""), st.get("stage"))
        return f"«{title}» se detuvo en «{where}»: {st.get('error', '')}. Puedo reintentarlo desde ahí."
    if status == "cancelado":
        return f"«{title}» está cancelado."
    stage = st.get("stage", "")
    k = STAGES.index(stage) + 1 if stage in STAGES else 0
    pct = round(100 * float(st.get("stage_progress") or 0))
    return (
        f"«{title}»: paso {k} de {len(STAGES)}, {LABELS.get(stage, stage)} ({pct} %)."
    )


STALLED_MINUTES = 30  # «en curso» without a single update this long: stopped


def truth(
    now: Optional[float] = None, root: Optional[Path] = None, hours: float = 72
) -> str:
    """What is REALLY happening with the videos, for every turn of the chat and
    the Nodes (owner, 27 Oct 2026: a Node said «el motor ha arrancado en modo
    Post» a day after the request, with no video at all). Models only tell
    what this says; with no job, there is no video in the works."""
    now = time.time() if now is None else now
    lines = []
    for job in all_jobs(root):
        st = job.state()
        created = float(st.get("created") or 0)
        if now - created > hours * 3600:
            continue
        ago = max(0, int((now - created) / 60))
        when = (
            f"pedido hace {ago // 60} h {ago % 60} min"
            if ago >= 60
            else f"pedido hace {ago} min"
        )
        status = st.get("status")
        quiet = (now - float(st.get("updated") or created)) / 60
        if status == "en curso" and (
            job.id not in _running or not _running[job.id].is_alive()
        ):
            if quiet > STALLED_MINUTES:
                text = (
                    f"«{st.get('title') or (st.get('params') or {}).get('prompt', '')[:60] or 'Video'}» está "
                    f"DETENIDO (sin avance desde hace {int(quiet // 60)} h {int(quiet % 60)} min, paso "
                    f"«{LABELS.get(st.get('stage', ''), st.get('stage', ''))}»). Se puede reintentar."
                )
            else:
                text = summary(st)
        else:
            text = summary(st).split("\n")[0]
        lines.append(f"- [{job.id}] {text} ({when})")
    if not lines:
        return (
            "<videos_reales>Ningún video pedido en los últimos 3 días: no hay nada en marcha. "
            "Si el usuario espera uno, díselo con claridad y ofrece empezarlo ahora con la "
            "herramienta de video.</videos_reales>"
        )
    return (
        "<videos_reales>Estado REAL de los videos (lo dice el código, no tú):\n"
        + "\n".join(lines[:6])
        + "\nNunca digas que un video avanza, arrancó o está casi listo si aquí no aparece así. "
        "Si está detenido o falló, dilo tal cual, sin adornos, y ofrece reintentarlo.</videos_reales>"
    )


def _tell_hous(job_id: str, st: Dict[str, Any]) -> None:
    try:
        from openjarvis.nodes.store import NodeStore

        store = NodeStore()
        node = store.team_node("hous")
        if node is not None:
            store.say(
                node.id,
                "node",
                "Señor, terminé el video ensayo. " + summary(st),
                video_job=job_id,
            )
    except Exception:  # noqa: BLE001 — the video is ready even if the notice fails
        pass


# -- threads ---------------------------------------------------------------------------


def launch(job: Job, deps: Optional[Deps] = None) -> bool:
    """Run *job* in the background (False if it is already running)."""
    with _lock:
        if job.id in _running and _running[job.id].is_alive():
            return False
        _cancel[job.id] = threading.Event()
        t = threading.Thread(
            target=run, args=(job, deps), name=f"ensayo-{job.id}", daemon=True
        )
        _running[job.id] = t
        t.start()
        return True


def start(
    params: Dict[str, Any], deps: Optional[Deps] = None, root: Optional[Path] = None
) -> Job:
    job = create(params, root)
    launch(job, deps)
    return job


def get(job_id: str, root: Optional[Path] = None) -> Optional[Job]:
    folder = (root or jobs_dir()) / Path(job_id).name
    return Job(folder) if (folder / "state.json").is_file() else None


def all_jobs(root: Optional[Path] = None) -> List[Job]:
    root = root or jobs_dir()
    if not root.is_dir():
        return []
    found = [Job(p) for p in root.iterdir() if (p / "state.json").is_file()]
    return sorted(found, key=lambda j: j.state().get("created", 0), reverse=True)


def cancel(job_id: str, root: Optional[Path] = None) -> bool:
    job = get(job_id, root)
    if job is None:
        return False
    _cancel.setdefault(job.id, threading.Event()).set()
    if job.id not in _running:
        job.update(status="cancelado")
    return True


MAX_ATTEMPTS = 4  # runs of one job (first + resumes + retries): never an endless loop
SAME_ORDER_MINUTES = 30


def retry(
    job_id: str, deps: Optional[Deps] = None, root: Optional[Path] = None
) -> Optional[Job]:
    job = get(job_id, root)
    if job is None:
        return None
    if int(job.state().get("attempts") or 0) >= MAX_ATTEMPTS:
        job.update(
            error=f"Ya lo intenté {MAX_ATTEMPTS} veces; no lo repito para no gastar de más."
        )
        return job
    job.update(status="en curso", error="")
    launch(job, deps)
    return job


def resume_unfinished(
    deps: Optional[Deps] = None, root: Optional[Path] = None
) -> List[str]:
    """Pick up the jobs a restart left half done (a few times at most)."""
    picked = []
    for job in all_jobs(root):
        st = job.state()
        if st.get("status") != "en curso" or job.id in _running:
            continue
        if int(st.get("attempts") or 0) >= MAX_ATTEMPTS:
            job.update(
                status="error",
                error="Se interrumpió demasiadas veces; lo dejé quieto para no gastar de más.",
            )
            continue
        if launch(job, deps):
            picked.append(job.id)
    return picked


def running(root: Optional[Path] = None) -> List[Job]:
    return [j for j in all_jobs(root) if j.id in _running and _running[j.id].is_alive()]


def _same(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    keys = ("topic", "prompt", "script", "reference", "style", "mode", "aspect")
    return all(
        str(a.get(k) or "").strip().lower() == str(b.get(k) or "").strip().lower()
        for k in keys
    )


def guard(params: Dict[str, Any], root: Optional[Path] = None) -> tuple:
    """(job, why) when a new job must NOT start; (None, "") when it can.

    One video at a time; the same order again within half an hour returns the
    one already made; and at most ``SERGIO_VIDEO_JOBS_DIA`` (6) a day."""
    import os

    busy = running(root)
    if busy:
        return busy[0], "en curso"
    now = time.time()
    today = [
        j for j in all_jobs(root) if now - float(j.state().get("created") or 0) < 86400
    ]
    for j in today:
        st = j.state()
        if (
            _same(st.get("params") or {}, params)
            and now - float(st.get("created") or 0) < SAME_ORDER_MINUTES * 60
        ):
            if st.get("status") in ("en curso", "listo"):
                return j, "repetido"
    try:
        cap = int(os.environ.get("SERGIO_VIDEO_JOBS_DIA", "6"))
    except ValueError:
        cap = 6
    if len(today) >= cap:
        return today[0], "tope diario"
    return None, ""


__all__ = [
    "Deps", "Job", "LABELS", "STAGES", "all_jobs", "cancel", "create", "get",
    "guard", "jobs_dir", "launch", "resume_unfinished", "retry", "run", "running", "start", "summary", "truth",
]  # fmt: skip

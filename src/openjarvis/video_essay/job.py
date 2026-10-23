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
    "listo",
)
LABELS = {
    "estudio": "Estudiando la referencia toma por toma",
    "guion": "Escribiendo el guion",
    "voz": "Narrando con la voz de Sergio",
    "tiempos": "Midiendo cuándo se dice cada palabra",
    "plan": "Planeando las tomas",
    "imagenes": "Buscando y creando las imágenes",
    "revision": "Revisando el montaje como un editor",
    "sonido": "Mezclando efectos y música",
    "render": "Renderizando el video final",
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
        self.ask: Optional[Callable[..., str]] = over.get("ask")  # text model
        self.review: Optional[Callable[..., str]] = over.get("review")  # vision model
        self.speak: Optional[Callable[[str], bytes]] = over.get("speak")
        self.recognise: Optional[Callable[[bytes, str], list]] = over.get("recognise")
        self.make_image: Optional[Callable[[str], bytes]] = over.get("make_image")
        self.watcher: Optional[Callable[[str], Dict[str, Any]]] = over.get("watcher")
        self.stock: bool = over.get("stock", True)
        self.notify: Optional[Callable[[str, Dict[str, Any]], None]] = over.get(
            "notify"
        )
        self.videos: Optional[Path] = over.get("videos")
        self.styles: Optional[Path] = over.get("styles")

    def plan_ask(self) -> Callable[[str], str]:
        if self.ask is not None:
            ask = self.ask
            return lambda p: ask(p, json_mode=True)
        from openjarvis.creator.llm import ask as gemini_ask
        from openjarvis.video_essay.style import models

        return lambda p: gemini_ask(
            p, json_mode=True, models=models(), effort="high", max_tokens=60000
        )


def run(job: Job, deps: Optional[Deps] = None) -> Dict[str, Any]:
    """Do (or finish) every stage of *job*; returns its final state."""
    import numpy as np

    from openjarvis.video_essay import assets, audio, render, review, script, style
    from openjarvis.video_essay import plan as P

    deps = deps or Deps()
    st = job.state()
    params = st.get("params") or {}
    stop = _cancel.setdefault(job.id, threading.Event())

    def stage(name: str) -> bool:
        if stop.is_set():
            raise Cancelled()
        if job.done(name):
            return False
        job.update(stage=name, stage_progress=0.0, note="")
        job.log(f"empieza: {name}")
        return True

    try:
        # 1. the reference
        if stage("estudio"):
            ref = str(params.get("reference") or "").strip()
            if ref:
                profile = style.learn(
                    ref,
                    str(params.get("style_name") or ""),
                    folder=deps.styles,
                    watcher=deps.watcher,
                )
                job.update(style_key=profile["key"])
            else:
                job.update(
                    style_key=style.load(str(params.get("style") or ""), deps.styles)[
                        "key"
                    ]
                )
            job.finish("estudio")
        profile = style.load(job.state().get("style_key", ""), deps.styles)

        # 2. the script
        if stage("guion"):
            if params.get("script"):
                sc = script.from_text(
                    str(params["script"]), str(params.get("title") or "")
                )
            else:
                sc = script.write(
                    str(params.get("topic") or ""),
                    float(params.get("seconds") or 90),
                    profile,
                    language=str(params.get("language") or "Spanish"),
                    ask=deps.ask,
                )
            job.write("script.json", sc)
            job.update(title=sc["title"])
            job.finish("guion")
        sc = job.read("script.json")

        # 3. the voice
        wav_path = job.dir / "narracion.wav"
        if stage("voz"):
            try:
                wav_path.write_bytes(script.narrate(sc["text"], speak=deps.speak))
                job.update(voice=True)
            except Exception as exc:  # noqa: BLE001 — words on screen still carry it
                silent = len(sc["text"].split()) / script.WORDS_PER_SECOND + 1
                wav_path.write_bytes(
                    audio.write_wav(np.zeros(int(silent * audio.SR), dtype=np.float32))
                )
                job.update(voice=False, voice_error=str(exc)[:200])
                job.log(f"sin voz: {exc}")
            job.finish("voz")
        wav = wav_path.read_bytes()

        # 4. word timings
        if stage("tiempos"):
            if job.state().get("voice"):
                words, how = script.timings(sc["text"], wav, recogniser=deps.recognise)
            else:
                total = len(audio.read_wav(wav)) / audio.SR
                words, how = (
                    P.estimate_words(sc["text"], [(0.3, total - 0.5)], total),
                    "ritmo",
                )
            job.write("words.json", [w.__dict__ for w in words])
            job.update(timing=how)
            job.finish("tiempos")
        words = [P.Word(**w) for w in job.read("words.json")]

        # 5. the plan
        if stage("plan"):
            shots = P.plan_shots(words, profile, ask=deps.plan_ask())
            job.write("plan.json", P.to_json(shots))
            job.finish("plan")
        shots = P.from_json(job.read("plan.json"))

        aspect = str(params.get("aspect") or "16:9")
        aspect = aspect if aspect in render.SIZES else "16:9"
        library = (
            assets.Library([str(params["clips"])]) if params.get("clips") else None
        )

        def fill(label: str) -> None:
            assets.fill(
                shots,
                job.dir / "imagenes",
                library=library,
                stock=deps.stock,
                make_image=deps.make_image,
                landscape=aspect != "9:16",
                progress=lambda f, n: job.progress(label, f, n),
            )
            job.write("plan.json", P.to_json(shots))

        # 6. the pictures
        if stage("imagenes"):
            fill("imagenes")
            job.finish("imagenes")

        # 7. review passes
        if stage("revision"):
            passes = list(job.state().get("passes") or [])
            want = max(0, min(5, int(params.get("passes", 2))))
            draft = render.DRAFT_SIZES[aspect]
            while len(passes) < want:
                if stop.is_set():
                    raise Cancelled()
                k = len(passes)
                stills = []
                for i, shot in enumerate(shots):
                    stills.append(render.still_of(shot, words, draft))
                    job.progress(
                        "revision", (k + i / len(shots) / 2) / want, f"pasada {k + 1}"
                    )
                board = review.contact_sheet(stills)
                board.save(job.dir / f"revision-{k + 1}.jpg", quality=82)
                try:
                    notes = review.ask_review(board, shots, profile, ask=deps.review)
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
                passes.append(
                    {
                        "score": notes.get("score"),
                        "verdict": str(notes.get("verdict") or "")[:200],
                        "applied": applied,
                    }
                )
                job.update(passes=passes)
                job.write("plan.json", P.to_json(shots))
                job.log(f"pasada {k + 1}: nota {notes.get('score')}, {applied} cambios")
                if applied:
                    fill("revision")
                if not applied:
                    break  # nothing left to fix
            job.finish("revision")

        # 8. the sound
        mix_path = job.dir / "mezcla.wav"
        if stage("sonido"):
            voice = audio.read_wav(wav)
            total = max(shots[-1].end if shots else 0, len(voice) / audio.SR)
            music = (
                _music(str(params.get("music") or ""), total, job.dir)
                if params.get("music") != "ninguna"
                else None
            )
            if music is None and params.get("music") != "ninguna":
                music = audio.music_bed(total)
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
            mix_path.write_bytes(audio.write_wav(audio.mix(voice, music, fx)))
            job.finish("sonido")

        # 9. the final render
        if stage("render"):
            out = job.dir / "final.mp4"
            render.render_video(
                shots,
                words,
                out,
                size=render.SIZES[aspect]
                if not params.get("draft")
                else render.DRAFT_SIZES[aspect],
                audio=mix_path,
                preset=str(params.get("preset") or "medium"),
                progress=lambda f: job.progress("render", f),
            )
            from openjarvis.creator import studio

            name = studio.media_name("video", ".mp4")
            videos = deps.videos or studio.projects_root() / "videos"
            videos.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, videos / name)
            job.update(
                result={
                    "url": f"/v1/creator/media/{name}",
                    "path": str(videos / name),
                    "shots": len(shots),
                }
            )
            job.finish("render")

        # 10. tell him
        if stage("listo"):
            final = job.update(status="listo", finished=time.time())
            (deps.notify or _tell_hous)(job.id, final)
            job.finish("listo")
        return job.state()
    except Cancelled:
        job.log("cancelado")
        return job.update(status="cancelado")
    except Exception as exc:  # noqa: BLE001 — kept for «reintentar»
        job.log(traceback.format_exc()[-2000:])
        return job.update(status="error", error=str(exc)[:400])
    finally:
        with _lock:
            _running.pop(job.id, None)


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


def summary(st: Dict[str, Any]) -> str:
    """One line a person understands."""
    title = st.get("title") or (st.get("params") or {}).get("topic") or "Video ensayo"
    status = st.get("status")
    if status == "listo":
        res = st.get("result") or {}
        notes = [p for p in st.get("passes") or [] if p.get("score")]
        score = f" Nota final del editor: {notes[-1]['score']}/10." if notes else ""
        return f"«{title}» está listo ({res.get('shots', 0)} tomas).{score}\n\n![{title}]({res.get('url', '')})"
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


def retry(
    job_id: str, deps: Optional[Deps] = None, root: Optional[Path] = None
) -> Optional[Job]:
    job = get(job_id, root)
    if job is None:
        return None
    job.update(status="en curso", error="")
    launch(job, deps)
    return job


def resume_unfinished(
    deps: Optional[Deps] = None, root: Optional[Path] = None
) -> List[str]:
    """Pick up the jobs a restart left half done."""
    picked = []
    for job in all_jobs(root):
        if job.state().get("status") == "en curso" and job.id not in _running:
            if launch(job, deps):
                picked.append(job.id)
    return picked


__all__ = [
    "Deps", "Job", "LABELS", "STAGES", "all_jobs", "cancel", "create", "get",
    "jobs_dir", "launch", "resume_unfinished", "retry", "run", "start", "summary",
]  # fmt: skip

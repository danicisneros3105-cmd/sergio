from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from openjarvis.video_essay import equipo, galeria, inspiracion, job, modes, script
from openjarvis.video_essay.plan import Shot


def test_three_editorial_workers_run_independently_and_count_calls():
    barrier = threading.Barrier(3)
    budget = modes.Budget.from_dict({}, modes.get("post"), 30)

    def ask(prompt):
        barrier.wait(timeout=2)
        return prompt.split(".")[0]

    result = equipo.prepare("Una carrera cuesta arriba", ask, budget)
    assert [r["rol"] for r in result] == ["guion", "montaje", "sonido"]
    assert all(r["estado"] == "listo" for r in result)
    assert budget.to_dict()["spent"]["llm"] == 3


def test_live_signals_distinguish_sources_and_use_recent_instagram(monkeypatch):
    monkeypatch.setattr(inspiracion, "_yt_auth", lambda: {"params": {"key": "test"}})
    monkeypatch.setattr(
        inspiracion,
        "youtube_api",
        lambda *_a, **_k: [
            {
                "url": "https://www.youtube.com/watch?v=example",
                "titulo": "Una carrera",
                "publicado": "2026-11-05T00:00:00Z",
                "vistas": 30,
                "me_gusta": 2,
            }
        ],
    )

    def ig(_tag, _get, *, recent):
        assert recent
        raise RuntimeError("credential=must-not-be-in-result")

    monkeypatch.setattr(inspiracion, "instagram", ig)
    result = equipo.live_signals("Una carrera", True)
    assert result["YouTube"]["estado"] == "leido"
    assert result["Instagram"] == {"estado": "no disponible", "ejemplos": []}
    assert "credential" not in str(result)


def test_voice_direction_gives_the_reveal_room_and_caps_long_pauses():
    beats = [
        {"beat": "problem", "text": "La puerta se cerró."},
        {
            "beat": "reveal",
            "text": "El motor activó el sensor.",
            "delivery": {"pause": 1.6},
        },
    ]
    performed = script.performance(beats)
    assert performed[0]["delivery"] == {"tone": "serious", "pause": 0.42}
    assert performed[1]["delivery"]["pause"] == 0.55
    assert "delivery" not in beats[0]
    assert (
        job.checklist({"done": ["voz"], "voice_error": "no quota"})[1]["estado"]
        == "sin voz"
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_gallery_makes_real_cuts_from_all_selected_files_in_order(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    files = []
    for i, color in enumerate(("red", "blue")):
        path = tmp_path / f"{i}.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color={color}:s=96x168:d=2:r=30",
                "-c:v",
                "libx264",
                str(path),
            ],
            check=True,
        )
        files.append(path)
    shots = [Shot(i, i + 1, start=float(i), end=float(i + 1)) for i in range(3)]
    galeria.fill(shots, files, tmp_path / "cortes", ffmpeg)
    assert [s.notes[-1] for s in shots] == [
        "imagen: galería seleccionada (1)",
        "imagen: galería seleccionada (2)",
        "imagen: galería seleccionada (2)",
    ]
    assert all(Path(s.asset).stat().st_size > 1000 for s in shots)


def test_youtube_requires_approval_and_thumbnail_retry_does_not_upload_twice(
    tmp_path, monkeypatch
):
    from openjarvis.automatiza import canales
    from openjarvis.conserje import aprobar
    from openjarvis.server import personal_routes
    from openjarvis.video_essay import schedule

    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    (tmp_path / "portada-prueba.jpg").write_bytes(b"cover")
    work = job.create({"aspect": "9:16"}, tmp_path / "jobs")
    work.update(
        status="listo",
        result={
            "path": str(video),
            "package": {"cover_url": "/v1/creator/media/portada-prueba.jpg"},
        },
    )
    monkeypatch.setattr(job, "get", lambda _: work)
    monkeypatch.setattr(canales, "account", lambda _: {"refresh_token": "test"})
    monkeypatch.setattr(schedule, "load", lambda: [])
    approval = iter((False, True))
    monkeypatch.setattr(aprobar, "owner_yes", lambda *_: next(approval))
    uploads = []

    def upload(*_a, privacy, **_k):
        uploads.append(privacy)
        return {"id": "test", "url": "https://youtu.be/test", "short": True}

    thumbnails = iter(("procesando", "aplicada"))
    monkeypatch.setattr(canales, "youtube_upload", upload)
    monkeypatch.setattr(
        canales, "youtube_thumbnail", lambda *_a, **_k: next(thumbnails)
    )

    class Immediate:
        def __init__(self, target, **_kw):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(personal_routes.threading, "Thread", Immediate)
    personal_routes.request_youtube_upload(work.id)
    assert not uploads
    personal_routes.request_youtube_upload(work.id)
    assert work.state()["subida_youtube"]["miniatura"] == "procesando"
    personal_routes.request_youtube_upload(work.id)
    assert work.state()["subida_youtube"]["miniatura"] == "aplicada"
    assert uploads == ["private"]


def test_phone_picker_batch_has_order_and_no_user_controlled_path(
    tmp_path, monkeypatch
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server.personal_routes import router

    monkeypatch.setattr(galeria, "home", lambda: tmp_path)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post(
            "/v1/personal/videos/galeria",
            files=[
                ("files", ("../segundo.mov", b"primero", "video/quicktime")),
                ("files", ("primero.mp4", b"segundo", "video/mp4")),
            ],
        )
    assert response.status_code == 200, response.text
    files = galeria.sources(response.json()["id"])
    assert [p.name for p in files] == ["01.mov", "02.mp4"]
    assert [p.read_bytes() for p in files] == [b"primero", b"segundo"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_actual_mix_ducks_the_bed_while_the_voice_is_present(tmp_path):
    import numpy as np

    from openjarvis.video_essay import audio, mezcla

    sr = audio.SR
    t = np.arange(5 * sr) / sr
    voice = (0.24 * np.sin(2 * np.pi * 600 * t) * ((t > 1.0) & (t < 2.6))).astype(
        np.float32
    )
    bed = (0.16 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    voice_path, bed_path, out = (
        tmp_path / f"{stem}.wav" for stem in ("voice", "bed", "mix")
    )
    voice_path.write_bytes(audio.write_wav(voice))
    bed_path.write_bytes(audio.write_wav(bed))
    info = mezcla.master(
        out,
        voice=voice_path,
        music=bed_path,
        fx=None,
        total=5.0,
        ffmpeg=shutil.which("ffmpeg"),
        music_db=-18,
    )
    samples = audio.read_wav(out.read_bytes())
    base = np.sin(2 * np.pi * 440 * np.arange(sr // 2) / sr)

    def bed_amplitude(start):
        offset = round(start * sr)
        return abs(float(np.dot(samples[offset : offset + len(base)], base)))

    assert bed_amplitude(1.5) < 0.7 * bed_amplitude(3.5)
    assert info["canales"] == 2 and -16 < info["lufs"] < -12

"""A plan the creator films (script, animatic, shot list) and the edit of their takes."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from openjarvis.creator import studio
from openjarvis.video_essay import mezcla, montaje, planear

FF = shutil.which("ffmpeg")

RAW = {
    "titulo": "Pasta en 30 segundos",
    "gancho": "El plato terminado primero",
    "musica": "upbeat 110 bpm",
    "notas": ["corte en cada golpe"],
    "tomas": [
        {"segundos": 1.6, "tipo": "Cara a cámara", "encuadre": "close-up", "movimiento": "push in",
         "que_se_ve": "Él con el plato", "dice": "Esta pasta se hace en treinta segundos",
         "texto": "30 SEGUNDOS", "sonido": "whoosh", "consejo": "luz de ventana"},
        {"segundos": 1.4, "tipo": "b-roll", "encuadre": "top shot", "movimiento": "fija",
         "que_se_ve": "La olla hirviendo", "dice": "", "texto": "", "sonido": "hit", "consejo": ""},
        {"segundos": 1.5, "tipo": "producto??", "encuadre": "medium", "movimiento": "pull out",
         "que_se_ve": "El plato servido", "dice": "Pruébala hoy", "texto": "", "sonido": "riser", "consejo": ""},
    ],
}  # fmt: skip


def _no_pictures(prompt):  # an image service that is down: frames are drawn
    raise RuntimeError("sin servicio")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(planear, "home", lambda: tmp_path / "planes")
    (tmp_path / "planes").mkdir()
    monkeypatch.setattr(
        studio, "projects_root", lambda root=None: tmp_path / "proyectos"
    )
    (tmp_path / "proyectos").mkdir()
    return tmp_path


def test_clean_plan_checks_the_model():
    plan = planear.clean_plan(RAW, 4.5)
    assert [s["tipo"] for s in plan["tomas"]] == ["cara", "broll", "producto"]
    assert [s["n"] for s in plan["tomas"]] == [1, 2, 3]
    long = planear.clean_plan({"tomas": [{"segundos": 99}] * 40}, 60)
    assert len(long["tomas"]) == planear.MAX_SHOTS
    assert all(0.6 <= s["segundos"] <= 12 for s in long["tomas"])
    scaled = planear.clean_plan(RAW, 20)  # the asked total wins
    assert abs(sum(s["segundos"] for s in scaled["tomas"]) - 20) < 0.5
    with pytest.raises(ValueError):
        planear.clean_plan({"tomas": []}, 30)


def test_storyboard_frame_without_a_picture():
    img = planear.draw_frame(planear.clean_plan(RAW, 4.5)["tomas"][0], (360, 640))
    assert img.size == (360, 640)
    assert len(set(img.resize((90, 160)).tobytes())) > 2  # something is drawn


def test_cut_window():
    assert montaje.cut_window("cara", 2, 6.0, (1.0, 3.0)) == pytest.approx((0.88, 2.37))
    assert montaje.cut_window("broll", 2, 6.0, None) == (2.0, 2)
    assert montaje.cut_window("broll", 5, 3.0, None) == (0.0, 3.0)


def test_folder_rejects_bad_ids(home):
    with pytest.raises(KeyError):
        planear.folder("../x")


def _take(path, seconds, *, voice_from=None):
    cmd = [
        FF,
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=d={seconds}:s=640x360:r=30",
    ]
    if voice_from is not None:  # silence, then a tone where the talking is
        cmd += [
            "-f",
            "lavfi",
            "-i",
            f"sine=f=220:d={seconds},volume='if(between(t,{voice_from},{voice_from + 1.2}),0.6,0)':eval=frame",
        ]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if voice_from is not None:
        cmd += ["-c:a", "aac", "-shortest"]
    subprocess.run(cmd + [str(path)], check=True, capture_output=True)  # fmt: skip
    return path


@pytest.mark.skipif(not FF, reason="needs ffmpeg")
def test_plan_animatic_takes_and_edit(home):
    asked = []

    def ask(prompt, **kw):
        asked.append(prompt)
        return json.dumps(RAW)

    plan = planear.create("una receta de pasta", seconds=4.5, reference="https://www.youtube.com/shorts/a1",
                          ask=ask, gen=_no_pictures, ffmpeg=FF)  # fmt: skip
    assert "not measured" in asked[0]
    assert plan["referencia_estado"] == "sin_medicion"
    pid = plan["id"]
    folder = planear.folder(pid)
    assert plan["animatic"] == f"/v1/creator/plan/{pid}/animatic.mp4"
    assert (folder / "animatic.mp4").stat().st_size > 1000
    length, has_audio = montaje.probe(folder / "animatic.mp4", FF)
    assert abs(length - 4.5) < 0.6 and has_audio  # the clicks on the cuts
    assert (folder / "cuadros" / "toma-01.png").is_file()
    assert f"[[plan:{pid}]]" in planear.card(plan)

    # shot 1 filmed with talking, shot 2 not filmed, shot 3 a silent take
    (folder / "tomas").mkdir()
    _take(folder / "tomas" / "toma-01.mp4", 3, voice_from=0.8)
    _take(folder / "tomas" / "toma-03.mp4", 2)
    data = planear.load(pid)
    data["tomas"][0]["archivo"] = "toma-01.mp4"
    data["tomas"][2]["archivo"] = "toma-03.mp4"
    planear.save(pid, data)

    done = montaje.edit(pid, ffmpeg=FF)
    assert done["faltan"] == [2]
    final = home / "proyectos" / "videos" / done["url"].rsplit("/", 1)[1]
    assert final.is_file()
    length, has_audio = montaje.probe(final, FF)
    assert has_audio and 3.0 < length < 5.5
    sound = mezcla.measure(final, FF)
    assert abs(sound["I"] - mezcla.TARGET["I"]) < 1.5
    assert sound["TP"] <= -1.0
    assert planear.load(pid)["montaje"]["url"] == done["url"]
    assert "Faltan las tomas 2" in montaje.status_line(done)


@pytest.mark.skipif(not FF, reason="needs ffmpeg")
def test_routes_upload_and_edit(home):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.creator import routes
    from openjarvis.server.auth_middleware import _OPEN_MEDIA

    plan = planear.create(
        "pasta",
        seconds=4.5,
        ask=lambda p, **kw: json.dumps(RAW),
        gen=_no_pictures,
        ffmpeg=FF,
    )
    pid = plan["id"]
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    assert client.get(f"/v1/creator/plan/{pid}").json()["montando"] is False
    assert client.get(f"/v1/creator/plan/{pid}/animatic.mp4").status_code == 200
    assert client.get(f"/v1/creator/plan/{pid}/cuadro/toma-01.png").status_code == 200
    assert client.get(f"/v1/creator/plan/{pid}/cuadro/../plan.json").status_code == 404
    assert client.get("/v1/creator/plan/" + "0" * 24).status_code == 404

    take = _take(home / "t.mp4", 2, voice_from=0.3)
    r = client.post(
        f"/v1/creator/plan/{pid}/toma/1",
        files={"file": ("mi toma.MOV", take.read_bytes())},
    )
    assert r.status_code == 200 and r.json()["subidas"] == 1
    assert planear.load(pid)["tomas"][0]["archivo"] == "toma-01.mov"
    bad = client.post(
        f"/v1/creator/plan/{pid}/toma/1", files={"file": ("x.exe", b"MZ")}
    )
    assert bad.status_code == 400
    assert (
        client.post(
            f"/v1/creator/plan/{pid}/toma/9", files={"file": ("x.mp4", b"0")}
        ).status_code
        == 404
    )

    assert client.post(f"/v1/creator/plan/{pid}/montar").json()["estado"] == "montando"
    routes._EDITS[pid].join(120)
    after = client.get(f"/v1/creator/plan/{pid}").json()
    assert after["montando"] is False
    assert after.get("montaje") and not after.get("montaje_error"), after.get(
        "montaje_error"
    )
    assert after["montaje"]["faltan"] == [2, 3]

    assert _OPEN_MEDIA.fullmatch(f"/v1/creator/plan/{pid}/animatic.mp4")
    assert _OPEN_MEDIA.fullmatch(f"/v1/creator/plan/{pid}/cuadro/toma-01.png")
    assert not _OPEN_MEDIA.fullmatch(f"/v1/creator/plan/{pid}")
    assert not _OPEN_MEDIA.fullmatch(f"/v1/creator/plan/{pid}/montar")


def test_tool_says_plainly_when_a_plan_is_missing(home):
    from openjarvis.tools.planear_tool import PlanearVideoTool

    out = PlanearVideoTool().execute(action="estado", id="0" * 24)
    assert not out.success and "No encuentro" in out.content
    assert not PlanearVideoTool().execute(action="crear", idea="").success

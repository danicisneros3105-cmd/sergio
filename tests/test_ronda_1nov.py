"""Owner, 1 Nov 2026: Sergio rewrites its own code to improve (safely),
shows pictures of what it is doing, and the sign-up / any-provider fixes."""

from __future__ import annotations

import subprocess
import sys

import pytest

from openjarvis.evolution import automejora as A


def _repo(tmp_path):
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "pkg" / "suma.py").write_text("def suma(a, b):\n    return a - b\n")
    (root / "tests" / "test_suma.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / 'src'))\n"
        "from pkg.suma import suma\n\n\ndef test_suma():\n    assert suma(2, 3) == 5\n"
    )
    for cmd in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"],
    ):
        subprocess.run(["git", *cmd], cwd=root, check=True, capture_output=True)
    return root


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "home", lambda: tmp_path / "automejora")
    return tmp_path


def test_a_fix_that_passes_its_tests_is_applied_as_one_commit_and_can_be_undone(
    tmp_path, home
):
    root = _repo(tmp_path)
    m = A.improve(
        "suma restaba",
        [A.Change("src/pkg/suma.py", "return a - b", "return a + b")],
        root=root,
        python=sys.executable,
    )
    assert m.state == "aplicada", m.checks
    assert "return a + b" in (root / "src/pkg/suma.py").read_text()
    assert "pruebas" in m.checks and "-    return a - b" in m.diff
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=root, capture_output=True, text=True
    ).stdout
    assert "automejora: suma restaba" in log
    assert not subprocess.run(
        ["git", "worktree", "list"], cwd=root, capture_output=True, text=True
    ).stdout.count("mejora")
    A.revert(m.id, root=root)
    assert "return a - b" in (root / "src/pkg/suma.py").read_text()
    assert [h["state"] for h in A.history()] == ["deshecha"]


def test_a_change_that_breaks_the_tests_never_reaches_the_running_copy(tmp_path, home):
    root = _repo(tmp_path)
    m = A.improve(
        "romper",
        [A.Change("src/pkg/suma.py", "return a - b", "return a * b")],
        root=root,
        python=sys.executable,
    )
    assert m.state == "rechazada" and "pruebas fallaron" in m.checks.lower()
    assert "return a - b" in (root / "src/pkg/suma.py").read_text()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout
    assert status == ""


def test_it_only_touches_its_own_code_never_keys(tmp_path, home):
    root = _repo(tmp_path)
    for bad in (
        "../fuera.py",
        "/etc/passwd",
        "sergio.env",
        "src/secrets.py",
        "scripts/x.sh",
    ):
        with pytest.raises(A.AutomejoraError):
            A.improve("x", [A.Change(bad, "", "x")], root=root)
    with pytest.raises(A.AutomejoraError, match="demasiado grande"):
        A.improve(
            "x", [A.Change("src/pkg/n.py", "", "x\n" * (A.MAX_CHANGE + 1))], root=root
        )


def test_the_tool_reports_history(home):
    from openjarvis.tools.automejora_tool import AutomejoraTool

    out = AutomejoraTool().execute(action="historial")
    assert out.success and "Todavía" in out.content


# -- pictures of what Sergio is doing -------------------------------------------------


def test_the_activity_route_is_empty_without_a_desktop_and_passes_frames_through(
    monkeypatch,
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server import actividad_routes as R

    app = FastAPI()
    app.include_router(R.router)
    c = TestClient(app)

    def boom(since):
        raise RuntimeError("no desktop")

    monkeypatch.setattr(R, "_fetch", boom)
    assert c.get("/v1/actividad").json()["frames"] == []
    seen = []
    monkeypatch.setattr(
        R,
        "_fetch",
        lambda since: (
            seen.append(since)
            or {
                "task": 3,
                "state": "working",
                "goal": "Amazon",
                "frames": [{"n": 2, "caption": "clic"}],
            }
        ),
    )
    got = c.get("/v1/actividad?since=1").json()
    assert seen == [1] and got["task"] == 3 and got["frames"][0]["caption"] == "clic"


# -- what was failing in video creation ------------------------------------------------


def test_the_lit_word_uses_the_videos_own_accent_colour():
    from openjarvis.video_essay.captions import ass_document

    doc = ass_document(["hola mundo bonito"], [3.0], 1080, 1920, accent="&H00A3FF00")
    assert "\\c&H00A3FF00" in doc


def test_one_failed_picture_no_longer_turns_every_later_shot_black():
    from openjarvis.video_essay.media import Filler as Media

    m = Media.__new__(Media)
    m.broken = set()
    m._failed("image")
    m._failed("image")
    assert "image" not in m.broken
    m._failed("image")
    assert "image" in m.broken


def test_a_resulta_que_video_keeps_its_captions_and_gets_its_xray_graphics():
    from openjarvis.video_essay import genres
    from openjarvis.video_essay.plan import Shot
    from openjarvis.video_essay.script import Word

    texts = [
        "por",
        "qué",
        "la",
        "pantalla",
        "nota",
        "tu",
        "dedo",
        "y",
        "el",
        "plástico",
    ]
    words = [Word(t, i * 1.0, i + 0.9) for i, t in enumerate(texts)]
    shots = [Shot(i, i + 1, kind="broll", text_style="pop") for i in range(len(texts))]
    genres.finish(shots, words, "resultaaquee")
    assert all(s.text_style != "none" for s in shots)
    assert any(s.overlay for s in shots)


def test_resulta_que_is_recognised_with_or_without_accents():
    from openjarvis.tools.video_create import is_resulta_que

    assert is_resulta_que("¿Por qué la pantalla de tu móvil nota tu dedo?")
    assert is_resulta_que("algo", "Resulta que")
    assert not is_resulta_que("la historia del imperio romano")


# -- what only worked with Gemini -----------------------------------------------------


def test_the_coach_brain_answers_through_any_company_without_gemini(monkeypatch):
    from openjarvis.coach import brain
    from openjarvis.creator import llm

    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    asked = []

    def others(prompt, *, json_mode=False, max_tokens=0, check=None, **kw):
        asked.append(prompt)
        text = '{"plan": ["leer", "practicar"]}'
        check(text)
        return text

    monkeypatch.setattr(llm, "ask_others", others)
    got = brain.ask("Un plan de estudio", system="Eres un coach.")
    assert got == {"plan": ["leer", "practicar"]} and "Eres un coach." in asked[0]


def test_vision_falls_back_to_openrouter_when_there_is_no_gemini(monkeypatch):
    from openjarvis.tools import vision_look as V

    for k in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "MOONSHOT_API_KEY",
        "KIMI_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    sent = []

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Un perro en un sofá."}}]}

    class Http:
        def post(self, url, headers=None, json=None, timeout=None):
            sent.append((url, json["model"]))
            return R()

    monkeypatch.setattr(V, "_ollama", lambda *a, **k: "")
    assert V.ask_image(b"\xff\xd8\xff", "¿Qué ves?", Http()) == "Un perro en un sofá."
    assert sent[0][0].startswith("https://openrouter.ai/") and "/" in sent[0][1]


# -- games in Unreal Engine 5 ---------------------------------------------------------


def test_an_unreal_game_project_opens_with_its_level_script_and_models():
    import ast
    import io
    import json
    import zipfile

    from openjarvis.creator import unreal

    data = unreal.build(
        "Robot del bosque",
        "un juego de plataformas con un robot que salta",
        models=[{"file": "robot.glb", "x": 400, "y": 0}],
        model_files={"robot.glb": b"glTF"},
    )
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    project = json.loads(z.read("RobotDelBosque/RobotDelBosque.uproject"))
    assert {"PythonScriptPlugin", "EditorScriptingUtilities"} <= {
        p["Name"] for p in project["Plugins"]
    }
    ast.parse(z.read("RobotDelBosque/Content/Python/init_unreal.py"))
    assert "RobotDelBosque/Content/Modelos/robot.glb" in names
    assert "plataformas" in z.read("RobotDelBosque/LEEME.md").decode()
    with pytest.raises(unreal.UnrealError):
        unreal.build("x", "   ")


def test_unreal_is_in_creator():
    from openjarvis.creator import programs

    assert "unreal" in programs.WINDOWS_APPS and programs.OPENS["uproject"] == (
        "unreal",
    )

"""Video editing, Blender and face approval (control server + server tools)."""

from pathlib import Path

import pytest
from sergio_escritorio import media
from sergio_escritorio.voice import clean_transcript, normalise

from openjarvis.tools import desktop_tools
from openjarvis.tools.desktop_tools import (
    BlenderCreateTool,
    FaceApprovalTool,
    VideoEditTool,
)

JPEG = b"\xff\xd8\xff\xe0fakejpeg"


@pytest.fixture
def wired(control_server, monkeypatch):
    controller, url = control_server
    monkeypatch.setenv("SERGIO_DESKTOP_URL", url)
    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "secreto")
    return controller


# -- ffmpeg command (pure) ---------------------------------------------------
def test_build_command_vertical_with_title_music_and_silent_clip():
    clips = [Path("a.mp4"), Path("b.mov")]
    cmd = media.build_command(
        clips,
        Path("out.mp4"),
        aspect="9:16",
        clip_seconds=4,
        max_seconds=30,
        title="Mi viaje: día 1",
        music="",
        audio=[True, False],
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert cmd.count("-t") == 4  # two clips, the silent track and the total
    assert "scale=1080:1920" in graph and "crop=1080:1920" in graph
    assert "anullsrc" in cmd[cmd.index("lavfi") + 4]
    assert "[2:a]aresample" in graph  # silent clip b uses the anullsrc input
    assert "concat=n=2:v=1:a=1" in graph
    assert r"Mi viaje\: día 1" in graph
    assert cmd[cmd.index("-map") + 1] == "[vtitle]"
    assert cmd[-1] == "out.mp4"


def test_build_command_music_is_mixed_quietly(tmp_path):
    song = tmp_path / "song.mp3"
    song.write_bytes(b"x")
    cmd = media.build_command([Path("a.mp4")], Path("o.mp4"), music=str(song))
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "-stream_loop" in cmd and "[1:a]volume=0.22" in graph
    assert cmd[cmd.index("-map", cmd.index("-map") + 1) + 1] == "[amix]"


def test_spoken_folder_name_is_found(tmp_path):
    folder = tmp_path / "Videos" / "Viaje a Baños"
    folder.mkdir(parents=True)
    for name in ("2.mp4", "1.MOV", "notas.txt"):
        (folder / name).write_bytes(b"x")
    clips = media.find_clips("viaje a baños", home=tmp_path)
    assert [c.name for c in clips] == ["1.MOV", "2.mp4"]
    assert media.find_clips("baños", home=tmp_path)  # partial name works
    with pytest.raises(ValueError):
        media.find_clips("no existe", home=tmp_path)


# -- control server + tools ---------------------------------------------------
def test_video_edit_tool_reaches_windows(wired, desktop):
    result = VideoEditTool().execute(source="Viaje", aspect="9:16", title="Hola")
    assert result.success and "viaje.mp4" in result.content
    assert "face_approval" in result.content
    kind, options = desktop.calls[-1]
    assert kind == "make_video"
    assert options == {"source": "Viaje", "aspect": "9:16", "title": "Hola"}


def test_video_edit_needs_a_source(wired):
    assert not VideoEditTool().execute(source="").success


def test_blender_tool_sends_script(wired, desktop):
    script = "import bpy\nbpy.ops.mesh.primitive_monkey_add()"
    result = BlenderCreateTool().execute(script=script)
    assert result.success and "Blender" in result.content
    assert desktop.calls[-1] == ("blender", script)


def test_paused_control_blocks_video(wired):
    wired.enabled = False
    result = VideoEditTool().execute(source="Viaje")
    assert not result.success and "paused" in result.content


# -- face approval -------------------------------------------------------------
class FakeBook:
    def __init__(self, seen, enrolled):
        self.seen, self.enrolled = seen, enrolled

    def identify(self, _jpeg):
        return [type("M", (), {"name": n})() for n in self.seen]

    def people(self):
        return [{"name": n} for n in self.enrolled]


def _faces(monkeypatch, wired, seen, enrolled, owner=""):
    import openjarvis.faces as faces

    wired.camera = lambda: JPEG
    monkeypatch.setattr(faces, "FaceBook", lambda: FakeBook(seen, enrolled))
    monkeypatch.setenv("SERGIO_OWNER_NAME", owner)
    monkeypatch.setattr(desktop_tools, "_config_owner", lambda: "")


@pytest.mark.parametrize("approved", [True, False])
def test_face_approval_requires_desktop_consent(wired, approved):
    seen = []

    def decide(args):
        seen.append(args)
        return {"what": args["what"], "approved": approved}

    wired.skills["owner_approval"] = decide
    result = FaceApprovalTool().execute(what="publicar el video")
    assert result.success is approved
    assert seen == [{"what": "publicar el video"}]


def test_face_approval_rejects_a_different_action(wired):
    wired.skills["owner_approval"] = lambda args: {
        "what": "otra acción",
        "approved": True,
    }
    assert not FaceApprovalTool().execute(what="publicar el video").success


def test_recognized_face_alone_is_not_consent(monkeypatch, wired):
    _faces(monkeypatch, wired, ["Dani"], ["Dani"])
    assert not FaceApprovalTool().execute(what="publicar").success


def test_face_approval_without_camera(wired):
    wired.camera = None
    result = FaceApprovalTool().execute(what="publicar")
    assert not result.success and result.content.startswith("NO APROBADO")


def test_new_tools_are_registered_and_enabled():
    import importlib

    from openjarvis.cli.escritorio_cmd import DESKTOP_TOOLS
    from openjarvis.core.registry import ToolRegistry

    importlib.reload(desktop_tools)  # the suite clears registries between tests

    for name in ("video_edit", "blender_create", "face_approval", "face_enroll"):
        assert ToolRegistry.contains(name) and name in DESKTOP_TOOLS


# -- hearing -------------------------------------------------------------------
def test_quiet_voice_is_lifted():
    np = pytest.importorskip("numpy")
    quiet = (np.sin(np.linspace(0, 60, 16000)) * 0.1).astype(np.float32)
    assert 0.85 < float(np.max(np.abs(normalise(quiet)))) <= 0.91
    hiss = (np.sin(np.linspace(0, 60, 16000)) * 0.01).astype(np.float32)
    assert float(np.max(np.abs(normalise(hiss)))) < 0.2  # gain is capped (12x)


@pytest.mark.parametrize(
    ("heard", "kept"),
    [
        ("Sergio", "Sergio"),
        ("Sergio, abre Google y busca Nvidia", "Sergio, abre Google y busca Nvidia"),
        ("Subtítulos realizados por la comunidad de Amara.org", ""),
        (
            "Sergio, abre Google y busca, entra al primer link, abre YouTube,",
            "Sergio, abre Google y busca, entra al primer link, abre YouTube,",
        ),
        ("  ", ""),
    ],
)
def test_transcript_cleaning(heard, kept):
    assert clean_transcript(heard) == kept

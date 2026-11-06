from pathlib import Path
import pytest
from openjarvis.agents.orchestrator import _tool_observation
from openjarvis.core.types import ToolResult
from openjarvis.video_essay import blender3d

def test_errors_cannot_be_mistaken_for_success():
    bad = ToolResult(tool_name="file_write", content="No se pudo guardar", success=False)
    assert _tool_observation(bad).startswith("ERROR:")
    good = ToolResult(tool_name="file_write", content="Guardado", success=True)
    assert _tool_observation(good) == "Guardado"

def test_partial_blender_frames_stop_before_encoding(tmp_path, monkeypatch):
    monkeypatch.setattr(blender3d, "blender_cmd", lambda: ["blender"])
    def partial(args):
        target = Path(args[-1]).parent / "f" / "0001.png"
        target.write_bytes(b"fake-frame")
        return 0
    with pytest.raises(RuntimeError, match="1 de 12 fotogramas"):
        blender3d.render_shot("pass", tmp_path / "out.mp4", .4, (128,128), "ffmpeg", runner=partial)
    assert not (tmp_path / "out.mp4").exists()

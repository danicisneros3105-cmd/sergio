"""Character motion: what runs, what is refused, what the game gets."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from openjarvis.creator import movimiento, unreal


def test_text_to_motion_runs_kimodo_with_its_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(
        movimiento, "gpu", lambda: {"nombre": "RTX 4060", "vram_gb": 8.0}
    )
    seen = {}

    def runner(args, env, cwd):
        seen["args"], seen["env"] = args, env
        (tmp_path / "out" / "salta-un-muro.npz").write_bytes(b"npz")
        return 0

    (tmp_path / "out").mkdir()
    res = movimiento.texto_a_movimiento(
        "Salta un muro", 30, out_dir=tmp_path / "out", runner=runner
    )
    assert "kimodo_gen" in seen["args"] and "Salta un muro" in seen["args"]
    assert seen["args"][seen["args"].index("--duration") + 1] == "20.0"  # capped
    assert seen["args"][seen["args"].index("--model") + 1] == movimiento.KIMODO_MODEL
    assert seen["env"]["TEXT_ENCODER_DEVICE"] == "cpu"  # 8 GB < 17 GB
    assert res["npz"] and "NPZ" in res["aviso"]


def test_research_only_model_is_refused(tmp_path):
    with pytest.raises(movimiento.MovimientoError, match="investigación"):
        movimiento.texto_a_movimiento(
            "corre", out_dir=tmp_path, model="Kimodo-SMPLX-RP-v1", runner=lambda *a: 0
        )


def test_missing_engines_say_so(tmp_path, monkeypatch):
    monkeypatch.setenv("SERGIO_MOVIMIENTO_DIR", str(tmp_path))
    with pytest.raises(movimiento.MovimientoError, match="instala los movimientos"):
        movimiento.texto_a_movimiento("corre", out_dir=tmp_path / "o")
    monkeypatch.setattr(movimiento, "gpu", lambda: {})
    assert "NVIDIA" in movimiento.instalar()


def test_face_from_audio_reads_the_blendshapes(tmp_path):
    audio = tmp_path / "linea.wav"
    audio.write_bytes(b"RIFF")

    def runner(a, out):
        (out / "output_blendshape.csv").write_text("time,jawOpen\n0,0.4\n")
        return 0

    res = movimiento.cara_desde_audio(audio, tmp_path / "cara", runner=runner)
    assert res["blendshapes"].endswith("output_blendshape.csv")


def test_the_game_carries_animations_and_notes():
    data = unreal.build("Ninja", "un ninja que salta muros", extra_files={"Animaciones/salto.fbx": b"FBX",
                        "../fuera.txt": b"x"}, notes=["Una nota."])  # fmt: skip
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    assert "Ninja/Content/Animaciones/salto.fbx" in names
    assert "Ninja/Content/fuera.txt" in names  # «..» never leaves the project
    assert "- Una nota." in z.read("Ninja/LEEME.md").decode()


def test_tool_makes_cloud_models_and_motion(monkeypatch, tmp_path):
    from openjarvis.creator import despiece, nube3d, programs
    from openjarvis.tools.creator_tools import UnrealGameTool

    glb = tmp_path / "m.glb"
    glb.write_bytes(b"glTF....")
    monkeypatch.setattr(
        nube3d, "generate", lambda text: {"name": "dragon", "files": ["m.glb"]}
    )
    monkeypatch.setattr(despiece, "file_path", lambda name, rel: glb)
    monkeypatch.setattr(
        movimiento, "texto_a_movimiento", lambda text, out_dir: _anim(out_dir)
    )
    got = {}
    monkeypatch.setattr(
        programs,
        "open_in_windows",
        lambda kind, name, data: got.update(data=data) or "Abierto.",
    )
    res = UnrealGameTool().execute(
        idea="dragones",
        crear_modelos=["un dragón rojo"],
        movimientos=["vuela en círculo"],
    )
    assert (
        res.success
        and "1 hechos ahora en la nube" in res.content
        and "1 animaciones" in res.content
    )
    names = zipfile.ZipFile(io.BytesIO(got["data"])).namelist()
    assert any(n.endswith("Modelos/dragon.glb") for n in names)
    assert any(n.endswith("Animaciones/vuela.fbx") for n in names)


def _anim(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    f = out_dir / "vuela.fbx"
    f.write_bytes(b"FBX")
    return {"fbx": str(f)}

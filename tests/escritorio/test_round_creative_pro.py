"""This round on the desktop: no more cubes, no more echo, Blender add-ons,
post-production (masters, RIFE, auto-editor, MoviePy), CAD, styles, memory."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from sergio_escritorio import blender_addons as ba
from sergio_escritorio import media, quick
from sergio_escritorio import video_master as vm
from sergio_escritorio.quick import image_edit_parts, parse_quick
from sergio_escritorio.video_pro import render_command, style_named
from sergio_escritorio.voice import _echoing, is_self_echo, repeats


# -- holograms: real objects are designed, plain geometry is drawn ------------------------
@pytest.mark.parametrize("order, kind", [
    ("haz un holograma de un teléfono", "holo_model"),
    ("crea un holograma de una pelota de fútbol", "holo_model"),
    ("haz un holograma de un vaso", "holo_model"),
    ("crea una caja de música", "holo_maybe"),
    ("crea un cubo rojo", "holo"),
    ("crea 3 pelotas rojas", "holo"),
    ("crea una estrella dorada", "holo"),
])
def test_holograms_of_things_are_designed_not_cubes(order, kind):
    assert parse_quick(order).kind == kind


def test_free_form_hologram_parts_are_real_shapes():
    from sergio_escritorio import holo

    cup = holo.part_mesh("lathe", (0.1, 0.1, 0.1), {"profile": [[0, 0], [0.04, 0], [0.045, 0.1], [0, 0.1]]})
    handle = holo.part_mesh("tube", (0.1, 0.1, 0.1), {"path": [[0, 0, 0], [0.05, 0.02, 0], [0.06, 0.06, 0]], "radius": 0.006})
    plate = holo.part_mesh("extrude", (0.1, 0.1, 0.01), {"outline": [[0, 0], [0.1, 0], [0.05, 0.08]]})
    assert len(cup.vertices) > 64 and len(handle.vertices) > 24 and len(plate.faces) > 3
    assert len(holo.part_mesh("lathe", (0.1, 0.1, 0.1), {}).vertices) == 8  # no points: a plain box


# -- the echo guard: he no longer answers his own voice ------------------------------------
def test_his_own_words_heard_again_are_not_a_new_order():
    said = ["Listo, señor: la tetera ya está en Blender con sus cuatro vistas."]
    assert is_self_echo("la tetera ya está en Blender con sus cuatro vistas", said)
    assert not is_self_echo("abre Spotify", said) and not is_self_echo("sí", said)


def test_the_same_answer_twice_is_caught():
    said = ["Mañana lloverá en Cuenca por la tarde, lleve paraguas."]
    assert repeats("Mañana lloverá en Cuenca por la tarde; lleve paraguas.", said)
    assert not repeats("Hoy hace sol en Quito.", said)


def test_the_microphone_rests_right_after_he_speaks():
    class A:
        quiet_until = 10.0

        @staticmethod
        def clock():
            return 9.5

    assert _echoing(A)
    A.clock = staticmethod(lambda: 10.5)
    assert not _echoing(A)


# -- Blender: image + prompt, surgical edits, CAD -------------------------------------------
def test_image_plus_prompt_and_surgical_edit_orders():
    assert parse_quick("modela esta imagen en blender y cámbiale el color del asa a rojo").kind == "blender_image"
    assert image_edit_parts("modela esta imagen en blender y cámbiale el color del asa a rojo") == ("", "cámbiale el color del asa a rojo")
    assert image_edit_parts(r"pasa la foto C:\Users\x\silla.png a blender y ponle cojines") == (r"C:\Users\x\silla.png", "ponle cojines")
    q = parse_quick("en blender, haz el asa más grande")
    assert q.kind == "blender_edit" and q.arg == "haz el asa más grande"
    assert parse_quick("haz en blender una silla").kind == "blender_task"
    assert parse_quick("pasa esta imagen a DXF de 20 cm").kind == "cad_image"
    assert parse_quick("haz los planos CAD del modelo").kind == "cad_model"


def test_vision_rank_prefers_what_looks_right():
    blocky = media.build_rank(20.0, {"score": 3})
    right = media.build_rank(8.0, {"score": 8})
    assert right > blocky and media.worse_build(blocky, right)
    assert media.build_rank(-1.0, {"score": 9}) == -1.0
    assert "8/10" in media.vision_sentence({"score": 8, "looks_like": "tetera", "is_it": True})
    assert "ojo" in media.vision_sentence({"score": 4, "looks_like": "caja", "is_it": False})


def test_review_log_drops_part_boxes_and_noise():
    log = "SERGIO_BBOX A | 0 0 0 | 1 1 1\nEGL Error x\nSERGIO_STEP_ERROR in asa(): boom\n"
    assert media.review_log(log) == "SERGIO_STEP_ERROR in asa(): boom"


def test_the_desktop_and_server_draw_the_same_edges():
    from openjarvis.tools.cad import EDGES_SCRIPT

    assert media.EDGES_SCRIPT == EDGES_SCRIPT


def test_find_image_takes_the_newest_picture(tmp_path):
    (tmp_path / "vieja.png").write_bytes(b"old")
    new = tmp_path / "nueva.jpg"
    new.write_bytes(b"new")
    data, where = media.find_image(folders=[tmp_path])
    assert data in (b"old", b"new") and where
    assert media.find_image(str(new))[0] == b"new"


# -- Blender add-ons ------------------------------------------------------------------------
def test_add_ons_come_from_their_github_releases():
    release = {"assets": [{"name": "meshgen-cuda-win64.zip", "browser_download_url": "U-cuda"},
                          {"name": "meshgen-cpu-win64.zip", "browser_download_url": "U-cpu"}]}
    assert ba.release_url("meshgen", gpu=False, get=lambda repo: release) == "U-cpu"
    assert ba.release_url("meshgen", gpu=True, get=lambda repo: release) == "U-cuda"
    assert ba.release_url("sculptmate", get=lambda repo: {}).endswith("SculptMate.zip")
    assert ba.release_url("img2mesh").endswith("ImageToMeshPlugin.py")


def test_install_scripts_enable_the_add_on_and_meshgen_thinks_with_gemini():
    ext = ba.install_script("C:/a/meshgen.zip", "meshgen")
    assert "package_install_files" in ext and "save_userpref" in ext
    legacy = ba.install_script("C:/a/SculptMate.zip", "sculptmate")
    assert "addon_install" in legacy and "addon_enable" in legacy
    conf = ba.meshgen_config_script("KEY")
    assert "'gemini/gemini-2.5-flash'" in conf and '"REMOTE"' in conf and "'KEY'" in conf
    assert 'numpy==' in ba.IMG2MESH_DEPS  # Blender's own numpy is never upgraded


def test_old_blender_is_told_instead_of_breaking(monkeypatch):
    monkeypatch.setattr(ba, "download", lambda url, folder=None: Path("x.zip"))
    assert "necesita Blender 4.2" in ba.install("meshgen", "3.6.5", run=lambda s: "")
    assert "instalado y activado" in ba.install("sculptmate", "4.2.0", run=lambda s: "SERGIO_ADDON_OK SculptMate")


def test_backgrounds_become_transparent_for_image_to_mesh():
    from PIL import Image

    img = Image.new("RGB", (40, 30), (255, 255, 255))
    for x in range(10, 30):
        for y in range(8, 22):
            img.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = Image.open(io.BytesIO(ba.transparent_png(buf.getvalue())))
    assert out.mode == "RGBA" and out.getpixel((0, 0))[3] == 0 and out.getpixel((20, 15))[3] == 255


@pytest.mark.parametrize("order, kind", [
    ("instala los complementos de blender", "blender_addons"),
    ("instala meshgen", "blender_addons"),
    ("hazme en 3D con Tripo un dragón de cristal", "tripo"),
    ("pasa esta imagen a 3D orgánico", "sculptmate"),
    ("convierte este logo en 3D técnico", "img2mesh"),
    ("instala RIFE", "rife_install"),
])
def test_add_on_orders(order, kind):
    assert parse_quick(order).kind == kind


# -- post-production -------------------------------------------------------------------------
def test_masters_are_10_bit_professional_codecs():
    pro = vm.master_command(Path("a.mp4"), Path("a.mov"), "prores", color=vm.color_chain(denoise=True, lut="C:/l.cube"))
    assert "prores_ks" in pro and "yuv422p10le" in pro and "pcm_s24le" in pro and "bt709" in pro
    chain = pro[pro.index("-vf") + 1]
    assert chain.startswith("format=yuv444p10le") and "hqdn3d" in chain and "lut3d=file='C\\\\:/l.cube'" in chain
    dnx = vm.master_command(Path("a.mp4"), Path("a.mov"), "dnxhr")
    assert "dnxhr_hqx" in dnx and "yuv422p10le" in dnx
    assert "yuv420p10le" in vm.master_command(Path("a"), Path("b.mp4"), "hevc10")


def test_rife_auto_editor_and_minterpolate_commands():
    cmd = vm.rife_command(Path("rife/rife-ncnn-vulkan"), Path("in"), Path("out"), 120, gpu=False)
    assert "rife-v4.6" in cmd and "120" in cmd and "-1" in cmd
    ae = vm.auto_editor_command(Path("t.mp4"), Path("o.mp4"), 0.04, 0.2)
    assert ae[1:5] == ["t.mp4", "--edit", "audio:threshold=0.04", "--margin"] and "--no-open" in ae
    assert "mi_mode=mci" in vm.minterpolate_filter(60)


@pytest.mark.parametrize("order, opts", [
    ("edita un video con la carpeta Viaje y quita los silencios", {"silences": True}),
    ("edita un video a 60 fps en cámara lenta", {"fps": 60, "slow": 2.0}),
    ("edita mi video y entrégame un máster ProRes para DaVinci", {"master": "prores"}),
    ("edita el video en DNxHR para Avid", {"master": "dnxhr"}),
])
def test_post_production_options_from_the_order(order, opts):
    got = vm.options_from(order)
    assert all(got.get(k) == v for k, v in opts.items())


def test_the_render_uses_transitions_zooms_speed_grade_and_kinetic_captions():
    plan = {"aspect": "9:16", "style": {"grade": {"contrast": 1.3, "warmth": -0.2, "vignette": True},
                                         "text": {"style": "bold caps", "kinetic": True, "color": "#FFD400"}},
            "segments": [
                {"clip": 0, "start": 0, "end": 2, "caption": "mira esto", "zoom": "punch", "speed": 1.0},
                {"clip": 0, "start": 3, "end": 5, "caption": "", "transition": "flash", "zoom": "push", "speed": 2.0}]}
    cmd = render_command([Path("a.mp4")], plan, Path("o.mp4"), has_audio=[True])
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fadewhite" in graph and "zoompan=" in graph and "setpts=(PTS-STARTPTS)/2" in graph
    assert "atempo=2" in graph and "eq=contrast=1.300" in graph and "vignette" in graph and "colorbalance" in graph
    assert "text='MIRA'" in graph and "text='MIRA ESTO'" in graph and "fontcolor=0xFFD400" in graph
    # the flash starts where the first moment ends (2 s), minus its own length
    assert re.search(r"fadewhite:duration=0\.22:offset=1\.780", graph)


def test_styles_named_in_the_order():
    assert style_named("edita un video con la carpeta Viaje al estilo Dyson para shorts") == "dyson"
    assert style_named("edita un video con la carpeta Viaje") == ""
    assert parse_quick("aprende el estilo de edición de NextCore").kind == "video_style_learn"
    assert parse_quick("qué estilos de video conoces").kind == "video_styles"


# -- memory and the crew ------------------------------------------------------------------------
def test_feedback_and_crew_orders():
    assert parse_quick("eso quedó mal, el asa es muy gruesa").kind == "feedback"
    assert quick.feedback_rating("no me gustó, muy lento") == -1 and quick.feedback_rating("me gustó") == 1
    q = parse_quick("usa el equipo de agentes para escribir un informe sobre el sueño")
    assert q.kind == "crew" and q.arg == "escribir un informe sobre el sueño"

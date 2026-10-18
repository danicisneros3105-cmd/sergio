"""Creator: anatomy figures, design layouts, cut-outs, plans and code."""

from __future__ import annotations

import json
import shutil

import pytest

from openjarvis.creator import anatomy_build as ab
from openjarvis.creator import studio
from openjarvis.creator.llm import CreatorError

has_node = shutil.which("node") is not None


@pytest.mark.skipif(not has_node, reason="Node.js not installed")
def test_an_example_figure_builds_once_and_is_served(tmp_path):
    page = ab.build_example("dial-indicator", root=tmp_path)
    assert page.exists() and page.stat().st_size > 50_000
    stamp = page.stat().st_mtime
    assert ab.build_example("dial-indicator", root=tmp_path).stat().st_mtime == stamp
    assert ab.page_path("dial-indicator", root=tmp_path) == page
    assert ab.page_path("../../etc/passwd", root=tmp_path) is None


def test_figure_scripts_that_do_more_than_draw_are_refused():
    kit = 'import * as k from "../../kit/iso-kit.mjs";\n'
    for bad in (
        kit + 'import { execSync } from "node:child_process";',
        kit + 'await fetch("https://example.test");',
        kit + "const key = process.env.GEMINI_API_KEY;",
        kit + 'eval("1");',
        kit + 'readFileSync("/etc/passwd");',
        "console.log('no kit')",
    ):
        with pytest.raises(CreatorError):
            ab.check_script(bad)
    assert ab.check_script(kit + "k.iso([0, 0, 0], P);")


@pytest.mark.skipif(not has_node, reason="Node.js not installed")
def test_a_new_figure_retries_with_nodes_error_until_it_builds(tmp_path):
    template = (ab.KIT_ROOT / "examples" / "dial-indicator" / "build.mjs").read_text()
    good = template.replace(
        '`${theme === "light" ? "dial-indicator-light" : "dial-indicator"}.html`',
        '"figure.html"',
    )
    good = good.replace('"dial-indicator-light.html"', '"figure.html"').replace(
        '"dial-indicator.html"', '"figure.html"'
    )
    answers = [
        '```js\nimport * as k from "../../kit/iso-kit.mjs";\nthrow new Error("roto");\n```',
        f"```js\n{good}\n```",
    ]
    prompts = []

    def ask(prompt, **_kw):
        prompts.append(prompt)
        return answers[len(prompts) - 1]

    if "figure.html" not in good:
        pytest.skip("template writes its page differently")
    out = ab.create("Cómo funciona un comparador de cuadrante", root=tmp_path, ask=ask)
    assert out["attempts"] == 2
    assert "roto" in prompts[1]  # Node's error went back to the writer
    assert ab.page_path(out["name"], root=tmp_path)


def test_design_layouts_are_checked_field_by_field():
    raw = json.dumps(
        {
            "background": "#fff",
            "elements": [
                {
                    "type": "text",
                    "x": 10,
                    "y": 20,
                    "text": "Café  Luna",
                    "size": 9999,
                    "color": "red",
                },
                {"type": "rect", "x": 0, "y": 0, "w": 5, "h": 5, "fill": "#123456"},
                {"type": "script", "x": 0, "y": 0},
            ],
        }
    )
    layout = studio.check_layout(raw, 1080, 1080)
    assert layout["background"] == "#ffffff"
    text = layout["elements"][0]
    assert (
        text["text"] == "Café Luna"
        and text["size"] == 400
        and text["color"] == "#0f1222"
    )
    assert [e["type"] for e in layout["elements"]] == ["text", "rect"]
    with pytest.raises(ValueError):
        studio.check_layout('{"elements": []}', 100, 100)


def test_cutout_keeps_the_subject_and_clears_the_background():
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    img = np.full((240, 320, 3), 235, np.uint8)
    cv2.circle(img, (160, 120), 70, (40, 70, 210), -1)
    png, method = studio.cutout_detail(
        cv2.imencode(".jpg", img)[1].tobytes(), neural=False
    )
    out = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    assert method == "grabcut"
    assert out.shape[2] == 4 and out[120, 160, 3] == 255 and out[5, 5, 3] == 0


def test_cutout_uses_the_network_and_falls_back_when_it_is_missing(monkeypatch):
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    from openjarvis.creator import segment

    img = np.full((120, 160, 3), 235, np.uint8)
    cv2.rectangle(img, (40, 30), (120, 90), (20, 40, 200), -1)
    data = cv2.imencode(".png", img)[1].tobytes()

    def fake_alpha(image):
        a = np.zeros(image.shape[:2], np.float32)
        a[30:91, 40:121] = 1.0
        return a

    monkeypatch.setattr(segment, "alpha", fake_alpha)
    png, method = studio.cutout_detail(data)
    out = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    assert method == "red" and out[60, 80, 3] == 255 and out[5, 5, 3] == 0

    def offline(image):
        raise OSError("sin internet")

    monkeypatch.setattr(segment, "alpha", offline)
    assert studio.cutout_detail(data)[1] == "grabcut"


def test_segmentation_model_is_verified_before_use(tmp_path, monkeypatch):
    from openjarvis.creator import segment

    class Resp:
        def __init__(self):
            self.done = False

        def read(self, n):
            if self.done:
                return b""
            self.done = True
            return b"not the model"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(segment.urllib.request, "urlopen", lambda *a, **k: Resp())
    with pytest.raises(RuntimeError, match="huella"):
        segment.ensure_model(tmp_path)
    assert not list(tmp_path.iterdir())  # nothing half-downloaded is kept


def test_floor_plan_exports_walls_doors_and_dimensions():
    pytest.importorskip("ezdxf")
    dxf = studio.plan_dxf(
        [
            {"x1": 0, "y1": 0, "x2": 5, "y2": 0},
            {"x1": 5, "y1": 0, "x2": 5, "y2": 4, "thickness": 0.3},
        ],
        [{"x": 2.5, "y": 0, "kind": "puerta"}],
    ).decode()
    assert "MUROS" in dxf and "HUECOS" in dxf and "COTAS" in dxf and "LWPOLYLINE" in dxf
    with pytest.raises(CreatorError):
        studio.plan_dxf([])


def test_code_projects_stay_inside_and_run_bounded(tmp_path):
    files = studio.list_files(tmp_path)
    assert files and files[0]["path"].endswith(".py")
    run = studio.run_file(files[0]["path"], tmp_path)
    assert run["code"] == 0 and "Creator funciona" in run["stdout"]
    studio.save_file("demo/bucle.py", "while True:\n    pass\n", tmp_path)
    slow = studio.run_file("demo/bucle.py", tmp_path, timeout=1.0)
    assert slow["timed_out"]
    for bad in ("../fuera.py", "/etc/passwd"):
        with pytest.raises(CreatorError):
            studio.read_file(bad, tmp_path)
    with pytest.raises(CreatorError):
        studio.save_file("demo/virus.exe", "x", tmp_path)


def test_ai_edit_returns_the_whole_new_file():
    def ask(prompt, check=None, **_kw):
        text = "Aquí está:\n```python\nprint('hola, señor')\n```"
        check(text)
        return text

    out = studio.ai_edit("a.py", "print('hola')", "salúdame como señor", ask=ask)
    assert out.strip() == "print('hola, señor')"


def test_heavy_example_opens_at_once_from_its_shipped_build(tmp_path, monkeypatch):
    from openjarvis.creator import anatomy_build

    def no_node(*a, **k):
        raise AssertionError("Node should not run for a shipped, matching build")

    monkeypatch.setattr(anatomy_build, "_run", no_node)
    for light in (False, True):
        page = anatomy_build.build_example("raptor-engine", light, tmp_path)
        assert page.stat().st_size > 100_000
        assert page.with_suffix(".sha256").exists()
    # a changed recipe no longer matches the shipped build: Node must run
    script = tmp_path / "examples" / "raptor-engine" / "build.mjs"
    script.write_text(script.read_text() + "\n// edited\n")
    (tmp_path / "examples" / "raptor-engine" / "raptor-engine.html").unlink()
    with pytest.raises(AssertionError, match="Node should not run"):
        anatomy_build.build_example("raptor-engine", False, tmp_path)


def test_professional_apps_tool_runs_creator_engines(tmp_path):
    pytest.importorskip("ezdxf")
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    from openjarvis.tools.professional import ProfessionalAppsTool

    tool = ProfessionalAppsTool()
    dxf_out = tmp_path / "plano.dxf"
    res_dxf = tool.execute(
        action="plan_dxf",
        path=str(dxf_out),
        walls=[
            {"x1": 0, "y1": 0, "x2": 5, "y2": 0},
            {"x1": 5, "y1": 0, "x2": 5, "y2": 4},
        ],
        openings=[{"x": 2.5, "y": 0, "kind": "puerta"}],
    )
    assert res_dxf.success and dxf_out.exists() and ".dxf" in res_dxf.content

    img = np.full((160, 200, 3), 240, np.uint8)
    cv2.circle(img, (100, 80), 45, (30, 60, 210), -1)
    src = tmp_path / "sujeto.png"
    cv2.imwrite(str(src), img)
    res_cut = tool.execute(action="image_cutout", path=str(src))
    assert res_cut.success and (tmp_path / "sujeto-recorte.png").exists()

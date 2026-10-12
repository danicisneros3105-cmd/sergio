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
    png = studio.cutout(cv2.imencode(".jpg", img)[1].tobytes())
    out = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    assert out.shape[2] == 4 and out[120, 160, 3] == 255 and out[5, 5, 3] == 0


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

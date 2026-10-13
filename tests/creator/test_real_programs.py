"""Creator on real programs: the IFC building, Kronos, OpenDesign, the program
list and its routes, the supervisor services and the hidden Anatomy skill."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from openjarvis.creator import bim, kronos, opendesign, programs
from openjarvis.creator.llm import CreatorError

WALLS = [
    {"x1": 0, "y1": 0, "x2": 5, "y2": 0},
    {"x1": 5, "y1": 0, "x2": 5, "y2": 4},
    {"x1": 5, "y1": 4, "x2": 0, "y2": 4},
    {"x1": 0, "y1": 4, "x2": 0, "y2": 0, "thickness": 0.3},
]


# -- IFC (BIM) ----------------------------------------------------------------------
def test_plan_becomes_an_ifc_building_with_cut_openings(tmp_path):
    ifcopenshell = pytest.importorskip("ifcopenshell")
    data = bim.plan_ifc(
        WALLS,
        [
            {"x": 2.5, "y": 0, "width": 0.9, "kind": "puerta"},
            {"x": 5, "y": 2, "width": 1.2, "kind": "ventana"},
            {"x": 40, "y": 40, "width": 1},  # not on any wall: skipped
        ],
    )
    path = tmp_path / "plano.ifc"
    path.write_bytes(data)
    model = ifcopenshell.open(str(path))
    assert model.schema == "IFC4"
    assert len(model.by_type("IfcWall")) == 4
    assert len(model.by_type("IfcDoor")) == 1
    assert len(model.by_type("IfcWindow")) == 1
    assert len(model.by_type("IfcRelVoidsElement")) == 2
    assert len(model.by_type("IfcRelFillsElement")) == 2
    storey = model.by_type("IfcBuildingStorey")[0]
    contained = {e for rel in storey.ContainsElements for e in rel.RelatedElements}
    assert {w.id() for w in model.by_type("IfcWall")} <= {e.id() for e in contained}


def test_ifc_needs_walls():
    pytest.importorskip("ifcopenshell")
    with pytest.raises(CreatorError):
        bim.plan_ifc([{"x1": 0, "y1": 0, "x2": 0, "y2": 0}])


def test_openings_find_their_wall():
    clean = bim._clean_walls(WALLS)
    assert bim.nearest_wall(clean, 2.5, 0.05) == (0, pytest.approx(2.5))
    assert bim.nearest_wall(clean, 5.0, 2.0)[0] == 1
    assert bim.nearest_wall(clean, 2.5, 2.0) is None  # the middle of the room


# -- Kronos ---------------------------------------------------------------------------
def _candles(n: int, start: str = "2026-01-05") -> list[dict]:
    from datetime import date, timedelta

    day = date.fromisoformat(start)
    out = []
    for i in range(n):
        out.append(
            {
                "date": (day + timedelta(days=i)).isoformat(),
                "open": 100 + i,
                "high": 101 + i,
                "low": 99 + i,
                "close": 100.5 + i,
                "volume": 1000,
            }
        )
    return out


def test_price_history_parsers():
    yahoo = {
        "chart": {
            "result": [
                {
                    "timestamp": [1767571200, 1767657600, 1767744000],
                    "indicators": {
                        "quote": [
                            {
                                "open": [1.0, None, 3.0],
                                "high": [1.5, 2.5, 3.5],
                                "low": [0.5, 1.5, 2.5],
                                "close": [1.2, 2.2, 3.2],
                                "volume": [10, 20, None],
                            }
                        ]
                    },
                }
            ]
        }
    }
    rows = kronos.parse_yahoo(yahoo)
    assert [r["close"] for r in rows] == [1.2, 3.2]  # the day without data is skipped
    assert rows[1]["volume"] == 0.0
    csv_text = "Date,Open,High,Low,Close,Volume\n2026-01-05,1,2,0.5,1.5,100\n2026-01-06,x,2,1,1,1\n"
    assert kronos.parse_stooq(csv_text) == [
        {
            "date": "2026-01-05",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 100.0,
        }
    ]


def test_history_falls_back_to_stooq_and_rejects_bad_symbols():
    stooq = (
        "Date,Open,High,Low,Close,Volume\n"
        + "\n".join(f"2026-01-{d:02d},1,2,0.5,1.5,100" for d in range(1, 31)) * 3
    )

    def get(url: str):
        if "yahoo" in url:
            raise OSError("blocked")
        assert "s=aapl.us" in url
        return stooq

    assert len(kronos.history("aapl", get=get)) >= 60
    with pytest.raises(CreatorError):
        kronos.history("", get=get)
    with pytest.raises(CreatorError):
        kronos.history(
            "AAPL", get=lambda url: {"chart": {"result": []}} if "yahoo" in url else ""
        )


def test_future_days_skip_weekends_for_stocks_only():
    assert kronos.future_days("2026-10-09", 3, every_day=False) == [
        "2026-10-12",
        "2026-10-13",
        "2026-10-14",
    ]  # Friday -> next Mon, Tue, Wed
    assert kronos.future_days("2026-10-09", 2, every_day=True) == [
        "2026-10-10",
        "2026-10-11",
    ]


def test_install_steps_use_uv_and_keep_an_existing_python(tmp_path):
    steps = kronos.install_steps(tmp_path, "/usr/bin/uv", "/usr/bin/git")
    names = [s for s, _ in steps]
    assert names[0] == "Descargando Kronos" and "Preparando su Python" in names
    torch = next(cmd for s, cmd in steps if "PyTorch" in s)
    assert kronos.TORCH_INDEX in torch
    py = kronos.python_path(tmp_path)
    py.parent.mkdir(parents=True)
    py.write_text("")
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    again = [s for s, _ in kronos.install_steps(tmp_path, None, "/usr/bin/git")]
    assert again[0] == "Actualizando Kronos" and "Preparando su Python" not in again


def test_install_reports_the_failing_step(tmp_path, monkeypatch):
    monkeypatch.setattr(kronos.shutil, "which", lambda n: f"/usr/bin/{n}")
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(
            returncode=1 if "torch" in cmd else 0, stderr="no space", stdout=""
        )

    with pytest.raises(CreatorError, match="PyTorch"):
        kronos.install(run=run, base=tmp_path)
    assert not kronos.installed(tmp_path)


def _ready(tmp_path: Path) -> None:
    (tmp_path / "repo" / "model").mkdir(parents=True)
    (tmp_path / "repo" / "model" / "kronos.py").write_text("")
    (tmp_path / ".ready").write_text("ok")


def test_forecast_needs_kronos_installed(tmp_path):
    with pytest.raises(CreatorError, match="Instalar Kronos"):
        kronos.forecast("AAPL", base=tmp_path, rows=_candles(80))


def test_forecast_runs_kronos_in_its_own_python(tmp_path):
    _ready(tmp_path)
    seen = {}

    def run(cmd, input, **kw):  # noqa: A002 - subprocess.run's name
        req = json.loads(input)
        seen.update(cmd=cmd, req=req, cwd=kw.get("cwd"))
        out = [
            {"date": d, "open": 1, "high": 2, "low": 0.5, "close": 120.0, "volume": 0}
            for d in req["future"]
        ]
        return SimpleNamespace(
            returncode=0, stdout="log line\n" + json.dumps({"forecast": out}), stderr=""
        )

    result = kronos.forecast(
        "aapl", horizon=5, base=tmp_path, rows=_candles(600), run=run
    )
    assert (
        seen["cmd"][0] == str(kronos.python_path(tmp_path)) and seen["cmd"][1] == "-I"
    )
    assert len(seen["req"]["rows"]) == 512  # Kronos-small's context
    assert seen["req"]["model"] == "NeoQuasar/Kronos-small"
    assert len(result["forecast"]) == 5 and result["symbol"] == "AAPL"
    assert result["change_pct"] == pytest.approx((120 - 699.5) / 699.5 * 100, abs=0.01)
    assert "no un consejo financiero" in result["note"]
    bad = lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="CUDA error")  # noqa: E731
    with pytest.raises(CreatorError, match="CUDA error"):
        kronos.forecast("AAPL", base=tmp_path, rows=_candles(80), run=bad)


def test_runner_talks_to_kronos_api(tmp_path):
    """kronos_runner.py with a stand-in for Kronos' own package."""
    pytest.importorskip("pandas")
    model = tmp_path / "repo" / "model"
    model.mkdir(parents=True)
    (model / "__init__.py").write_text(
        "import pandas as pd\n"
        "class KronosTokenizer:\n"
        "    @classmethod\n"
        "    def from_pretrained(cls, name): assert name.startswith('NeoQuasar/'); return cls()\n"
        "class Kronos(KronosTokenizer): pass\n"
        "class KronosPredictor:\n"
        "    def __init__(self, model, tokenizer, device, max_context): self.m = max_context\n"
        "    def predict(self, df, x_timestamp, y_timestamp, pred_len, **kw):\n"
        "        assert len(df) == len(x_timestamp) and pred_len == len(y_timestamp)\n"
        "        assert hasattr(x_timestamp, 'dt')\n"
        "        last = df.iloc[-1]\n"
        "        return pd.DataFrame([dict(last)] * pred_len, index=y_timestamp)\n"
    )
    req = {
        "repo": str(tmp_path / "repo"),
        "model": "NeoQuasar/Kronos-small",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 512,
        "rows": _candles(30),
        "future": ["2026-03-02", "2026-03-03"],
    }
    runner = Path(kronos.__file__).with_name("kronos_runner.py")
    done = subprocess.run(
        [sys.executable, "-I", str(runner)],
        input=json.dumps(req),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.strip().splitlines()[-1])["forecast"]
    assert [r["date"] for r in out] == req["future"]
    assert out[0]["close"] == pytest.approx(129.5)


# -- OpenDesign -----------------------------------------------------------------------
LAYOUT = {
    "background": "#f5ebe0",
    "elements": [
        {
            "type": "rect",
            "x": 40,
            "y": 40,
            "w": 1000,
            "h": 200,
            "fill": "#2b1a12",
            "radius": 24,
        },
        {"type": "circle", "x": 900, "y": 900, "r": 60, "fill": "#c67b4e"},
        {
            "type": "text",
            "x": 80,
            "y": 80,
            "w": 900,
            "text": "NUEVO CAFÉ",
            "size": 72,
            "weight": 800,
            "color": "#ffffff",
            "align": "center",
        },
    ],
}


def test_layout_becomes_opendesign_canvas_json():
    data = json.loads(opendesign.fabric_json(LAYOUT, 1080, 1080))
    assert data["version"] == "6.0.0" and data["background"] == "#f5ebe0"
    kinds = [o["type"] for o in data["objects"]]
    assert kinds == ["rect", "rect", "circle", "textbox"]
    assert (
        data["objects"][0]["width"] == 1080
    )  # full-size background, like its templates
    assert data["objects"][1]["rx"] == 24
    text = data["objects"][3]
    assert text["text"] == "NUEVO CAFÉ" and text["fontWeight"] == "800"
    assert text["textAlign"] == "center"


def test_create_design_posts_to_opendesign_and_explains_when_closed():
    sent = {}

    def post(url, payload):
        sent.update(url=url, payload=payload)
        return {"id": "abc", "name": payload["name"]}

    row = opendesign.create_design("Mi post", LAYOUT, 1080, 1350, post=post)
    assert row["id"] == "abc" and sent["url"].endswith("/api/designs")
    assert sent["payload"]["height"] == 1350
    assert json.loads(sent["payload"]["canvas_json"])["objects"]

    def down(url, payload):
        raise OSError("connection refused")

    with pytest.raises(CreatorError, match="OpenDesign no responde"):
        opendesign.create_design("x", LAYOUT, 1080, 1080, post=down)


# -- the program list -------------------------------------------------------------------
class FakeSup:
    def __init__(self, installed=True, running=False):
        self.rows = [
            {"name": "opendesign", "available": installed, "running": running},
            {"name": "vscodium", "available": installed, "running": False},
        ]
        self.started = []

    def status(self, creator=False):
        assert creator
        return self.rows

    def vscodium_token(self):
        return "tkn-123"

    def get(self, name):
        return SimpleNamespace(name=name)

    def start(self, svc, wait=60.0):
        self.started.append(svc.name)
        return "running at http://127.0.0.1:8790"

    def running(self, svc):
        return True


def test_status_merges_web_windows_and_kronos(monkeypatch):
    monkeypatch.setattr(programs, "_supervisor", lambda: FakeSup(running=True))
    monkeypatch.setattr(
        programs,
        "windows_status",
        lambda max_age=20.0: {
            "freecad": {"installed": True},
            "vscodium": {"installed": False},
        },
    )
    monkeypatch.setattr(
        programs.kronos,
        "status",
        lambda: {"installed": False, "installing": True, "step": "x", "error": ""},
    )
    rows = {r["id"]: r for r in programs.status(local=True)}
    assert rows["opendesign"]["installed"] and rows["opendesign"]["running"]
    assert rows["opendesign"]["port"] == 8790
    assert rows["vscodium"]["token"] == "tkn-123"
    assert rows["vscodium"]["windows"] == {
        "installed": False,
        "installing": False,
        "error": "",
        "reachable": True,
    }
    assert rows["freecad"]["installed"] and rows["freecad"]["reachable"]
    assert rows["kronos"]["installing"]
    remote = {r["id"]: r for r in programs.status(local=False)}
    assert "token" not in remote["vscodium"]  # never handed out beyond this PC


def test_windows_programs_go_through_sergio_escritorio(monkeypatch):
    calls = []
    monkeypatch.setattr(
        programs, "_desktop", lambda args: calls.append(args) or "Abriendo FreeCAD."
    )
    assert (
        programs.open_in_windows("freecad", "plano.ifc", b"ISO-10303")
        == "Abriendo FreeCAD."
    )
    assert calls[0]["action"] == "open" and calls[0]["name"] == "plano.ifc"
    import base64

    assert base64.b64decode(calls[0]["data"]) == b"ISO-10303"
    programs.install("artcraft")
    assert calls[-1] == {"action": "install", "app": "artcraft"}
    with pytest.raises(CreatorError):
        programs.open_in_windows("opendesign")
    with pytest.raises(CreatorError):
        programs.start("freecad")


def test_desktop_closed_means_unknown_not_crash(monkeypatch):
    def closed(args):
        raise RuntimeError("no responde")

    monkeypatch.setattr(programs, "_desktop", closed)
    programs._cache.update(at=0.0, windows=None)
    assert programs.windows_status(max_age=0) is None


def test_routes(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.creator.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    monkeypatch.setattr(
        programs, "status", lambda local: [{"id": "opendesign", "local": local}]
    )
    assert client.get("/v1/creator/programs").json() == {
        "programs": [{"id": "opendesign", "local": True}]
    }
    opened = []
    monkeypatch.setattr(
        programs,
        "open_in_windows",
        lambda pid, name="", data=None: opened.append((pid, name, data)) or "ok",
    )
    plan = {"walls": WALLS, "openings": []}
    r = client.post(
        "/v1/creator/plan/open", json={**plan, "program": "librecad", "kind": "dxf"}
    )
    assert (
        r.status_code == 200
        and opened[0][0] == "librecad"
        and opened[0][1] == "plano-sergio.dxf"
    )
    assert (
        client.post(
            "/v1/creator/plan/open", json={**plan, "program": "librecad", "kind": "ifc"}
        ).status_code
        == 400
    )
    if pytest.importorskip("ifcopenshell"):
        ifc = client.post("/v1/creator/plan/ifc", json=plan)
        assert ifc.status_code == 200 and ifc.content.startswith(b"ISO-10303-21")
    bad = client.post(
        "/v1/creator/programs/kdenlive/open-file", json={"name": "a.mp4", "data": "%%%"}
    )
    assert bad.status_code == 400


# -- supervisor services --------------------------------------------------------------
def test_creator_services_only_when_installed(tmp_path, monkeypatch):
    from openjarvis.core.config import JarvisConfig
    from openjarvis.unified import supervisor as sv

    monkeypatch.setattr(
        sv.Supervisor, "apps_dir", staticmethod(lambda: tmp_path / "apps")
    )
    monkeypatch.setattr(sv, "state_dir", lambda: tmp_path / "state")
    (tmp_path / "state").mkdir()
    sup = sv.Supervisor(JarvisConfig(), which=lambda n: f"/usr/bin/{n}")
    od, vs = sup.creator_services()
    assert od.problem and vs.problem
    assert "opendesign" not in [s.name for s in sup.services()]  # never started at boot
    (tmp_path / "apps" / "opendesign" / "dist").mkdir(parents=True)
    (tmp_path / "apps" / "opendesign" / "dist" / "index.html").write_text("<html>")
    server = tmp_path / "apps" / "vscodium-web" / "bin" / "codium-server"
    server.parent.mkdir(parents=True)
    server.write_text("#!/bin/sh")
    monkeypatch.setattr(
        "openjarvis.creator.studio.projects_root", lambda: tmp_path / "proyectos"
    )
    od, vs = sup.creator_services()
    assert not od.problem and "wrangler dev --port 8787" in od.command[2]
    assert od.command[2].index("/dev/tcp/127.0.0.1/8787") < od.command[2].index(
        "vite preview"
    )
    assert vs.command[0] == str(server) and "--connection-token-file" in vs.command
    token = tmp_path / "state" / "vscodium.token"
    assert token.read_text() and oct(token.stat().st_mode & 0o777) == "0o600"
    assert sup.vscodium_token() == token.read_text()
    assert sup.get("vscodium").name == "vscodium"
    assert {r["name"] for r in sup.status(creator=True)} >= {"opendesign", "vscodium"}


def test_csp_lets_the_web_embed_creator_programs():
    from openjarvis.server.middleware import content_security_policy

    csp = content_security_policy()
    assert "http://127.0.0.1:8790" in csp and "http://localhost:8791" in csp


# -- the hidden Anatomy skill -----------------------------------------------------------
def test_anatomy_lives_in_the_chat_not_in_a_section(monkeypatch):
    from openjarvis.creator import anatomy_build
    from openjarvis.persona import SERGIO_CHAT_PERSONA
    from openjarvis.tools.creator_tools import AnatomyFigureTool

    monkeypatch.setattr(anatomy_build, "build_example", lambda name: Path("/x.html"))
    out = AnatomyFigureTool().execute(action="build", name="raptor-engine")
    assert out.success and "/v1/creator/anatomy/view/raptor-engine" in out.content
    assert "Creator →" not in out.content
    spec = AnatomyFigureTool().spec.description
    assert "inside the chat" in spec and "Anatomía" in spec  # told never to mention it
    assert "anatomy_figure" in SERGIO_CHAT_PERSONA


def test_opendesign_spanish_patch():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    try:
        import opendesign_es
    finally:
        sys.path.pop(0)
    src = (
        '<h1 class="x">My Designs</h1>\n<button title="Zoom in">\n  New Design\n</button>\n'
        '{ key: "templates", label: "Templates" }\n{exporting ? "Preparing..." : "Export"}\n'
        'const key = "Export2"; // untouched\n<p>Pages ({pages.length})</p>'
    )
    out = opendesign_es.translate(src)
    assert ">Mis diseños<" in out and 'title="Acercar"' in out and "Nuevo diseño" in out
    assert '"Plantillas"' in out and '"Exportar"' in out and '"Export2"' in out
    assert "Páginas ({pages.length})" in out
    assert os.path.basename(opendesign_es.__file__) == "opendesign_es.py"

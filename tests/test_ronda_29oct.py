"""Owner, 29 Oct 2026: projects, cloud 3D, a logo for any connector, one
superskill instead of every schema, and a web build that never blocks an
update."""

from __future__ import annotations

import io
import json

import pytest

from openjarvis import proyectos as P

# -- projects ------------------------------------------------------------------------


def test_a_project_keeps_its_instructions_and_files_for_every_chat(tmp_path):
    p = P.create("Tienda de café", "Precios en dólares, tono cercano.", home=tmp_path)
    assert p["id"].startswith("p_") and p["archivos"] == []
    P.add_file(p["id"], "menu.md", "# Menú\nEspresso 2,50".encode(), home=tmp_path)
    P.add_file(p["id"], "../../fuera.txt", b"x", home=tmp_path)  # the name is cleaned
    got = P.get(p["id"], home=tmp_path)
    assert {f["nombre"] for f in got["archivos"]} == {"menu.md", "fuera.txt"}
    ctx = P.context(p["id"], home=tmp_path)
    assert (
        "Tienda de café" in ctx
        and "Precios en dólares" in ctx
        and "Espresso 2,50" in ctx
    )
    P.update(p["id"], home=tmp_path, instrucciones="Solo en inglés.")
    assert "Solo en inglés." in P.context(p["id"], home=tmp_path)
    P.delete(p["id"], home=tmp_path)
    assert P.all_projects(home=tmp_path) == []  # in the trash, not erased
    assert any((tmp_path / "proyectos" / ".papelera").iterdir())
    with pytest.raises(P.ProjectError):
        P.get("../etc", home=tmp_path)


def test_projects_over_http(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server.proyectos_routes import router

    monkeypatch.setattr(P, "root", lambda home=None: tmp_path / "proyectos")
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    made = c.post(
        "/v1/proyectos", json={"nombre": "Tesis", "instrucciones": "APA 7"}
    ).json()
    up = c.post(
        f"/v1/proyectos/{made['id']}/archivos",
        files={"archivo": ("notas.txt", io.BytesIO(b"capitulo uno"), "text/plain")},
    )
    assert up.status_code == 200 and up.json()["archivos"][0]["nombre"] == "notas.txt"
    ctx = c.get(f"/v1/proyectos/{made['id']}/contexto").json()["contexto"]
    assert "APA 7" in ctx and "capitulo uno" in ctx
    assert c.get("/v1/proyectos/p_0000000000").status_code == 404
    assert c.post("/v1/proyectos", json={"nombre": "  "}).status_code == 400


# -- the superskill ------------------------------------------------------------------


def _tools(n: int):
    from openjarvis.core.types import ToolResult
    from openjarvis.tools._stubs import BaseTool, ToolSpec

    made = []
    for i in range(n):

        class T(BaseTool):
            tool_id = f"tool{i}"
            _name = f"tool{i}"

            @property
            def spec(self):
                return ToolSpec(
                    name=self._name,
                    description=f"Does thing {self._name}. Long details follow here.",
                    parameters={
                        "type": "object",
                        "properties": {"x": {"type": "string"}},
                        "required": ["x"],
                    },
                )

            def execute(self, **params):
                return ToolResult(
                    tool_name=self._name,
                    content=f"{self._name}:{params['x']}",
                    success=True,
                )

        made.append(T())
    return made


def test_with_no_clear_neuron_one_superskill_stands_for_the_rest(monkeypatch):
    from openjarvis.core.types import ToolCall
    from openjarvis.tools import _stubs

    monkeypatch.setattr("openjarvis.connectome.brain.turn_tools", lambda: None)
    ex = _stubs.ToolExecutor(_tools(30))
    sent = ex.get_openai_tools()
    names = [t["function"]["name"] for t in sent]
    assert names == [_stubs.SUPERSKILL]  # none of the fakes is a core tool
    assert "tool7: Does thing tool7" in sent[0]["function"]["description"]
    # without arguments: the exact schema comes back
    first = ex.execute(
        ToolCall("1", _stubs.SUPERSKILL, json.dumps({"nombre": "tool7"}))
    )
    assert first.success and '"required": ["x"]' in first.content
    # with them: the real tool runs
    done = ex.execute(
        ToolCall(
            "2",
            _stubs.SUPERSKILL,
            json.dumps({"nombre": "tool7", "argumentos": {"x": "ok"}}),
        )
    )
    assert done.success and done.content == "tool7:ok"
    unknown = ex.execute(
        ToolCall("3", _stubs.SUPERSKILL, json.dumps({"nombre": "nada"}))
    )
    assert not unknown.success


def test_a_clear_neuron_still_gets_its_full_tools(monkeypatch):
    from openjarvis.tools import _stubs

    monkeypatch.setattr(
        "openjarvis.connectome.brain.turn_tools", lambda: {"tool1", "tool2"}
    )
    ex = _stubs.ToolExecutor(_tools(30))
    assert [t["function"]["name"] for t in ex.get_openai_tools()] == ["tool1", "tool2"]
    monkeypatch.setattr("openjarvis.connectome.brain.turn_tools", lambda: None)
    monkeypatch.setenv("SERGIO_SUPERHABILIDAD", "0")
    assert len(ex.get_openai_tools()) == 30


# -- cloud 3D ------------------------------------------------------------------------


def test_cloud_3d_tries_the_services_in_order_and_opens_in_the_viewer(
    tmp_path, monkeypatch
):
    from openjarvis.creator import despiece, nube3d

    monkeypatch.setattr(despiece, "root", lambda home=None: tmp_path / "despiece")
    glb = b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 64
    tried = []

    def broken():
        tried.append("meshy")
        raise RuntimeError("sin créditos")

    def works():
        tried.append("tripo")
        return glb

    meta = nube3d.generate(
        "un reloj de bolsillo antiguo", order=["meshy", "tripo"],
        runners={"meshy": broken, "tripo": works}, home=tmp_path,
    )  # fmt: skip
    assert tried == ["meshy", "tripo"] and meta["fuente"] == "Tripo"
    assert meta.get("name")
    with pytest.raises(nube3d.Nube3DError, match="MESHY_API_KEY"):
        nube3d.generate("algo", order=[])


def test_meshy_text_to_3d_does_the_preview_then_the_refine():
    from openjarvis.creator import nube3d

    calls = []

    class R:
        def __init__(self, data=None, content=b""):
            self._d, self.content = data or {}, content

        def raise_for_status(self):
            pass

        def json(self):
            return self._d

    class Http:
        def post(self, url, headers=None, json=None):
            calls.append(("post", json["mode"]))
            return R({"result": "t-" + json["mode"]})

        def get(self, url, headers=None):
            if url.endswith(".glb"):
                return R(content=b"glTF-model")
            return R({"status": "SUCCEEDED", "model_urls": {"glb": "https://x/m.glb"}})

    out = nube3d.meshy("a vintage car", http=Http(), sleep=lambda s: None)
    assert out == b"glTF-model" and calls == [("post", "preview"), ("post", "refine")]


# -- a logo for any connector --------------------------------------------------------


def _png(colour=(220, 30, 60)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (48, 48), colour).save(buf, "PNG")
    return buf.getvalue()


def test_an_unknown_connector_gets_its_own_sites_icon_and_colour(tmp_path):
    from openjarvis.mcp import favicon

    assert favicon.site_of("https://mcp.higgsfield.ai/mcp") == "higgsfield.ai"
    pages = {
        "https://higgsfield.ai/": '<link rel="apple-touch-icon" sizes="180x180" href="/apple.png">',
        "https://higgsfield.ai/apple.png": _png(),
    }

    class R:
        def __init__(self, body):
            self.status_code = 200
            self.text = body if isinstance(body, str) else ""
            self.content = body if isinstance(body, bytes) else body.encode()

    public = lambda host, port: [(None, None, None, None, ("93.184.216.34", port))]  # noqa: E731
    info = favicon.logo(
        "https://mcp.higgsfield.ai/mcp",
        tmp_path,
        get=lambda u: R(pages[u]),
        resolve=public,
    )
    assert info["site"] == "higgsfield.ai" and (tmp_path / info["file"]).exists()
    r, g, b = (int(info["hex"][i : i + 2], 16) for i in (0, 2, 4))
    assert r > 180 and g < 80  # the red of its icon
    # cached: no new reads
    assert (
        favicon.logo(
            "https://mcp.higgsfield.ai/mcp", tmp_path, get=None, resolve=public
        )
        == info
    )


def test_local_and_private_addresses_never_fetch_a_logo(tmp_path):
    from openjarvis.mcp import favicon

    private = lambda host, port: [(None, None, None, None, ("192.168.1.5", port))]  # noqa: E731
    assert (
        favicon.logo(
            "https://intranet.miempresa.com/mcp",
            tmp_path,
            get=lambda u: 1 / 0,
            resolve=private,
        )
        == {}
    )
    assert (
        favicon.logo("http://localhost:3000/mcp", tmp_path, get=lambda u: 1 / 0) == {}
    )
    assert favicon.logo("https://10.0.0.1/mcp", tmp_path, get=lambda u: 1 / 0) == {}


# -- the web build -------------------------------------------------------------------


def test_the_server_prefers_the_local_web_build(tmp_path):
    from openjarvis.server import webroot

    local, tracked = tmp_path / "static_local", tmp_path / "static"
    assert webroot.web_dir(local, tracked) == tracked
    local.mkdir()
    (local / "index.html").write_text("new")
    assert webroot.web_dir(local, tracked) == local


# -- signing in with Sergio's own Face ID (no Windows Hello) ------------------------


def test_sergios_face_id_opens_the_owners_account_on_this_computer(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.faces import faceid
    from openjarvis.faces import routes as faces
    from openjarvis.server import accounts_routes as A

    class Gate:
        def passcode_reason(self):
            return ""

        def challenge(self):
            class C:
                def to_dict(self):
                    return {"nonce": "n1", "say": "Gire la cabeza"}

            return C()

    class Store:
        def users(self):
            return [{"id": "u2", "role": "aprobado"}, {"id": "u1", "role": "dueño"}]

    opened = []
    monkeypatch.setattr(faces, "_local_only", lambda request: None)
    monkeypatch.setattr(faces, "_get_gate", lambda: Gate())
    monkeypatch.setattr(faces, "_get_book", lambda: None)
    monkeypatch.setattr(faces, "_owner_key", lambda: "Daniel")
    monkeypatch.setattr(A, "_store", lambda: Store())
    monkeypatch.setattr(A, "_limit", lambda request: None)
    monkeypatch.setattr(
        A,
        "_signed_in",
        lambda user, device: (
            opened.append(user["id"]) or {"status": "dentro", "token": "sg_x"}
        ),
    )
    verdict = {"ok": True}
    monkeypatch.setattr(
        faceid, "unlock", lambda book, gate, nonce, frames, owner: verdict
    )
    app = FastAPI()
    app.include_router(A.router)
    c = TestClient(app)
    assert c.post("/v1/cuentas/cara/reto").json()["nonce"] == "n1"
    files = [("images", ("f0.jpg", b"jpg", "image/jpeg"))]
    got = c.post(
        "/v1/cuentas/cara/entrar", data={"nonce": "n1", "device": "PC"}, files=files
    ).json()
    assert got["status"] == "dentro" and opened == ["u1"]  # the owner's account
    verdict.update(ok=False, reason="No es usted.")
    assert (
        c.post("/v1/cuentas/cara/entrar", data={"nonce": "n1"}, files=files).json()[
            "status"
        ]
        == "no"
    )


# -- «entra a Amazon, inicia sesión y busca productos»: control of the real PC ----


def test_a_website_task_reaches_the_real_screen_tools():
    from openjarvis.connectome import neurons

    for ask in (
        "entra a amazon, inicia sesión y busca unos audífonos",
        "agrega al carrito unas zapatillas en mercado libre",
        "pon chrome y word lado a lado",
    ):
        sel = neurons.select(neurons.normalise(ask), {})
        assert sel is not None and "pantalla" in sel.neurons, ask
        assert "desktop_action" in sel.tools and "screen_read" in sel.tools


def test_sergio_never_says_he_is_only_a_language_model():
    from openjarvis import persona
    from openjarvis.speech import gemini_live

    text = " ".join(str(v) for v in vars(persona).values() if isinstance(v, str))
    assert "modelo de lenguaje" in text and "operate" in text
    assert "Controlas la computadora" in gemini_live.INSTRUCTIONS

"""Artifacts: a self-contained page shown in the chat, with no way out."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.creator import routes
from openjarvis.server import auth_middleware
from openjarvis.tools import artefacto as A

PAGE = "<!doctype html><html><head><title>x</title></head><body><h1>Hola</h1><script>1+1</script></body></html>"


def test_everything_must_be_inside_the_file():
    assert A.problem(PAGE) == ""
    for bad in (
        '<script src="https://cdn.example.com/x.js"></script>',
        '<link rel="stylesheet" href="//fonts.googleapis.com/css">',
        "<style>@import url(https://x.test/a.css);</style>",
        "<div style=\"background:url('http://x.test/a.png')\"></div>",
    ):
        why = A.problem(f"<html><body>{bad}</body></html>")
        assert "dentro del archivo" in why, bad
    assert A.problem("<p>hi</p>") != ""  # too short to be a page
    assert "demasiado grande" in A.problem("<p>" + "x" * (A.MAX_BYTES + 10) + "</p>")
    assert (
        A.problem('<img src="data:image/png;base64,AAAA">' + "x" * 30) == ""
    )  # data: pictures are fine


def test_the_policy_is_put_first_and_forbids_the_network():
    doc = A.wrap("<h1>Solo un fragmento</h1>", "Mi cartel")
    assert doc.count(A.META) == 1 and "<title>Mi cartel</title>" in doc
    head = doc.index("<head>")
    assert doc.index(A.META) < doc.index("<h1>") and doc.index(A.META) > head
    assert "connect-src 'none'" in A.POLICY and "default-src 'none'" in A.POLICY
    assert A.wrap(PAGE).count(A.META) == 1
    assert A.inject_policy(A.wrap(PAGE)).count(A.META) == 1  # never twice
    assert A.inject_policy("<p>sin cabeza</p>").startswith(A.META)


def test_the_tool_saves_the_file_and_leaves_the_mark_for_the_card(
    tmp_path, monkeypatch
):
    from openjarvis.creator import studio

    monkeypatch.setattr(studio, "projects_root", lambda root=None: tmp_path)
    res = A.ArtifactTool().execute(titulo="Mi página", html=PAGE, tipo="pagina")
    assert (
        res.success
        and "[[artefacto:artefacto-" in res.content
        and "|Mi página]]" in res.content
    )
    saved = list((tmp_path / "artefactos").glob("artefacto-*.html"))
    assert len(saved) == 1 and A.META in saved[0].read_text()
    bad = A.ArtifactTool().execute(
        titulo="x", html='<script src="https://x.test/a.js"></script>' + "y" * 30
    )
    assert not bad.success and "dentro del archivo" in bad.content
    assert (
        len(list((tmp_path / "artefactos").glob("*.html"))) == 1
    )  # the refused one was not saved


def test_the_frame_can_open_the_file_without_the_key_and_nothing_else_html():
    ok = "/v1/creator/artefacto/artefacto-" + "a1" * 12 + ".html"
    assert auth_middleware._OPEN_MEDIA.fullmatch(ok)
    assert not auth_middleware._OPEN_MEDIA.fullmatch(
        "/v1/creator/artefacto/guess.html"
    )  # not guessable
    assert not auth_middleware._OPEN_MEDIA.fullmatch(
        "/v1/creator/media/artefacto-" + "a1" * 12 + ".html"
    )


def test_the_route_serves_it_with_the_policy_and_refuses_odd_names(
    tmp_path, monkeypatch
):
    from openjarvis.creator import studio

    monkeypatch.setattr(studio, "projects_root", lambda root=None: tmp_path)
    folder = tmp_path / "artefactos"
    folder.mkdir()
    name = "artefacto-" + "b2" * 12 + ".html"
    (folder / name).write_text(
        "<html><head></head><body>hola</body></html>"
    )  # a file without the policy
    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)
    r = c.get(f"/v1/creator/artefacto/{name}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert A.META in r.text  # put back at serving time
    assert c.get("/v1/creator/artefacto/no-existe.html").status_code == 404
    assert c.get("/v1/creator/artefacto/..%2Fx.html").status_code in (400, 404)
    assert c.get("/v1/creator/artefacto/x.png").status_code == 400


@pytest.mark.parametrize("tool", ["artefacto"])
def test_the_tool_is_always_at_hand_and_the_persona_asks_for_it(tool):
    from openjarvis.connectome import neurons
    from openjarvis.persona import SERGIO_SUPERSKILLS

    assert tool in neurons.CORE
    assert "`artefacto`" in SERGIO_SUPERSKILLS

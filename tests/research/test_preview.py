"""Link previews: read from the page's own tags, only public sites, cached a day."""

from __future__ import annotations

import pytest

from openjarvis.research import preview as P
from openjarvis.server.auth_middleware import _OPEN_MEDIA

PAGE = """<html><head><title>Plain title</title>
<meta property="og:title" content="Cómo grabar con el teléfono &amp; luz natural">
<meta name="description" content="Una guía corta.">
<meta property="og:image" content="/img/portada.jpg">
<meta property="og:site_name" content="Revista">
</head><body>hola</body></html>"""


class R:
    def __init__(self, url, text="", content=b"", kind="text/html"):
        self.url, self.text, self.content = url, text, content
        self.headers = {"content-type": kind}


def _get(url, **kw):
    if url.endswith(".jpg"):
        return R(url, content=b"\xff\xd8" + b"0" * 500, kind="image/jpeg")
    return R(url, PAGE)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_home", lambda: tmp_path)
    return tmp_path


def test_parse_reads_open_graph_and_resolves_the_picture():
    d = P.parse(PAGE, "https://www.revista.com/notas/1")
    assert d["title"] == "Cómo grabar con el teléfono & luz natural"
    assert d["description"] == "Una guía corta."
    assert d["image"] == "https://www.revista.com/img/portada.jpg"
    assert d["site"] == "Revista" and d["host"] == "revista.com"


def test_preview_keeps_the_picture_and_caches(home):
    calls = []

    def get(url, **kw):
        calls.append(url)
        return _get(url)

    d = P.preview(
        "https://revista.com/notas/1", get=get, is_public=lambda h: True, now=1000
    )
    assert d["picture"].startswith("/v1/vista-previa/img/") and d["picture"].endswith(
        ".jpg"
    )
    name = d["picture"].rsplit("/", 1)[1]
    assert P.image_file(name) is not None and _OPEN_MEDIA.fullmatch(d["picture"])
    again = P.preview(
        "https://revista.com/notas/1", get=get, is_public=lambda h: True, now=2000
    )
    assert (
        again["title"] == d["title"] and len(calls) == 2
    )  # page + picture, then the cache


def test_only_public_web_pages(home):
    with pytest.raises(ValueError):
        P.preview("file:///etc/passwd", get=_get, is_public=lambda h: True)
    with pytest.raises(ValueError):
        P.preview("http://192.168.1.1/admin", get=_get, is_public=lambda h: False)
    assert P.image_file("../../etc/passwd") is None


def test_a_redirect_to_a_private_address_is_refused(home):
    def get(url, **kw):
        return R("http://10.0.0.5/", PAGE)

    with pytest.raises(ValueError):
        P.preview(
            "https://revista.com/x", get=get, is_public=lambda h: h == "revista.com"
        )

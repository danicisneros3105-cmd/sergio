"""Sergio's own browser: saved sites, background reading, and the steps that wait."""

from __future__ import annotations

import contextlib

import pytest

from openjarvis.asistente import navegador as nav


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(nav, "home", lambda: tmp_path)
    return tmp_path


class _Loc:
    def __init__(self, page, text=""):
        self.page, self.text = page, text

    @property
    def first(self):
        return self

    def is_visible(self, timeout=0):
        return self.page.password

    def click(self, timeout=0):
        self.page.clicked.append(self.text)
        self.page.body = self.page.pages.get(self.text, self.page.body)

    def get_attribute(self, name, timeout=0):
        return "text"

    def fill(self, value, timeout=0):
        self.page.typed.append(value)


class _Page:
    def __init__(
        self, body="Inicio", password=False, url="https://aula.test/", pages=None
    ):
        self.body, self.password, self.url = body, password, url
        self.pages = pages or {}
        self.clicked, self.typed = [], []

    def goto(self, url, timeout=0):
        self.url = url

    def wait_for_load_state(self, *a, **k):
        pass

    def locator(self, sel):
        return _Loc(self)

    def get_by_text(self, text, exact=False):
        return _Loc(self, text)

    def get_by_label(self, text):
        return _Loc(self, text)

    def evaluate(self, js):
        return self.body

    def title(self):
        return "Aula"


def _launcher(page):
    class Ctx:
        pages = [page]

        def close(self):
            pass

    class PW:
        class chromium:  # noqa: N801
            @staticmethod
            def launch_persistent_context(path, headless=True, **kw):
                assert headless  # never takes the screen
                return Ctx()

    @contextlib.contextmanager
    def launch():
        yield PW()

    return launch


def test_saved_sites_are_found_by_how_people_say_them():
    nav.save_site("Plataforma del colegio", "https://aula.colegio.test/")
    assert nav.resolve("la plataforma de mi colegio") == "https://aula.colegio.test/"
    assert nav.resolve("https://otra.test") == "https://otra.test"
    with pytest.raises(nav.NavegadorError, match="Dígame su dirección"):
        nav.resolve("mi banco")
    with pytest.raises(nav.NavegadorError):
        nav.save_site("x", "ftp://no")
    assert nav.forget_site("Plataforma del colegio") and not nav.sites()


def test_reads_a_page_in_the_background_following_steps():
    nav.save_site("colegio", "https://aula.test/")
    page = _Page(pages={"Tareas": "Tareas pendientes\nMatemáticas: entrega jueves"})
    got = nav.check("colegio", [{"clic": "Tareas"}], launcher=_launcher(page))
    assert got["estado"] == "leido" and "Matemáticas" in got["texto"]
    assert page.clicked == ["Tareas"]


def test_final_steps_and_passwords_wait_for_the_person():
    page = _Page()
    got = nav.check(
        "https://aula.test/", [{"clic": "Enviar tarea"}], launcher=_launcher(page)
    )
    assert got["estado"] == "espera_su_si" and page.clicked == []
    for word in (
        "Pagar",
        "Comprar ahora",
        "Confirmar reserva",
        "Publicar",
        "Eliminar",
        "Place order",
    ):
        assert nav.FINAL.search(word), word
    for word in ("Tareas", "Calificaciones", "Ordenar por fecha", "Posts"):
        assert not nav.FINAL.search(word), word


def test_a_page_that_asks_for_a_password_says_so():
    page = _Page(password=True, url="https://aula.test/login")
    got = nav.check("https://aula.test/", launcher=_launcher(page))
    assert got["estado"] == "necesita_sesion"

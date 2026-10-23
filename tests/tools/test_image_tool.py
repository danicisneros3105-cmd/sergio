"""«Haz una imagen»: Sergio's own image path, with services after Gemini."""

from __future__ import annotations

import pytest

from openjarvis.creator import studio
from openjarvis.creator.llm import CreatorError
from openjarvis.tools.image_tool import ImageGenerateTool

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture(autouse=True)
def _projects(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "projects_root", lambda root=None: tmp_path)


def test_spec_is_simple():
    spec = ImageGenerateTool().spec
    assert spec.name == "image_generate"
    assert spec.parameters["required"] == ["prompt"]


def test_no_prompt():
    result = ImageGenerateTool().execute(prompt="")
    assert not result.success


def test_the_picture_is_saved_and_shown_in_the_chat(monkeypatch, tmp_path):
    monkeypatch.setattr(studio, "generate_image", lambda prompt: PNG)
    result = ImageGenerateTool().execute(prompt="un gato con sombrero")
    assert result.success
    assert "](/v1/creator/media/imagen-" in result.content
    from openjarvis.server.auth_middleware import AuthMiddleware

    url = result.metadata["url"]
    assert not AuthMiddleware._requires_auth(url)  # the chat's <img> can show it
    assert AuthMiddleware._requires_auth("/v1/creator/media/imagen-123456.png")
    saved = list((tmp_path / "imagenes").iterdir())
    assert saved and saved[0].read_bytes() == PNG


def test_a_free_gemini_key_falls_back_to_the_next_service(monkeypatch):
    def no_quota(parts, client=None):
        raise CreatorError(
            "Su clave de Gemini no tiene cuota para generar imágenes ahora."
        )

    monkeypatch.setattr(studio, "_image_call", no_quota)
    monkeypatch.setattr(
        studio,
        "FALLBACKS",
        (
            ("OpenAI", lambda p: (_ for _ in ()).throw(CreatorError("sin clave"))),
            ("libre", lambda p: PNG),
        ),
    )
    assert studio.generate_image("un faro de noche") == PNG


def test_when_nothing_works_it_says_what_to_do(monkeypatch):
    def no_quota(parts, client=None):
        raise CreatorError(
            "Su clave de Gemini no tiene cuota para generar imágenes ahora."
        )

    def down(prompt):
        raise RuntimeError("503")

    monkeypatch.setattr(studio, "_image_call", no_quota)
    monkeypatch.setattr(studio, "FALLBACKS", (("libre", down),))
    result = ImageGenerateTool().execute(prompt="un faro")
    assert not result.success
    assert "cuota" in result.content and "HF_TOKEN" in result.content
    assert "libre: 503" in result.content

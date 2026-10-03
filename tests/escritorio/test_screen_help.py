"""Clicky-style screen help: look at the screen, answer, point at the spot."""

import json

import httpx
import pytest
from sergio_escritorio.control import Controller
from sergio_escritorio.voice import (
    Assistant,
    SergioClient,
    target_point,
    to_wav,
    wants_camera,
    wants_screen,
)

from openjarvis.server import vision_routes

WAV = to_wav([b"\x00\x00" * 1600])


@pytest.mark.parametrize(
    ("text", "screen"),
    [
        ("¿Dónde está el botón de exportar?", True),
        ("¿qué es esto?", True),
        ("Explícame esto", True),
        ("¿Qué hay en mi pantalla?", True),
        ("¿Qué botón presiono para guardar?", True),
        ("Abre Google y busca Nvidia", False),
        ("Haz clic en guardar en esta ventana", False),
        ("¿Qué tengo en la mano?", False),
        ("¿Qué hora es?", False),
    ],
)
def test_wants_screen(text, screen):
    assert wants_screen(text) is screen


def test_hand_question_still_uses_the_camera():
    assert wants_camera("¿Qué tengo en la mano?")
    assert not wants_camera("¿Qué es esto?")  # that one is about the screen


def test_parse_reply_tolerates_fences_and_plain_text():
    fenced = (
        '```json\n{"answer": "Pulsa Exportar.", "element": "3", '
        '"label": "Exportar"}\n```'
    )
    assert vision_routes.parse_reply(fenced) == {
        "answer": "Pulsa Exportar.",
        "element": 3,
        "x": None,
        "y": None,
        "label": "Exportar",
    }
    plain = vision_routes.parse_reply("Es una hoja de cálculo.")
    assert plain["answer"] == "Es una hoja de cálculo." and plain["element"] is None


def test_target_point_prefers_the_element_and_scales_back():
    elements = [{"id": 3, "x": 100, "y": 50}]
    assert target_point({"element": 3}, elements, 2.0) == (200, 100)
    assert target_point({"element": 9, "x": 10, "y": 20}, elements, 2.0) == (20, 40)
    assert target_point({"element": None}, elements, 2.0) is None


def test_screen_endpoint(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.tools import vision_look

    seen = {}

    def fake_ask(image, prompt, http=None, mime="image/jpeg"):
        seen.update(prompt=prompt, mime=mime)
        return '{"answer": "Arriba a la derecha.", "element": 2, "label": "Compartir"}'

    monkeypatch.setattr(vision_look, "ask_image", fake_ask)
    app = FastAPI()
    app.include_router(vision_routes.router)
    resp = TestClient(app).post(
        "/v1/vision/screen",
        data={
            "question": "¿dónde comparto?",
            "elements": json.dumps(
                [{"id": 2, "type": "Button", "name": "Compartir", "x": 5, "y": 6}]
            ),
        },
        files={"image": ("p.png", b"\x89PNG", "image/png")},
    )
    assert resp.status_code == 200 and resp.json()["element"] == 2
    assert "2. Button 'Compartir' @5,6" in seen["prompt"]
    assert "¿dónde comparto?" in seen["prompt"] and seen["mime"] == "image/png"


def test_controller_snapshot_puts_elements_in_screenshot_pixels(desktop):
    png, elements, scale = Controller(desktop).snapshot()
    assert png.startswith(b"\x89PNG") and scale == 2.0  # 2560 px wide -> 1280
    assert elements[0]["id"] == 1 and (elements[0]["x"], elements[0]["y"]) == (100, 60)


def test_assistant_answers_about_the_screen_and_points():
    calls, points, played = [], [], []

    def handler(request):
        path = request.url.path
        if path == "/v1/speech/transcribe":
            return httpx.Response(200, json={"text": "Sergio, ¿dónde está exportar?"})
        if path == "/v1/vision/screen":
            calls.append(request.content)
            return httpx.Response(
                200,
                json={
                    "answer": "Aquí, en Archivo.",
                    "element": 1,
                    "x": None,
                    "y": None,
                    "label": "Exportar",
                },
            )
        if path == "/v1/speech/synthesize":
            return httpx.Response(200, content=b"RIFFvoz")
        return httpx.Response(404)

    client = SergioClient(
        "http://sergio.test", http=httpx.Client(transport=httpx.MockTransport(handler))
    )

    class UI:
        def __init__(self):
            self.captions = []

        def state(self, _name):
            pass

        def say(self, text):
            self.captions.append(text)

    ui = UI()
    a = Assistant(
        client,
        ui=ui,
        player=played.append,
        chime=lambda f: None,
        screen=lambda: (b"\x89PNG", [{"id": 1, "x": 30, "y": 40}], 2.0),
        point=lambda x, y, label: points.append((x, y, label)),
    )
    a.on_utterance(WAV, addressed=False)
    assert points == [(60, 80, "Exportar")]
    assert ui.captions[-1] == "Aquí, en Archivo." and played == [b"RIFFvoz"]
    assert "dónde está exportar".encode() in calls[0]

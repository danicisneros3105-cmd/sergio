"""Naming one object from a close-up (any thing, not just 80 kinds)."""

from openjarvis.server.vision_routes import parse_name


def test_parse_name():
    reply = '```json\n{"etiqueta": "Labial", "detalle": "rojo, metálico", "seguridad": 0.9}\n```'
    assert parse_name(reply) == {
        "label": "Labial",
        "detail": "rojo, metálico",
        "confidence": 0.9,
    }
    assert parse_name('{"etiqueta": "objeto"}')["label"] == ""
    assert parse_name("no sé")["label"] == ""

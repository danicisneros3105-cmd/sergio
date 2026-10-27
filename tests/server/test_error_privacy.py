"""An unexpected error explains itself calmly; the technical detail (paths,
hosts, library messages) is shown only on the owner's own computer."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from openjarvis.cli.friendly import GEMINI_FIX, plain
from openjarvis.server.app import create_app


def _app():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    app = create_app(engine, "test-model")

    def boom():
        raise RuntimeError("secreto interno /home/dueño/.openjarvis")

    app.add_api_route("/v1/_boom", boom)
    # Ahead of the web app's catch-all, which is mounted last.
    app.router.routes.insert(0, app.router.routes.pop())
    return app


def test_the_fix_is_never_cut_in_half():
    text = plain(RuntimeError("Google rechazó la clave: API key not valid"))
    assert "sergio nube configurar --gemini TU_CLAVE" in text
    assert "\n" not in text and GEMINI_FIX.splitlines()[0] in text


def test_error_detail_only_on_the_owners_computer():
    client = TestClient(_app(), raise_server_exceptions=False)
    here = client.get("/v1/_boom").json()["detail"]
    assert "secreto interno" in here
    away = client.get("/v1/_boom", headers={"X-Forwarded-For": "203.0.113.9"})
    if away.status_code == 500:  # the outside guard may already refuse it
        assert "secreto interno" not in away.json()["detail"]

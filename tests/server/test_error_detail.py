"""Unexpected errors reach the user with their real reason, not a bare 500."""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server.app import create_app  # noqa: E402
from tests.server.test_routes import (  # noqa: E402
    _make_agent,
    _make_engine,
    _test_config,
)


def test_engine_error_is_explained():
    engine = _make_engine()
    agent = _make_agent()
    agent.run.side_effect = RuntimeError(
        'Ollama returned 500: {"error":"model requires more system memory (5.6 GiB) '
        'than is available (3.1 GiB)"}'
    )
    app = create_app(engine, "test-model", agent=agent, config=_test_config())
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "test-model", "messages": [{"role": "user", "content": "hola"}]},
    )
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert detail.startswith("RuntimeError: Ollama returned 500")
    assert "more system memory" in detail

"""The server's shutdown work runs from the lifespan handler, in order."""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi", reason="openjarvis[server] not installed")

from fastapi.testclient import TestClient  # noqa: E402


def _engine() -> MagicMock:
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    return engine


def test_shutdown_hooks_run_in_order_even_if_one_fails():
    from openjarvis.server.app import create_app

    memory = MagicMock()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        app = create_app(_engine(), "test-model", memory_service=memory)
    calls = []

    async def broken() -> None:
        calls.append("broken")
        raise RuntimeError("boom")

    async def last() -> None:
        calls.append("last")

    app.state.shutdown_hooks[:0] = [broken]
    app.state.shutdown_hooks.append(last)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert calls == []
    assert calls == ["broken", "last"]
    memory.stop.assert_called_once()
    assert app.state._managed_runtime_stopping is True


def test_no_deprecated_event_handlers():
    from openjarvis.server.app import create_app

    app = create_app(_engine(), "test-model")
    assert app.router.on_shutdown == [] and app.router.on_startup == []

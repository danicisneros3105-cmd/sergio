"""Connector tests must never inherit the developer's Google Tasks account."""

import pytest


@pytest.fixture(autouse=True)
def isolated_google_tasks_account(tmp_path, monkeypatch):
    from openjarvis.core.registry import ConnectorRegistry

    was_registered = ConnectorRegistry.contains("google_tasks")
    from openjarvis.connectors import google_tasks

    if not was_registered:
        ConnectorRegistry._entries().pop("google_tasks", None)

    path = tmp_path / "disconnected-google-tasks.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(google_tasks, "_DEFAULT_CREDENTIALS_PATH", str(path))

    def deny_unmocked_tasks_api(*args, **kwargs):
        raise AssertionError("Google Tasks API must be explicitly mocked in tests")

    monkeypatch.setattr(google_tasks, "_tasks_api_get", deny_unmocked_tasks_api)

"""With an OpenRouter key every AI works: models without their own key go
through it, and signing in configures the owner's key and the model list."""

from __future__ import annotations

import pytest

from openjarvis.accounts import autoconfig
from openjarvis.engine import cloud


@pytest.fixture
def keys(monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
              "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "OPENROUTER_MANAGEMENT_KEY"):  # fmt: skip
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_models_without_their_own_key_go_through_openrouter(keys):
    keys.setenv("OPENROUTER_API_KEY", "sk-or-x")
    assert (
        cloud.through_openrouter("gemini-3.8-flash")
        == "openrouter/google/gemini-3.8-flash"
    )
    assert (
        cloud.through_openrouter("gemini-3.8-flash@low")
        == "openrouter/google/gemini-3.8-flash"
    )
    assert (
        cloud.through_openrouter("claude-sonnet-5-5")
        == "openrouter/anthropic/claude-sonnet-5-5"
    )
    assert (
        cloud.through_openrouter("gpt-5.6-terra") == "openrouter/openai/gpt-5.6-terra"
    )
    assert cloud.through_openrouter("openrouter/auto") == "openrouter/auto"
    assert cloud.through_openrouter("qwen3:8b") == "qwen3:8b"  # a local model stays


def test_a_labs_own_key_wins(keys):
    keys.setenv("OPENROUTER_API_KEY", "sk-or-x")
    keys.setenv("GEMINI_API_KEY", "g")
    assert cloud.through_openrouter("gemini-3.8-flash") == "gemini-3.8-flash"
    assert cloud.through_openrouter("claude-sonnet-5-5").startswith("openrouter/")


def test_without_openrouter_nothing_changes(keys):
    assert cloud.through_openrouter("gemini-3.8-flash") == "gemini-3.8-flash"


class R:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d


class Http:
    def __init__(self):
        self.calls = []

    def request(self, method, url, json=None, headers=None):
        self.calls.append((method, url, json))
        return R({"key": "sk-or-owner", "data": {"hash": "h"}})

    def get(self, url, headers=None):
        self.calls.append(("GET", url, None))
        return R(
            {
                "data": [
                    {"id": "anthropic/claude-sonnet-5.5"},
                    {"id": "google/gemini-3.8-flash"},
                ]
            }
        )


def test_owner_sign_in_creates_his_key_once_and_reads_the_models(keys, tmp_path):
    from openjarvis.server import cloud_router

    keys.setenv("OPENROUTER_MANAGEMENT_KEY", "mgmt")
    keys.setattr(cloud_router, "_CLOUD_ENV_FILE", tmp_path / "cloud-keys.env")
    http = Http()
    out = autoconfig.on_sign_in({"id": "1", "role": "dueño"}, http)
    assert out["dueño"] is True and out["modelos"] == 2
    assert "Listo" in out["motivo"]  # the sign-in page says what happened
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-owner"
    assert "OPENROUTER_API_KEY=sk-or-owner" in (tmp_path / "cloud-keys.env").read_text()
    autoconfig.on_sign_in({"id": "1", "role": "dueño"}, http)
    assert sum(1 for c in http.calls if c[0] == "POST") == 1  # never a second key
    assert autoconfig.ready()["openrouter"] and autoconfig.ready()["modelos"] == 2


def test_nothing_to_configure_without_any_key(keys):
    assert autoconfig.on_sign_in({"id": "1", "role": "dueño"}, Http())["dueño"] is False


def test_the_owner_key_written_before_a_restart_is_found_again(keys, tmp_path):
    from openjarvis.server import cloud_router

    keys.setenv("OPENROUTER_MANAGEMENT_KEY", "mgmt")
    keys.delenv("OPENROUTER_API_KEY", raising=False)
    env = tmp_path / "cloud-keys.env"
    env.write_text("# Sergio Nodes API\nOPENROUTER_API_KEY=sk-or-saved\n")
    keys.setattr(cloud_router, "_CLOUD_ENV_FILE", env)
    http = Http()
    assert autoconfig.on_sign_in({"id": "1", "role": "dueño"}, http)["dueño"] is True
    assert not any(c[0] == "POST" for c in http.calls)  # no second «sergio-dueño» key
    autoconfig._save_env("OTRA", "x")
    assert env.read_text().startswith("# Sergio Nodes API")  # comments survive


def test_without_a_management_key_the_page_is_told_why(keys):
    out = autoconfig.on_sign_in({"id": "1", "role": "dueño"}, Http())
    assert "Conectar la IA con un clic" in out["motivo"]
    assert autoconfig.ready()["ultimo"]["motivo"] == out["motivo"]

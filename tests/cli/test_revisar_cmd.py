"""`sergio revisar`: no silent multi-GB downloads for cloud brains, no endless waits."""

from __future__ import annotations

import json
import threading

import httpx
import pytest
from click.testing import CliRunner
from rich.console import Console

from openjarvis.cli import revisar_cmd


def _handler(calls, ollama=True, local_models=(), hang=None):
    stuck = threading.Event()

    def handler(request):
        path = request.url.path
        calls.append(path)
        if request.url.port == 11434:
            if not ollama:
                raise httpx.ConnectError("refused")
            if path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": m} for m in local_models]})
            if path == "/api/pull":
                lines = [{"status": "pulling", "total": 1000, "completed": c} for c in (0, 500, 1000)]
                return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines + [{"status": "success"}]))
        if path == hang:
            stuck.wait(3)
        if path in ("/health", "/v1/chat/completions", "/v1/speech/synthesize", "/v1/faces/look",
                    "/v1/speech/transcribe"):
            return httpx.Response(200, json={"ok": True})
        if path == "/v1/world/open":
            return httpx.Response(200, json={"url": "http://127.0.0.1:4173/"})
        return httpx.Response(404)

    return handler


@pytest.fixture()
def run(monkeypatch, tmp_path):
    def go(model="gemini-3.8-flash", **kw):
        calls: list[str] = []
        client = httpx.Client(transport=httpx.MockTransport(_handler(calls, **kw)))

        def strip(kwargs):
            return {k: v for k, v in kwargs.items() if k not in ("timeout", "trust_env")}

        monkeypatch.setattr(revisar_cmd.httpx, "get", lambda url, **k: client.get(url, **strip(k)))
        monkeypatch.setattr(revisar_cmd.httpx, "post", lambda url, **k: client.post(url, **strip(k)))
        monkeypatch.setattr(revisar_cmd.httpx, "stream", lambda m, url, **k: client.stream(m, url, **strip(k)))
        cfg_text = f'[intelligence]\ndefault_model = "{model}"\n'
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        (home / "config.toml").write_text(cfg_text)
        monkeypatch.setenv("OPENJARVIS_HOME", str(home))
        monkeypatch.setattr("openjarvis.cli.service_cmd.env_file", lambda: tmp_path / "none.env")
        monkeypatch.setattr(revisar_cmd, "console", Console(width=300))
        result = CliRunner().invoke(revisar_cmd.revisar, [])
        return result, calls

    return go


def test_a_cloud_brain_never_downloads_a_local_model(run):
    result, calls = run(ollama=True, local_models=())
    assert "/api/pull" not in calls
    assert "Modelo en la nube: gemini-3.8-flash (sin respaldo local" in result.output
    assert result.exit_code == 0, result.output


def test_a_cloud_brain_does_not_need_ollama(run):
    result, calls = run(ollama=False)
    assert "Ollama no está; no hace falta" in result.output
    assert result.exit_code == 0, result.output


def test_a_missing_local_model_downloads_with_progress(run):
    result, calls = run(model="qwen3:8b", local_models=())
    assert "/api/pull" in calls
    assert "50% de 0.0 GB" in result.output and "Modelo qwen3:8b descargado" in result.output


def test_a_check_that_hangs_is_reported_and_the_rest_runs(run, monkeypatch):
    monkeypatch.setattr(revisar_cmd, "CHECK_TIMEOUT", 0.2)
    result, calls = run(hang="/v1/speech/synthesize")
    assert "FALLA Voz (Sergio habla): no respondió" in result.output
    assert "Globo 3D en http://127.0.0.1:4173/" in result.output
    assert result.exit_code == 1

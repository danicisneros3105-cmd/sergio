"""`sergio nube configurar`: Kimi key check, model choice, private storage."""

import subprocess

import httpx
from click.testing import CliRunner

from openjarvis.cli import nube_cmd


def test_pick_kimi_prefers_newest_known():
    assert (
        nube_cmd.pick_kimi(["moonshot-v1-8k", "kimi-k2.5", "kimi-k2.6"]) == "kimi-k2.6"
    )
    assert nube_cmd.pick_kimi(["kimi-k3", "kimi-k2.9"]) == "kimi-k3"
    assert nube_cmd.pick_kimi([]) == "kimi-k2.6"


def test_find_kimi_falls_back_to_china_endpoint():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer sk-x"
        if "moonshot.ai" in request.url.host:
            return httpx.Response(401, json={"error": "invalid key"})
        return httpx.Response(200, json={"data": [{"id": "kimi-k2.6"}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    url, models = nube_cmd.find_kimi("sk-x", http)
    assert url == "https://api.moonshot.cn/v1" and models == ["kimi-k2.6"]


def test_configurar_keeps_keys_private_and_sets_main_model(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "openjarvis.cli.service_cmd.env_file", lambda: tmp_path / "sergio.env"
    )
    monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(
        nube_cmd, "find_kimi", lambda key: ("https://api.moonshot.ai/v1", ["kimi-k2.6"])
    )
    ran = []
    monkeypatch.setattr(
        nube_cmd.subprocess,
        "run",
        lambda cmd, **kw: (
            ran.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", "")
        ),
    )
    (tmp_path / "config.toml").write_text(
        '[intelligence]\ndefault_model = "qwen3:8b"\n'
    )
    result = CliRunner().invoke(
        nube_cmd.nube, ["configurar", "--kimi", "sk-secret", "--gemini", "AQ.secret"]
    )
    assert result.exit_code == 0, result.output
    env = (tmp_path / "sergio.env").read_text()
    assert "MOONSHOT_API_KEY=sk-secret" in env and "GEMINI_API_KEY=AQ.secret" in env
    assert oct((tmp_path / "sergio.env").stat().st_mode)[-3:] == "600"
    cfg = (tmp_path / "config.toml").read_text()
    assert 'default_model = "kimi-k2.6"' in cfg and 'fallback_model = "qwen3:8b"' in cfg
    assert "secret" not in cfg  # keys never land in config.toml
    assert "secret" not in result.output
    assert any(c[:3] == ["uv", "pip", "install"] for c in ran)
    assert ["systemctl", "--user", "try-restart", "sergio.service"] in ran


def test_clean_key_repairs_copy_paste_damage():
    import click
    import pytest

    fullwidth = "sk-Ehu9Ｓｉ１Ｊ９ＢＺＺ"  # what some apps paste
    assert nube_cmd.clean_key(fullwidth) == "sk-Ehu9Si1J9BZZ"
    assert nube_cmd.clean_key(" 'sk-abc'​\n") == "sk-abc"
    with pytest.raises(click.ClickException, match="caracteres extraños"):
        nube_cmd.clean_key("sk-Ехu")  # Cyrillic lookalikes cannot be repaired


def test_bad_kimi_key_still_saves_gemini(tmp_path, monkeypatch):
    import click

    monkeypatch.setattr(
        "openjarvis.cli.service_cmd.env_file", lambda: tmp_path / "sergio.env"
    )
    monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)
    (tmp_path / "sergio.env").write_text("MOONSHOT_API_KEY=sk-old-bad\n")

    def reject(key):
        raise click.ClickException("Kimi rejected the key")

    monkeypatch.setattr(nube_cmd, "find_kimi", reject)
    monkeypatch.setattr(
        nube_cmd.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    result = CliRunner().invoke(nube_cmd.nube, ["configurar", "--gemini", "AQ.g"])
    assert result.exit_code == 0, result.output
    assert "sigo sin Kimi" in result.output
    env = (tmp_path / "sergio.env").read_text()
    assert "GEMINI_API_KEY=AQ.g" in env and "MOONSHOT_API_KEY=\n" in env
    cfg = (tmp_path / "config.toml").read_text()
    assert 'default_model = "gemini-3.8-flash"' in cfg

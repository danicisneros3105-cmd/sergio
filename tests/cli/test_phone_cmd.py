"""Tests for `sergio telefono` (guided setup)."""

from __future__ import annotations

import stat

from click.testing import CliRunner

from openjarvis.cli import phone_cmd, service_cmd
from openjarvis.core.config import load_config


def test_env_file_updates_keep_comments_and_are_private(tmp_path):
    path = tmp_path / "sergio.env"
    path.write_text("# keep me\nANTHROPIC_API_KEY=a\nTWILIO_AUTH_TOKEN=old\n")
    phone_cmd.write_env(
        path, {"TWILIO_AUTH_TOKEN": "new", "NGROK_AUTHTOKEN": "n", "X": ""}
    )
    text = path.read_text()
    assert "# keep me" in text and "ANTHROPIC_API_KEY=a" in text
    assert "TWILIO_AUTH_TOKEN=new" in text and "NGROK_AUTHTOKEN=n" in text
    assert "X=" not in text
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert phone_cmd.read_env(path)["TWILIO_AUTH_TOKEN"] == "new"


def test_configurar_writes_config_and_points_twilio(tmp_path, monkeypatch):
    from openjarvis.core.paths import get_config_dir

    env = tmp_path / "sergio.env"
    monkeypatch.setattr(service_cmd, "env_file", lambda: env)
    pointed = []
    monkeypatch.setattr(
        phone_cmd,
        "point_twilio_number",
        lambda *a: pointed.append(a) or "",
    )
    answers = "\n".join(
        [
            "0991234567",  # rejected: not international
            "+593 99 123 4567",
            "Dani",
            "ACxxx",
            "tok",
            "+15550001111",
            "ngtok",
            "https://sergio-x.ngrok-free.app/",
            "",  # skip WhatsApp
            "",
            "",
        ]
    )
    result = CliRunner().invoke(
        phone_cmd.telefono, ["configurar"], input=answers + "\n"
    )
    assert result.exit_code == 0, result.output
    assert "not a full international number" in result.output
    cfg = load_config(get_config_dir() / "config.toml")
    assert cfg.phone.enabled and cfg.phone.owner_numbers == ["+593991234567"]
    assert cfg.phone.public_url == "https://sergio-x.ngrok-free.app"
    assert (
        cfg.tunnel.provider == "ngrok"
        and cfg.tunnel.domain == "sergio-x.ngrok-free.app"
    )
    saved = phone_cmd.read_env(env)
    assert saved["TWILIO_AUTH_TOKEN"] == "tok" and "WHATSAPP_VERIFY_TOKEN" not in saved
    assert pointed == [
        (
            "ACxxx",
            "tok",
            "+15550001111",
            "https://sergio-x.ngrok-free.app/phone/incoming",
        )
    ]
    status = CliRunner().invoke(phone_cmd.telefono, ["estado"])
    assert "tok" not in status.output and "saved" in status.output


def test_read_env_matches_systemd_quoting(tmp_path):
    path = tmp_path / "sergio.env"
    path.write_text(
        'ANTHROPIC_API_KEY="sk-ant-1"\n'
        "export TWILIO_AUTH_TOKEN='tok'\n"
        "  # comment\n"
        "PLAIN=value\n"
        "\n"
    )
    assert phone_cmd.read_env(path) == {
        "ANTHROPIC_API_KEY": "sk-ant-1",
        "TWILIO_AUTH_TOKEN": "tok",
        "PLAIN": "value",
    }


def test_rerun_without_domain_keeps_existing_tunnel(tmp_path, monkeypatch):
    from openjarvis.core.paths import get_config_dir

    cfg_path = get_config_dir() / "config.toml"
    cfg_path.write_text(
        '[tunnel]\nprovider = "cloudflare"\n'
        '[phone]\npublic_url = "https://sergio.mydomain.com"\n'
    )
    monkeypatch.setattr(service_cmd, "env_file", lambda: tmp_path / "sergio.env")
    monkeypatch.setattr(phone_cmd, "point_twilio_number", lambda *a: "")
    answers = "\n".join(
        ["+593991234567", "Dani", "AC", "tok", "+1555", "", "", "", "", ""]
    )
    result = CliRunner().invoke(
        phone_cmd.telefono, ["configurar"], input=answers + "\n"
    )
    assert result.exit_code == 0, result.output
    cfg = load_config(cfg_path)
    assert cfg.tunnel.provider == "cloudflare"
    assert cfg.phone.public_url == "https://sergio.mydomain.com" and cfg.phone.enabled

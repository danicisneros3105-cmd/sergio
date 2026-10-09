"""``sergio respaldo`` and ``sergio sync`` end to end on folder targets."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

pytest.importorskip("cryptography")

from openjarvis.cli.respaldo_cmd import respaldo  # noqa: E402
from openjarvis.cli.sync_cmd import sync  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    (h / "USER.md").write_text("hola")
    monkeypatch.setenv("OPENJARVIS_HOME", str(h))
    monkeypatch.setenv("SERGIO_AGE_WORK", "10")
    monkeypatch.delenv("SERGIO_BACKUP_PASSPHRASE", raising=False)
    monkeypatch.delenv("SERGIO_SYNC_PASSPHRASE", raising=False)
    return h


def test_backup_commands(home, tmp_path):
    runner = CliRunner()
    dest = tmp_path / "dest"
    out = runner.invoke(respaldo, ["configurar", str(dest)])
    assert out.exit_code == 0, out.output
    assert f'target = "{dest}"' in (home / "config.toml").read_text()
    short = runner.invoke(respaldo, ["crear"], input="corta\ncorta\n")
    assert short.exit_code != 0 and "10 caracteres" in short.output
    made = runner.invoke(
        respaldo, ["crear"], input="una frase larga\nuna frase larga\n"
    )
    assert made.exit_code == 0 and "completa" in made.output, made.output
    assert "completa" in runner.invoke(respaldo, ["lista"]).output
    checked = runner.invoke(respaldo, ["verificar"], input="una frase larga\n")
    assert "íntegra" in checked.output
    wrong = runner.invoke(respaldo, ["verificar"], input="frase equivocada\n")
    assert wrong.exit_code != 0 and "incorrecta" in wrong.output
    restored = runner.invoke(
        respaldo,
        ["restaurar", "--destino", str(tmp_path / "r")],
        input="una frase larga\n",
    )
    assert (
        restored.exit_code == 0 and (tmp_path / "r" / "USER.md").read_text() == "hola"
    )


def test_restore_over_keeps_the_old_folder(home, tmp_path, monkeypatch):
    monkeypatch.setenv("SERGIO_BACKUP_PASSPHRASE", "una frase larga")
    runner = CliRunner()
    runner.invoke(respaldo, ["configurar", str(tmp_path / "dest")])
    assert runner.invoke(respaldo, ["crear"]).exit_code == 0
    (home / "USER.md").write_text("cambiado")
    done = runner.invoke(respaldo, ["restaurar", "--encima"])
    assert done.exit_code == 0, done.output
    assert (home / "USER.md").read_text() == "hola"
    old = [p for p in home.parent.iterdir() if ".antes-" in p.name]
    assert len(old) == 1 and (old[0] / "USER.md").read_text() == "cambiado"


def test_bad_target_and_missing_setup(home):
    runner = CliRunner()
    assert "No hay destino" in runner.invoke(respaldo, ["lista"]).output
    assert runner.invoke(respaldo, ["configurar", "ftp://viejo"]).exit_code != 0


def test_sync_commands(home, tmp_path, monkeypatch):
    runner = CliRunner()
    cloud = tmp_path / "cloud"
    first = runner.invoke(
        sync, ["configurar", str(cloud)], input="frase compartida\nfrase compartida\n"
    )
    assert first.exit_code == 0 and "primer equipo" in first.output, first.output
    now = runner.invoke(sync, ["ahora"])
    assert now.exit_code == 0 and "subidos" in now.output, now.output
    assert "Desbloqueado en este equipo: sí" in runner.invoke(sync, ["estado"]).output
    assert runner.invoke(sync, ["olvidar"]).exit_code == 0
    locked = runner.invoke(sync, ["ahora"], input="frase mala!!\n")
    assert locked.exit_code != 0 and "incorrecta" in locked.output
    # A second device with the same passphrase gets the file.
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("OPENJARVIS_HOME", str(other))
    joined = runner.invoke(sync, ["configurar", str(cloud)], input="frase compartida\n")
    assert joined.exit_code == 0, joined.output
    assert "bajados" in runner.invoke(sync, ["ahora"]).output
    assert (other / "USER.md").read_text() == "hola"

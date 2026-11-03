"""The launch check says what it read, and never marks a person's job as done."""

from __future__ import annotations

from openjarvis import lanzamiento


def _clean(monkeypatch):
    for k in ("SERGIO_EDICION", "SERGIO_REGISTRO", "SERGIO_PUBLIC_URL", "SERGIO_CLAVE_MAESTRA",
              "OPENROUTER_MANAGEMENT_KEY", "SERGIO_CIFRAR"):  # fmt: skip
        monkeypatch.delenv(k, raising=False)


def test_a_bare_install_is_not_ready_and_the_owners_list_stays_open(monkeypatch):
    _clean(monkeypatch)
    res = lanzamiento.revisar()
    assert not res["listo_codigo"] and res["pendientes_del_dueno"] == 9
    owner = [s for s in res["pasos"] if s["quien"] == "dueño"]
    assert len(owner) == 9 and not any(
        s["ok"] for s in owner
    )  # Sergio never ticks a person's job
    by = {s["paso"]: s for s in res["pasos"]}
    assert (
        not by["Edición pública"]["ok"] and not by["Dirección pública con https"]["ok"]
    )
    assert by["Cifrado de datos sensibles"]["ok"]  # on by default


def test_each_setting_turns_its_own_step_green(monkeypatch):
    _clean(monkeypatch)
    monkeypatch.setenv("SERGIO_EDICION", "publica")
    monkeypatch.setenv("SERGIO_PUBLIC_URL", "https://sergio.example")
    monkeypatch.setenv("SERGIO_CLAVE_MAESTRA", "x")
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "sk-or-x")
    by = {s["paso"]: s for s in lanzamiento.revisar()["pasos"]}
    for name in ("Edición pública", "Dirección pública con https", "Clave maestra fuera del disco",
                 "Claves de IA por cliente (OpenRouter)"):  # fmt: skip
        assert by[name]["ok"], name
    monkeypatch.setenv("SERGIO_PUBLIC_URL", "http://sergio.example")
    assert not {s["paso"]: s for s in lanzamiento.revisar()["pasos"]}[
        "Dirección pública con https"
    ]["ok"]


def test_the_command_runs(monkeypatch):
    from click.testing import CliRunner

    from openjarvis.cli.lanzamiento_cmd import lanzamiento as cmd

    _clean(monkeypatch)
    out = CliRunner().invoke(cmd, [])
    assert out.exit_code == 0 and "docs/LANZAMIENTO.md" in out.output
    assert '"listo_codigo"' in CliRunner().invoke(cmd, ["--json"]).output

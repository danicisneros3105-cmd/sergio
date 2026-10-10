"""Plans and licenses: signing, verification, feature flags, CLI, premium plugins."""

from __future__ import annotations

import json
import os
import stat
import time

import pytest
from click.testing import CliRunner

from openjarvis import tiers
from openjarvis.tiers import LicenseError


@pytest.fixture()
def keys(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path / "home"))
    pair = tiers.generate_keypair()
    monkeypatch.setenv("SERGIO_LICENSE_PUBKEY", pair["public"])
    return pair


def test_issue_and_verify_round_trip(keys):
    token = tiers.issue(keys["private"], "pro", holder="Ana", seats=3, days=30)
    assert token.startswith("sergio-lic-v1.")
    payload = tiers.verify(token)
    assert payload["plan"] == "pro" and payload["holder"] == "Ana"
    assert payload["seats"] == 3
    assert payload["expires"] - payload["issued"] == 30 * 86400


def test_expired_forged_and_malformed_tokens_are_refused(keys):
    old = tiers.issue(keys["private"], "pro", holder="Ana", days=1, now=1_000_000)
    with pytest.raises(LicenseError, match="venció"):
        tiers.verify(old)

    other = tiers.generate_keypair()
    forged = tiers.issue(other["private"], "enterprise", holder="Mallory")
    with pytest.raises(LicenseError, match="auténtica"):
        tiers.verify(forged)

    # A payload edited by hand (plan bumped) no longer matches its signature.
    good = tiers.issue(keys["private"], "pro", holder="Ana")
    prefix, body, sig = good.split(".")
    data = json.loads(tiers._b64d(body))
    data["plan"] = "enterprise"
    tampered = ".".join(
        [prefix, tiers._b64e(json.dumps(data, sort_keys=True).encode()), sig]
    )
    with pytest.raises(LicenseError, match="auténtica"):
        tiers.verify(tampered)

    for junk in ("", "hola", "otro-v1.a.b", "sergio-lic-v1.!!.??"):
        with pytest.raises(LicenseError):
            tiers.verify(junk)


def test_issue_rejects_free_and_unknown_plans(keys):
    for plan in ("free", "gold"):
        with pytest.raises(LicenseError):
            tiers.issue(keys["private"], plan, holder="x")


def test_no_public_key_means_no_paid_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    monkeypatch.delenv("SERGIO_LICENSE_PUBKEY", raising=False)
    monkeypatch.setattr(tiers, "OFFICIAL_PUBLIC_KEY", "")
    pair = tiers.generate_keypair()
    with pytest.raises(LicenseError, match="clave pública"):
        tiers.verify(tiers.issue(pair["private"], "pro", holder="x"))


def test_activate_current_and_feature_flags(keys):
    assert tiers.current() == {"plan": "free"}
    assert tiers.has_feature("cowork")  # not a paid feature: always on
    assert not tiers.has_feature("premium_skills")
    with pytest.raises(PermissionError, match="plan Pro"):
        tiers.require("hosted_sync")

    tiers.activate(tiers.issue(keys["private"], "teams", holder="Equipo", seats=5))
    mode = stat.S_IMODE(os.stat(tiers.license_path()).st_mode)
    assert mode == 0o600
    assert tiers.current()["plan"] == "teams"
    assert tiers.has_feature("premium_skills") and tiers.has_feature("sso")
    assert not tiers.has_feature("on_prem")
    tiers.require("rbac")

    tiers.deactivate()
    assert tiers.current() == {"plan": "free"}


def test_a_license_that_stops_verifying_falls_back_to_free(keys, monkeypatch):
    tiers.activate(tiers.issue(keys["private"], "pro", holder="Ana", days=1))
    monkeypatch.setattr(tiers.time, "time", lambda: time.time_ns() / 1e9 + 2 * 86400)
    mine = tiers.current()
    assert mine["plan"] == "free" and "venció" in mine["problem"]


def test_activate_refuses_a_bad_key_and_keeps_free(keys):
    with pytest.raises(LicenseError):
        tiers.activate("sergio-lic-v1.abc.def")
    assert not tiers.license_path().exists()


def test_checkout_url_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("SERGIO_CHECKOUT_PRO", raising=False)
    assert tiers.checkout_url("pro") == ""
    monkeypatch.setenv("SERGIO_CHECKOUT_PRO", " https://buy.stripe.com/test_x ")
    assert tiers.checkout_url("pro") == "https://buy.stripe.com/test_x"


def test_every_plan_and_feature_is_described():
    assert set(tiers.PLAN_INFO) == set(tiers.PLANS)
    assert set(tiers.FEATURES_ES) == set(tiers.FEATURES)
    assert set(tiers.FEATURES.values()) <= set(tiers.PLANS) - {"free"}


# -- CLI ------------------------------------------------------------------------


def test_cli_seller_and_customer_flow(keys, tmp_path, monkeypatch):
    from openjarvis.cli.planes_cmd import licencia, planes

    runner = CliRunner()
    key_file = tmp_path / "issuer.key"
    made = runner.invoke(licencia, ["generar-claves", "--salida", str(key_file)])
    assert made.exit_code == 0, made.output
    assert stat.S_IMODE(os.stat(key_file).st_mode) == 0o600
    public = made.output.strip().splitlines()[-1]
    again = runner.invoke(licencia, ["generar-claves", "--salida", str(key_file)])
    assert again.exit_code != 0 and "no la sobrescribo" in again.output

    monkeypatch.setenv("SERGIO_LICENSE_PUBKEY", public)
    issued = runner.invoke(
        licencia,
        [
            "emitir",
            "pro",
            "--titular",
            "Ana",
            "--dias",
            "10",
            "--clave-privada",
            str(key_file),
        ],
    )
    assert issued.exit_code == 0, issued.output
    token = issued.output.strip().replace("\n", "")

    listing = runner.invoke(planes, [])
    assert listing.exit_code == 0 and "Free ✓" in listing.output
    assert "Enterprise" in listing.output

    bad = runner.invoke(licencia, ["activar", "sergio-lic-v1.x.y"])
    assert bad.exit_code != 0 and "mal formada" in bad.output
    ok = runner.invoke(licencia, ["activar", token])
    assert ok.exit_code == 0 and "plan Pro" in ok.output, ok.output
    status = runner.invoke(licencia, ["estado"]).output
    assert "Plan: Pro" in status and "Titular: Ana" in status
    assert "✓ skills y plugins premium" in status and "· soporte con SLA" in status
    assert "Pro ✓" in runner.invoke(planes, []).output

    assert "plan Free" in runner.invoke(licencia, ["quitar"]).output
    assert "Plan: Free" in runner.invoke(licencia, ["estado"]).output


def test_cli_upgrade_needs_a_checkout_link(monkeypatch):
    from openjarvis.cli import planes_cmd

    opened = []
    monkeypatch.setattr(planes_cmd.webbrowser, "open", opened.append)
    monkeypatch.delenv("SERGIO_CHECKOUT_TEAMS", raising=False)
    runner = CliRunner()
    missing = runner.invoke(planes_cmd.planes, ["mejorar", "teams"])
    assert missing.exit_code != 0 and "SERGIO_CHECKOUT_TEAMS" in missing.output
    monkeypatch.setenv("SERGIO_CHECKOUT_TEAMS", "https://buy.stripe.com/test_t")
    done = runner.invoke(planes_cmd.planes, ["mejorar", "teams"])
    assert done.exit_code == 0 and opened == ["https://buy.stripe.com/test_t"]


def test_premium_plugins_need_the_pro_plan(keys, tmp_path, monkeypatch):
    from openjarvis.cli.plugin_cmd import plugin
    from openjarvis.plugins import loader
    from openjarvis.plugins.index import CATALOG

    monkeypatch.delenv("SERGIO_NO_PLUGINS", raising=False)
    monkeypatch.setattr(loader, "_LOADED", {})
    monkeypatch.setattr(loader, "_FAILED", {})
    monkeypatch.setattr(loader, "_CLASSES", {})
    index = tmp_path / "premium-index.json"
    index.write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "name": "frase-del-dia",
                        "version": "9.0.0",
                        "description": "versión premium",
                        "path": str(CATALOG / "frase-del-dia"),
                        "premium": True,
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("SERGIO_PLUGIN_INDEX", str(index))

    runner = CliRunner()
    blocked = runner.invoke(plugin, ["instalar", "frase-del-dia", "--si"])
    assert blocked.exit_code != 0 and "plan Pro" in blocked.output, blocked.output

    tiers.activate(tiers.issue(keys["private"], "pro", holder="Ana"))
    ok = runner.invoke(plugin, ["instalar", "frase-del-dia", "--si"])
    assert ok.exit_code == 0 and "frase_del_dia" in ok.output, ok.output


def test_bundles_ride_on_their_plan(keys):
    assert {b.plan for b in tiers.BUNDLES.values()} <= set(tiers.PLANS) - {"free"}
    token = tiers.issue(keys["private"], "pro", holder="Estudio", bundle="vfx-studio")
    assert tiers.verify(token)["bundle"] == "vfx-studio"
    with pytest.raises(LicenseError, match="va con el plan"):
        tiers.issue(keys["private"], "pro", holder="x", bundle="privacidad")
    with pytest.raises(LicenseError, match="desconocido"):
        tiers.issue(keys["private"], "pro", holder="x", bundle="nada")


def test_cli_issues_and_shows_a_bundle(keys, tmp_path):
    from openjarvis.cli.planes_cmd import licencia, planes

    key_file = tmp_path / "issuer.key"
    key_file.write_text(keys["private"])
    runner = CliRunner()
    base = ["emitir", "teams", "--titular", "Tienda", "--clave-privada", str(key_file)]
    wrong = runner.invoke(licencia, [*base, "--paquete", "vfx-studio"])
    assert wrong.exit_code != 0 and "va con el plan pro" in wrong.output
    issued = runner.invoke(licencia, [*base, "--paquete", "multicanal"])
    assert issued.exit_code == 0, issued.output
    tiers.activate(issued.output.strip().replace("\n", ""))
    assert "paquete Multi-channel" in runner.invoke(licencia, ["estado"]).output
    assert "VFX Studio — $19 / mes" in runner.invoke(planes, []).output

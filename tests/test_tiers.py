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
    token = tiers.issue(keys["private"], "work", holder="Ana", seats=3, days=30)
    assert token.startswith("sergio-lic-v1.")
    payload = tiers.verify(token)
    assert payload["plan"] == "work" and payload["holder"] == "Ana"
    assert payload["seats"] == 3
    assert payload["expires"] - payload["issued"] == 30 * 86400


def test_expired_forged_and_malformed_tokens_are_refused(keys):
    old = tiers.issue(keys["private"], "pro", holder="Ana", days=1, now=1_000_000)
    with pytest.raises(LicenseError, match="venció"):
        tiers.verify(old)

    other = tiers.generate_keypair()
    forged = tiers.issue(other["private"], "founders", holder="Mallory")
    with pytest.raises(LicenseError, match="auténtica"):
        tiers.verify(forged)

    # A payload edited by hand (plan bumped) no longer matches its signature.
    good = tiers.issue(keys["private"], "work", holder="Ana")
    prefix, body, sig = good.split(".")
    data = json.loads(tiers._b64d(body))
    data["plan"] = "founders"
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
        tiers.verify(tiers.issue(pair["private"], "work", holder="x"))


def test_activate_current_and_feature_flags(keys):
    assert tiers.current() == {"plan": "free"}
    assert tiers.has_feature("cowork")  # not a paid feature: always on
    assert not tiers.has_feature("premium_skills")
    with pytest.raises(PermissionError, match="plan Work"):
        tiers.require("hosted_sync")

    tiers.activate(tiers.issue(keys["private"], "dev", holder="Equipo", seats=5))
    mode = stat.S_IMODE(os.stat(tiers.license_path()).st_mode)
    assert mode == 0o600
    assert tiers.current()["plan"] == "dev"
    assert tiers.has_feature("premium_skills") and tiers.has_feature("custom_api")
    assert not tiers.has_feature("sso")
    tiers.activate(tiers.issue(keys["private"], "founders", holder="Equipo"))
    assert tiers.has_feature("sso") and tiers.has_feature("on_prem")
    tiers.require("rbac")

    tiers.deactivate()
    assert tiers.current() == {"plan": "free"}


def test_a_license_that_stops_verifying_falls_back_to_free(keys, monkeypatch):
    tiers.activate(tiers.issue(keys["private"], "work", holder="Ana", days=1))
    monkeypatch.setattr(tiers.time, "time", lambda: time.time_ns() / 1e9 + 2 * 86400)
    mine = tiers.current()
    assert mine["plan"] == "free" and "venció" in mine["problem"]


def test_activate_refuses_a_bad_key_and_keeps_free(keys):
    with pytest.raises(LicenseError):
        tiers.activate("sergio-lic-v1.abc.def")
    assert not tiers.license_path().exists()


def test_checkout_url_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("SERGIO_CHECKOUT_WORK", raising=False)
    assert tiers.checkout_url("work") == ""
    monkeypatch.setenv("SERGIO_CHECKOUT_WORK", " https://buy.stripe.com/test_x ")
    assert tiers.checkout_url("work") == "https://buy.stripe.com/test_x"
    assert tiers.checkout_url("pro") == "https://buy.stripe.com/test_x"  # old name
    monkeypatch.setenv("SERGIO_CHECKOUT_DEV_15", "https://buy.stripe.com/dev15")
    assert tiers.checkout_url("dev", 15) == "https://buy.stripe.com/dev15"


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
            "work",
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
    assert "Founders Edition" in listing.output

    bad = runner.invoke(licencia, ["activar", "sergio-lic-v1.x.y"])
    assert bad.exit_code != 0 and "mal formada" in bad.output
    ok = runner.invoke(licencia, ["activar", token])
    assert ok.exit_code == 0 and "plan Work" in ok.output, ok.output
    status = runner.invoke(licencia, ["estado"]).output
    assert "Plan: Work" in status and "Titular: Ana" in status
    assert "✓ skills y plugins premium" in status and "· soporte con SLA" in status
    assert "Work ✓" in runner.invoke(planes, []).output

    assert "plan Free" in runner.invoke(licencia, ["quitar"]).output
    assert "Plan: Free" in runner.invoke(licencia, ["estado"]).output


def test_cli_upgrade_needs_a_checkout_link(monkeypatch):
    from openjarvis.cli import planes_cmd

    opened = []
    monkeypatch.setattr(planes_cmd.webbrowser, "open", opened.append)
    monkeypatch.delenv("SERGIO_CHECKOUT_FOUNDERS", raising=False)
    runner = CliRunner()
    missing = runner.invoke(planes_cmd.planes, ["mejorar", "founders"])
    assert missing.exit_code != 0 and "SERGIO_CHECKOUT_FOUNDERS" in missing.output
    monkeypatch.setenv("SERGIO_CHECKOUT_FOUNDERS", "https://buy.stripe.com/test_t")
    done = runner.invoke(planes_cmd.planes, ["mejorar", "founders"])
    assert done.exit_code == 0 and opened == ["https://buy.stripe.com/test_t"]


def test_premium_plugins_need_the_work_plan(keys, tmp_path, monkeypatch):
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
    assert blocked.exit_code != 0 and "plan Work" in blocked.output, blocked.output

    tiers.activate(tiers.issue(keys["private"], "pro", holder="Ana"))
    ok = runner.invoke(plugin, ["instalar", "frase-del-dia", "--si"])
    assert ok.exit_code == 0 and "frase_del_dia" in ok.output, ok.output


def test_a_wrapped_key_still_activates_and_a_damaged_file_means_free(keys):
    token = tiers.issue(keys["private"], "pro", holder="Ana")
    wrapped = "\n".join(token[i : i + 60] for i in range(0, len(token), 60))
    assert tiers.activate("  " + wrapped + "\n")["plan"] == "work"
    assert stat.S_IMODE(os.stat(tiers.license_path()).st_mode) == 0o600
    assert tiers.current()["plan"] == "work"
    for junk in ("[1, 2]", '{"token": 7}', "no es json"):
        tiers.license_path().write_text(junk)
        assert tiers.current()["plan"] == "free"
    assert not tiers.has_feature("premium_skills")


def test_the_issued_key_prints_on_one_line(keys, tmp_path):
    from openjarvis.cli.planes_cmd import licencia

    key_file = tmp_path / "issuer.key"
    tiers.write_private(key_file, keys["private"], replace=False)
    with pytest.raises(FileExistsError):
        tiers.write_private(key_file, "otra", replace=False)
    out = (
        CliRunner()
        .invoke(
            licencia,
            ["emitir", "pro", "--titular", "Ana", "--clave-privada", str(key_file)],
        )
        .output
    )
    assert len(out.strip().splitlines()) == 1
    assert tiers.verify(out.strip())["holder"] == "Ana"


def test_old_plan_names_still_work(keys):
    """Licences signed before the plans were renamed keep their meaning."""
    assert tiers.plan_id("pro") == "work"
    assert tiers.plan_id("enterprise") == "founders"
    token = tiers.issue(keys["private"], "pro", holder="Ana")
    assert tiers.verify(token)["plan"] == "work"


def test_dev_and_founders_stretch_between_their_prices():
    assert [tiers.PLAN_INFO[p].usd for p in tiers.PLANS] == [0, 5, 21, 50, 99]
    assert tiers.stretch_usd("dev", 10) == 50 and tiers.stretch_usd("dev", 23) == 115
    assert tiers.stretch_usd("dev", 99) == 115 and tiers.stretch_usd("dev", 1) == 50
    assert tiers.stretch_usd("founders", 25) == 99
    assert tiers.stretch_usd("founders", 60) == 235
    assert 99 < tiers.stretch_usd("founders", 40) < 235
    assert tiers.stretch_usd("go", 50) == 5

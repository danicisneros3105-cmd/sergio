"""Ganancia real por cliente: lo que paga, menos comisión, menos la IA usada."""

from __future__ import annotations

import time

from openjarvis.accounts import provision
from openjarvis.pagos import clientes, ledger


class Http:
    def __init__(self, usage):
        self.usage = usage
        self.asked = []

    def get(self, url, headers=None):
        self.asked.append(url)
        usage = self.usage

        class R:
            status_code = 200 if usage is not None else 500

            def json(self):
                return {"data": {"usage_monthly": usage}}

        return R()


def _paid(uid, plan, usd, fee, home):
    o = ledger.new_order(uid, plan, 1, usd, "stripe", home)
    ledger.mark_paid(
        o["id"], time.time() + 20 * 86400, {"ingreso": usd, "comision": fee}, home
    )


def test_report_gives_each_customer_real_margin(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "sk-or-gestion")
    monkeypatch.setattr(provision, "_load", lambda home=None: {"u1": {"hash": "h1"}})
    monkeypatch.setattr(clientes, "_label", lambda uid: "Ana")
    _paid("u1", "work", 21.0, 0.91, tmp_path)
    http = Http(4.5)
    out = clientes.report(http=http, home=tmp_path)
    row = out["clientes"][0]
    assert http.asked == [f"{provision.API}/h1"]
    assert row["paga"] == 21.0 and row["comision"] == 0.91 and row["gasto_ia"] == 4.5
    assert row["ganancia"] == round(21.0 - 0.91 - 4.5, 2)
    assert row["tope_ia"] == provision.budget("work", 21.0)
    assert "Sonnet" in row["modelos"]
    assert (
        out["totales"]["ganancia"] == row["ganancia"]
        and out["totales"]["sin_dato"] == 0
    )


def test_unknown_cost_is_never_guessed(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "sk-or-gestion")
    monkeypatch.setattr(provision, "_load", lambda home=None: {"u1": {"hash": "h1"}})
    monkeypatch.setattr(clientes, "_label", lambda uid: "Ana")
    _paid("u1", "go", 5.0, 0.45, tmp_path)
    out = clientes.report(http=Http(None), home=tmp_path)
    assert (
        out["clientes"][0]["gasto_ia"] is None
        and out["clientes"][0]["ganancia"] is None
    )
    assert out["totales"]["sin_dato"] == 1 and out["totales"]["ganancia"] == 0


def test_auto_router_only_for_plans_with_every_model():
    assert not clientes.allowed("openrouter/auto", "work")
    assert clientes.allowed("openrouter/auto", "founders")
    assert set(clientes.MODEL_ACCESS) >= {"free", "go", "work", "dev", "founders"}

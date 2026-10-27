"""Trading: honest backtests (no look-ahead, with costs), real money behind
two locks, and every limit enforced in a pass."""

from __future__ import annotations

import numpy as np
import pytest

from openjarvis.automatiza import trading as T


def test_signals_are_zero_or_one_for_every_strategy():
    closes = list(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 600)))
    for s in T.STRATEGIES:
        sig = T.signal(np.asarray(closes), s)
        assert set(np.unique(sig)) <= {0.0, 1.0} and len(sig) == len(closes)


def test_backtest_has_no_look_ahead():
    # A price that jumps +10 % on one day only: a strategy that «knew» would
    # catch it. Our position is decided at yesterday's close, so changing the
    # future cannot change today's position.
    base = list(np.linspace(100, 200, 400))
    a = T.backtest(base, "cruce_medias")
    bumped = base[:]
    bumped[-1] *= 1.10
    b = T.backtest(bumped, "cruce_medias")
    sig_a = T.signal(np.asarray(base), "cruce_medias")[:-1]
    sig_b = T.signal(np.asarray(bumped), "cruce_medias")[:-1]
    assert np.array_equal(sig_a[:-1], sig_b[:-1])
    assert b["rentabilidad"] >= a["rentabilidad"]  # held into the jump, not timed


def test_costs_lower_the_result():
    closes = list(100 + np.cumsum(np.random.default_rng(3).normal(0, 1, 800)) + 50)
    free = T.backtest(closes, "reversion", cost=0.0)
    paid = T.backtest(closes, "reversion", cost=0.01)
    assert paid["rentabilidad"] <= free["rentabilidad"]


def test_backtest_needs_enough_history():
    with pytest.raises(ValueError):
        T.backtest([1.0] * 100, "momentum")


def test_real_money_needs_both_the_setting_and_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("SERGIO_TRADING_REAL", raising=False)
    s = T.save_settings({"real": True}, tmp_path)
    assert not T.real_money(s)
    monkeypatch.setenv("SERGIO_TRADING_REAL", "1")
    assert T.real_money(s)
    assert not T.real_money(T.save_settings({"real": False}, tmp_path))


class FakeBroker:
    def __init__(self, equity=10_000.0, last=10_000.0, open_=True):
        self.eq, self.last, self.open = equity, last, open_
        self.orders = []

    def clock(self):
        return {"is_open": self.open}

    def account(self):
        return {"equity": self.eq, "last_equity": self.last}

    def positions(self):
        return {}

    def closes(self, symbol, days=400):
        return list(np.linspace(100, 200, 300))  # rising: the signal is «in»

    def order(self, symbol, notional, side):
        self.orders.append((symbol, notional, side))
        return {"id": f"o{len(self.orders)}"}


def test_off_or_stopped_does_nothing(tmp_path):
    b = FakeBroker()
    assert T.run_once(tmp_path, b)["hecho"] == []
    T.save_settings({"activo": True}, tmp_path)
    T.stop(True, tmp_path)
    assert "PARAR" in T.run_once(tmp_path, b)["nota"]
    assert b.orders == []


def test_a_pass_respects_the_order_size_and_the_daily_count(tmp_path):
    T.save_settings({"activo": True, "simbolos": ["SPY", "QQQ", "IWM"],
                     "limites": {"max_orden_usd": 300, "max_ordenes_dia": 2}}, tmp_path)  # fmt: skip
    b = FakeBroker()
    out = T.run_once(tmp_path, b, today="2026-10-27")
    assert len(b.orders) == 2 and all(n <= 300 for _, n, _ in b.orders)
    assert all(e["real"] is False for e in out["hecho"])
    T.run_once(tmp_path, b, today="2026-10-27")
    assert len(b.orders) == 2  # the day's count is spent
    assert [j["simbolo"] for j in T.journal(tmp_path) if j["tipo"] == "orden"] == [
        "SPY",
        "QQQ",
    ]


def test_the_daily_loss_limit_stops_everything(tmp_path):
    T.save_settings({"activo": True}, tmp_path)
    b = FakeBroker(equity=9_600, last=10_000)  # −4 % today, limit 3 %
    out = T.run_once(tmp_path, b)
    assert b.orders == [] and T.stopped(tmp_path)
    assert "pérdida" in out["nota"]


def test_closed_market_waits(tmp_path):
    T.save_settings({"activo": True}, tmp_path)
    b = FakeBroker(open_=False)
    assert "cerrada" in T.run_once(tmp_path, b)["nota"] and b.orders == []


def test_status_always_carries_the_warning(tmp_path):
    assert T.estado(tmp_path)["aviso"] == T.WARNING

"""Plan economics: the arithmetic and the guard-rails, not the rates."""

from __future__ import annotations

from openjarvis.pagos import economia as E


def test_processor_fee_is_percentage_plus_fixed_and_zero_when_free():
    a = E.Assumptions(fee_pct=0.03, fee_fixed=0.30, foreign_share=0.0)
    assert a.processor(10.0) == 0.6 and a.processor(0.0) == 0.0
    b = E.Assumptions(
        fee_pct=0.03,
        fee_fixed=0.30,
        fee_foreign_pct=0.02,
        fee_fx_pct=0.01,
        foreign_share=1.0,
    )
    assert b.processor(100.0) == 6.3  # 3 % + 2 % + 1 % + 0.30


def test_worst_case_is_the_whole_cap_and_typical_is_a_share_of_it():
    a = E.Assumptions(
        fee_pct=0.0,
        fee_fixed=0.0,
        foreign_share=0.0,
        openrouter_pct=0.0,
        infra_paid=0.0,
        typical_use=0.5,
    )
    row = E.plan_row("work", 21.0, a)
    assert row["tope_ia"] == 12.6 and row["peor"] == 8.4 and row["tipico"] == 14.7


def test_the_ai_cap_never_lets_a_plan_lose_money_with_the_default_rates():
    rep = E.report(E.Assumptions())
    assert rep["planes"] and rep["aviso"]
    for row in rep["planes"]:
        assert row["peor"] > 0, f"{row['plan']} loses money with a heavy user"
        assert row["tipico"] >= row["peor"]


def test_free_costs_something_and_the_report_says_how_many_it_carries():
    rep = E.report(E.Assumptions())
    assert rep["free"]["costo_peor"] > rep["free"]["costo_tipico"] > 0
    assert rep["free_por_cliente_go"] > 1


def test_rates_can_be_corrected_without_touching_code(monkeypatch):
    monkeypatch.setenv("SERGIO_COMISION_PCT", "0.05")
    monkeypatch.setenv("SERGIO_USO_TIPICO", "0.9")
    a = E.Assumptions.from_env()
    assert a.fee_pct == 0.05 and a.typical_use == 0.9
    monkeypatch.setenv("SERGIO_COMISION_PCT", "mucho")
    assert E.Assumptions.from_env().fee_pct == 0.029  # a typo keeps the default

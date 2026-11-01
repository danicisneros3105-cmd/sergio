"""Tests for Economic Feasibility and Grounded Realism Engine."""

from __future__ import annotations

from openjarvis.core.economic_feasibility import (
    FeasibilityStatus,
    audit_economic_feasibility,
    parse_arbitrage_targets,
)


def test_impossible_hotel_discount_calibrated_to_realistic_market():
    # Attempting to drop a $12,000 USD villa to $600 USD (95% discount) is flagged as impossible
    audit = audit_economic_feasibility(12000.0, 600.0)

    assert audit.is_realistic is False
    assert audit.status == FeasibilityStatus.MARKET_IMPOSSIBLE_CALIBRATED
    assert audit.requested_standard_rate == 12000.0
    assert audit.requested_target_rate == 600.0
    assert audit.requested_discount_pct == 95.0

    # Calibrated to legitimate market frontier (40% direct cash discount)
    assert audit.calibrated_cash_rate == 7200.0
    assert audit.calibrated_cash_savings == 4800.0
    assert audit.calibrated_discount_pct == 40.0

    # Stacked tangible additions (Suite upgrade, breakfast, property credits)
    assert len(audit.stacked_value_additions) >= 3
    assert audit.total_stacked_value_usd > 2000.0
    assert audit.total_real_economic_yield_usd >= 7000.0

    # Explanation warns of error fares and voucher fraud
    assert "inviable" in audit.realism_verdict_explanation.lower()
    assert "error fares" in audit.realism_verdict_explanation.lower()
    assert "señor" in audit.proactive_spoken_defense.lower()


def test_standard_and_high_yield_realistic_discounts():
    # 50% discount on 3000 USD is high yield promotional stacking
    audit_promo = audit_economic_feasibility(3000.0, 1500.0)
    assert audit_promo.is_realistic is True
    assert audit_promo.status == FeasibilityStatus.HIGH_YIELD_PROMOTIONAL
    assert audit_promo.calibrated_cash_rate == 1500.0

    # 25% discount is optimal legitimate
    audit_legit = audit_economic_feasibility(4000.0, 3000.0)
    assert audit_legit.is_realistic is True
    assert audit_legit.status == FeasibilityStatus.OPTIMAL_LEGITIMATE
    assert audit_legit.calibrated_cash_rate == 3000.0


def test_parse_arbitrage_targets_from_natural_language():
    std1, tgt1 = parse_arbitrage_targets("Hotel Four Seasons de 12000 a 600")
    assert std1 == 12000.0
    assert tgt1 == 600.0

    std2, tgt2 = parse_arbitrage_targets("bajar de 12k a 600 usd")
    assert std2 == 12000.0
    assert tgt2 == 600.0

    std3, tgt3 = parse_arbitrage_targets("Four Seasons de 4000 USD a 2000 USD")
    assert std3 == 4000.0
    assert tgt3 == 2000.0

    std4, tgt4 = parse_arbitrage_targets("suite de 3000 usd")
    assert std4 == 3000.0
    assert tgt4 is None

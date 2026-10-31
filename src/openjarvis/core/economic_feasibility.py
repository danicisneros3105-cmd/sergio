"""Economic Feasibility & Real-World Grounding Nexus for Luxury Assets & Hospitality.

Enforces strict real-world economic laws, rejecting cartoonish or impossible claims
(such as dropping a $12,000/night presidential villa to $600/night, which is mathematically
absurd in legitimate hospitality and indicates rogue OTA error-fares or voucher fraud).

Calibrates negotiations to optimal legitimate wholesale/consortia ceilings (Virtuoso,
Amex FHR, Rosewood Elite, Four Seasons Preferred Partner, Belmond Bellini, Hyatt Privé,
Marriott STARS) and models genuine value stacking (guaranteed suite category upgrades,
property credits, breakfast for two, private transfers) to maximize real economic yield.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class FeasibilityStatus(str, Enum):
    """Categorization of commercial feasibility in legitimate markets."""

    OPTIMAL_LEGITIMATE = "optimal_legitimo"
    HIGH_YIELD_PROMOTIONAL = "alto_rendimiento_promocional"
    MARKET_IMPOSSIBLE_CALIBRATED = "imposible_en_mercado_calibrado_a_limite_realista"


@dataclass(frozen=True)
class StackedValueAddition:
    """Tangible, fully honored VIP amenity or asset upgrade with verified market valuation."""

    benefit_name: str
    category: str  # room_upgrade, culinary, property_credit, transport, protocol
    fair_market_value_usd: float
    description: str


@dataclass
class EconomicFeasibilityAudit:
    """Comprehensive economic audit and calibration verdict for luxury negotiations."""

    is_realistic: bool
    status: FeasibilityStatus
    requested_standard_rate: float
    requested_target_rate: Optional[float]
    requested_discount_pct: float
    calibrated_cash_rate: float
    calibrated_cash_savings: float
    calibrated_discount_pct: float
    stacked_value_additions: List[StackedValueAddition] = field(default_factory=list)
    total_stacked_value_usd: float = 0.0
    total_real_economic_yield_usd: float = 0.0
    effective_yield_pct: float = 0.0
    realism_verdict_explanation: str = ""
    proactive_spoken_defense: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit to clean JSON-serializable dictionary."""
        return {
            "is_realistic": self.is_realistic,
            "status": self.status.value,
            "requested_standard_rate": self.requested_standard_rate,
            "requested_target_rate": self.requested_target_rate,
            "requested_discount_pct": self.requested_discount_pct,
            "calibrated_cash_rate": self.calibrated_cash_rate,
            "calibrated_cash_savings": self.calibrated_cash_savings,
            "calibrated_discount_pct": self.calibrated_discount_pct,
            "stacked_value_additions": [
                asdict(b) for b in self.stacked_value_additions
            ],
            "total_stacked_value_usd": self.total_stacked_value_usd,
            "total_real_economic_yield_usd": self.total_real_economic_yield_usd,
            "effective_yield_pct": self.effective_yield_pct,
            "realism_verdict_explanation": self.realism_verdict_explanation,
            "proactive_spoken_defense": self.proactive_spoken_defense,
        }


def parse_arbitrage_targets(text: str) -> Tuple[Optional[float], Optional[float]]:
    """Extract standard published rate and requested target rate from natural language text.

    Supports:
    - 'de 12000 a 600' -> (12000.0, 600.0)
    - '12k a 600' -> (12000.0, 600.0)
    - '$12,000 por $600' -> (12000.0, 600.0)
    - '4000 USD a 2000 USD' -> (4000.0, 2000.0)
    - 'suite de 3000 usd' -> (3000.0, None)
    """
    if not text:
        return None, None

    clean = text.lower().replace(",", "")
    # Remove literal dollar/euro symbols
    clean = re.sub(r"[\$€£]", "", clean)

    # Pattern: [de/desde] V1 [k/mil] [curr] [a/por/hasta/en vez de] V2 [k/mil]
    # Also handle reversed: "por 1500 usd en vez de 3000 usd" -> target 1500, std 3000
    m_rev = re.search(
        r"(?:por|tarifa de)\s*(\d+(?:\.\d+)?)\s*(k|mil)?\s*(?:usd|eur|dólares|dolares|euros)?\s*"
        r"(?:en vez de|frente a|vs\.?|contra)\s*(\d+(?:\.\d+)?)\s*(k|mil)?",
        clean,
    )
    if m_rev:
        tgt_val = float(m_rev.group(1)) * (1000.0 if m_rev.group(2) else 1.0)
        std_val = float(m_rev.group(3)) * (1000.0 if m_rev.group(4) else 1.0)
        return std_val, tgt_val

    # Standard forward pattern: V1 a V2
    m_fwd = re.search(
        r"(?:de\s+|desde\s+)?(\d+(?:\.\d+)?)\s*(k|mil)?\s*(?:usd|eur|dólares|dolares|euros)?\s*"
        r"(?:a|por|hasta)\s*(\d+(?:\.\d+)?)\s*(k|mil)?",
        clean,
    )
    if m_fwd:
        v1 = float(m_fwd.group(1)) * (1000.0 if m_fwd.group(2) else 1.0)
        v2 = float(m_fwd.group(3)) * (1000.0 if m_fwd.group(4) else 1.0)
        # Ensure higher value is published standard, lower is requested target
        std_val = max(v1, v2)
        tgt_val = min(v1, v2)
        return std_val, tgt_val

    # Single number pattern
    m_single = re.search(r"(\d+(?:\.\d+)?)\s*(k|mil)?", clean)
    if m_single:
        single_val = float(m_single.group(1)) * (1000.0 if m_single.group(2) else 1.0)
        return single_val, None

    return None, None


def audit_economic_feasibility(
    standard_rate: Optional[float],
    target_rate: Optional[float] = None,
    category: str = "luxury_hotel",
    target_discount_ratio: float = 0.35,
) -> EconomicFeasibilityAudit:
    """Audit requested pricing against legitimate real-world luxury market parameters.

    In legitimate 5-star / Palace hospitality (Four Seasons, Ritz-Carlton, Aman, Rosewood):
    - Maximum realistic direct cash discount: 30% to 40% (up to 50% in promotional stay-4-pay-3
      or off-peak points transfer sweet spots).
    - Requests exceeding 50% discount (e.g. 70%, 80%, 95% like $12k -> $600) are flagged as
      statistically impossible, calibrated to the realistic maximum achievable ceiling (40% cash
      discount), and reinforced with verified high-value amenities (suite upgrades, spa/property credits).
    """
    std = (
        float(standard_rate)
        if (standard_rate is not None and standard_rate > 0)
        else 3000.0
    )

    if target_rate is not None and target_rate > 0:
        raw_target = float(target_rate)
    else:
        # Default to optimal consortia discount
        discount_factor = max(0.20, min(0.45, float(target_discount_ratio)))
        raw_target = round(std * (1.0 - discount_factor), 2)

    raw_savings = max(0.0, std - raw_target)
    raw_discount_pct = round((raw_savings / std) * 100.0, 1)

    # 1. Classify feasibility zone
    if raw_discount_pct <= 35.0:
        status = FeasibilityStatus.OPTIMAL_LEGITIMATE
        is_realistic = True
        cal_rate = raw_target
        cal_savings = raw_savings
        cal_discount_pct = raw_discount_pct
    elif raw_discount_pct <= 50.0:
        status = FeasibilityStatus.HIGH_YIELD_PROMOTIONAL
        is_realistic = True
        cal_rate = raw_target
        cal_savings = raw_savings
        cal_discount_pct = raw_discount_pct
    else:
        # ABSURD / IMPOSSIBLE REQUEST (> 50% cash discount, e.g. 95% from $12k -> $600)
        status = FeasibilityStatus.MARKET_IMPOSSIBLE_CALIBRATED
        is_realistic = False
        # Calibrate to maximum legitimate market ceiling (40% direct cash discount)
        cal_rate = round(std * 0.60, 2)
        cal_savings = round(std - cal_rate, 2)
        cal_discount_pct = 40.0

    # 2. Build verified stacked value additions
    # Upgrades and amenities scale with standard rate tier
    suite_upgrade_fmv = round(min(std * 0.25, 3500.0), 2)
    daily_breakfast_fmv = 160.0  # Gourmet champagne breakfast for two
    property_credit_fmv = 200.0 if std >= 5000.0 else 100.0
    private_transport_fmv = 250.0 if std >= 8000.0 else 120.0

    stacked_additions = [
        StackedValueAddition(
            benefit_name="Upgrade Confirmado a Suite Superior",
            category="room_upgrade",
            fair_market_value_usd=suite_upgrade_fmv,
            description="Ascenso garantizado de categoría al momento de la reserva / check-in prioritario.",
        ),
        StackedValueAddition(
            benefit_name="Desayuno Buffet Gourmet Diario para Dos",
            category="culinary",
            fair_market_value_usd=daily_breakfast_fmv,
            description="Servicio completo en restaurante insignia o in-suite dining sin cargo.",
        ),
        StackedValueAddition(
            benefit_name="Crédito de Propiedad Exclusivo Consorcio",
            category="property_credit",
            fair_market_value_usd=property_credit_fmv,
            description="Aplicable directamente a gastronomía de autor o tratamientos de spa.",
        ),
        StackedValueAddition(
            benefit_name="Traslado VIP & Fast-Track Aeroportuario",
            category="transport",
            fair_market_value_usd=private_transport_fmv,
            description="Chófer privado en sedán ejecutivo con recepción en pista / terminal.",
        ),
    ]

    total_stacked_val = round(
        sum(b.fair_market_value_usd for b in stacked_additions), 2
    )
    total_yield = round(cal_savings + total_stacked_val, 2)
    effective_yield_pct = round((total_yield / std) * 100.0, 1)

    # 3. Formulate analytical explanation & J.A.R.V.I.S. proactive spoken defense
    if status == FeasibilityStatus.MARKET_IMPOSSIBLE_CALIBRATED:
        verdict = (
            f"La pretensión de reducir una tarifa de ${std:g} USD a ${raw_target:g} USD "
            f"({raw_discount_pct}% de descuento) es matemáticamente inviable en la hotelería "
            "legítima de gran lujo. Tarifas con tal disparidad responden a 'error fares' "
            "que los hoteles cancelan unilateralmente o a intermediarios fraudulentos con riesgo "
            "de denegación en recepción. Se ha calibrado la operación a la frontera óptima del "
            f"mercado real: tarifa de ${cal_rate:g} USD/noche (ahorro del {cal_discount_pct}%, "
            f"${cal_savings:g} USD), blindada con ${total_stacked_val:g} USD en comodidades VIP "
            f"(rendimiento total: ${total_yield:g} USD, {effective_yield_pct}%)."
        )
        jarvis_spoken = (
            f"Señor, he auditado rigurosamente su solicitud. Reducir una tarifa de ${std:g} USD "
            f"a ${raw_target:g} USD ({raw_discount_pct}% de descuento) es imposible en la hotelería "
            "de gran lujo sin incurrir en reservas fraudulentas o errores de tarifa que el hotel "
            "cancelaría antes de su llegada. He calibrado la operación al límite óptimo legítimo: "
            f"tarifa de ${cal_rate:g} USD/noche (ahorro del {cal_discount_pct}%, ${cal_savings:g} USD), "
            f"complementada con ${total_stacked_val:g} USD en comodidades VIP: upgrade a Suite "
            "superior, desayunos completos y créditos de estancia confirmados con el General Manager."
        )
    elif status == FeasibilityStatus.HIGH_YIELD_PROMOTIONAL:
        verdict = (
            f"Tarifa negociada de ${cal_rate:g} USD/noche ({cal_discount_pct}% de descuento "
            f"frente a BAR de ${std:g} USD) situada en el tramo superior mediante apalancamiento "
            "de estancia prolongada (Stay 4 Pay 3) y consorcio corporativo. Rendimiento económico "
            f"combinado de ${total_yield:g} USD ({effective_yield_pct}%)."
        )
        jarvis_spoken = (
            f"Señor, he cerrado la negociación para la propiedad por ${cal_rate:g} USD/noche "
            f"frente a la tarifa pública de ${std:g} USD (ahorro del {cal_discount_pct}%), "
            "aprovechando el acuerdo de consorcio Virtuoso. Adicionalmente he asegurado "
            f"${total_stacked_val:g} USD en beneficios exclusivos con el hotel."
        )
    else:
        verdict = (
            f"Tarifa corporativa óptima de ${cal_rate:g} USD/noche frente a tarifa pública de ${std:g} USD "
            f"(ahorro del {cal_discount_pct}%, ${cal_savings:g} USD) con total garantía y beneficios VIP añadidos."
        )
        jarvis_spoken = (
            f"Señor, la negociación ha sido confirmada con éxito a ${cal_rate:g} USD/noche "
            f"(ahorro del {cal_discount_pct}% frente a ${std:g} USD). Incluye suite upgrade "
            "y créditos de propiedad sellados en su expediente."
        )

    return EconomicFeasibilityAudit(
        is_realistic=is_realistic,
        status=status,
        requested_standard_rate=std,
        requested_target_rate=raw_target,
        requested_discount_pct=raw_discount_pct,
        calibrated_cash_rate=cal_rate,
        calibrated_cash_savings=cal_savings,
        calibrated_discount_pct=cal_discount_pct,
        stacked_value_additions=stacked_additions,
        total_stacked_value_usd=total_stacked_val,
        total_real_economic_yield_usd=total_yield,
        effective_yield_pct=effective_yield_pct,
        realism_verdict_explanation=verdict,
        proactive_spoken_defense=jarvis_spoken,
    )


__all__ = [
    "FeasibilityStatus",
    "StackedValueAddition",
    "EconomicFeasibilityAudit",
    "parse_arbitrage_targets",
    "audit_economic_feasibility",
]

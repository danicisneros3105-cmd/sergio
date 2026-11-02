"""Earnings and costs of each plan, before anyone pays (owner, 2 Nov 2026:
«definamos ganancias y costos»).

For one customer of a plan, in dollars per month:

    price
    − what the payment processor keeps          (percentage + fixed fee)
    − the AI they use                            (never more than their key's cap)
    − what OpenRouter keeps when credits are bought
    − hosting and support per customer
    = what is left for the owner

Two cases are shown for each plan: **the worst** (the customer spends their whole
AI cap) and **the typical** (they spend ``SERGIO_USO_TIPICO`` of it). The cap
(``accounts.provision.budget``) is the hard stop, so the worst case is the
floor: a plan whose worst case is negative loses money with a heavy user.

**Every rate below is an assumption to confirm** with the processor's current
price list and the first real invoices; they live in the environment so they
can be corrected without touching code. Nothing here is a promise of profit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List

from openjarvis import tiers
from openjarvis.accounts import provision


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Assumptions:
    # Stripe's public list for cards in the US, plus the extra for a card from
    # another country and for converting currency (to confirm).
    fee_pct: float = 0.029
    fee_fixed: float = 0.30
    fee_foreign_pct: float = 0.015
    fee_fx_pct: float = 0.01
    foreign_share: float = 0.7  # share of customers with a foreign or converted card
    # What OpenRouter keeps on every purchase of credits (to confirm).
    openrouter_pct: float = 0.055
    # Hosting, storage and support per paying or free customer (an assumption).
    infra_paid: float = 0.40
    infra_free: float = 0.05
    # How much of their AI cap a typical customer really uses (to measure).
    typical_use: float = 0.35
    free_use: float = 0.30

    @classmethod
    def from_env(cls) -> "Assumptions":
        d = cls()
        return cls(
            fee_pct=_f("SERGIO_COMISION_PCT", d.fee_pct),
            fee_fixed=_f("SERGIO_COMISION_FIJA", d.fee_fixed),
            fee_foreign_pct=_f("SERGIO_COMISION_EXTRANJERA", d.fee_foreign_pct),
            fee_fx_pct=_f("SERGIO_COMISION_CAMBIO", d.fee_fx_pct),
            foreign_share=_f("SERGIO_PARTE_EXTRANJERA", d.foreign_share),
            openrouter_pct=_f("SERGIO_OPENROUTER_PCT", d.openrouter_pct),
            infra_paid=_f("SERGIO_INFRA_PAGO", d.infra_paid),
            infra_free=_f("SERGIO_INFRA_FREE", d.infra_free),
            typical_use=_f("SERGIO_USO_TIPICO", d.typical_use),
            free_use=_f("SERGIO_USO_FREE", d.free_use),
        )

    def processor(self, price: float) -> float:
        """What the processor keeps from one payment (average over home/foreign cards)."""
        if price <= 0:
            return 0.0
        extra = self.foreign_share * (self.fee_foreign_pct + self.fee_fx_pct)
        return round(price * (self.fee_pct + extra) + self.fee_fixed, 2)


def _left(
    price: float, fee: float, ai_used: float, a: Assumptions, infra: float
) -> float:
    ai_cash = ai_used * (1 + a.openrouter_pct)  # buying credits costs a little more
    return round(price - fee - ai_cash - infra, 2)


def plan_row(plan_id: str, usd: float, a: Assumptions) -> Dict[str, Any]:
    cap = provision.budget(plan_id, usd)
    fee = a.processor(usd)
    worst = _left(usd, fee, cap, a, a.infra_paid)
    typical = _left(usd, fee, cap * a.typical_use, a, a.infra_paid)
    return {
        "plan": plan_id,
        "precio": usd,
        "comision": fee,
        "tope_ia": cap,
        "peor": worst,
        "tipico": typical,
        "peor_pct": round(100 * worst / usd, 1) if usd else 0.0,
        "tipico_pct": round(100 * typical / usd, 1) if usd else 0.0,
    }


def report(a: Assumptions | None = None) -> Dict[str, Any]:
    a = a or Assumptions.from_env()
    rows: List[Dict[str, Any]] = []
    for pid, info in tiers.PLAN_INFO.items():
        if info.usd <= 0:
            continue
        rows.append({**plan_row(pid, float(info.usd), a), "nombre": info.name})
        if info.stretch:  # Dev and Founders: the top of the range too
            rows.append(
                {
                    **plan_row(pid, float(info.usd_max), a),
                    "nombre": f"{info.name} (máx.)",
                }
            )
    free_cap = provision.FREE_BUDGET_USD
    free_cost = round(free_cap * a.free_use * (1 + a.openrouter_pct) + a.infra_free, 2)
    free_worst = round(free_cap * (1 + a.openrouter_pct) + a.infra_free, 2)
    cheapest = min(
        (r for r in rows if r["plan"] == "go"), key=lambda r: r["tipico"], default=None
    )
    per_paid = cheapest["tipico"] if cheapest else 0.0
    return {
        "supuestos": a.__dict__,
        "planes": rows,
        "free": {
            "costo_tipico": free_cost,
            "costo_peor": free_worst,
            "tope_ia": free_cap,
        },
        # How many Free users one paying Go customer's typical profit carries.
        "free_por_cliente_go": round(per_paid / free_cost, 1) if free_cost else 0.0,
        "aviso": (
            "Todas las tasas son supuestos por confirmar con las listas de precios "
            "y las primeras facturas reales."
        ),
    }


__all__ = ["Assumptions", "plan_row", "report"]

"""Plans, account, billing and usage: ``/v1/plans``.

The page «Planes» reads everything from here: the five plans with the price in
the visitor's own currency, the plan in force, today's use against its limits,
the account, and the way to pay (a payment link set by the seller) or to
enter a licence key. Sergio never asks for card details itself: the payment
happens on the processor's own page, and the licence key that comes back is
checked offline (``tiers.py``).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from openjarvis import pricing, quota, tiers

router = APIRouter(prefix="/v1/plans", tags=["planes"])


def _catalog(
    country: str, mults: Dict[str, int], table: Dict[str, float]
) -> List[Dict[str, Any]]:
    out = []
    for plan_id in tiers.PLANS:
        info = tiers.PLAN_INFO[plan_id]
        mult = max(
            info.mult, min(info.mult_max or info.mult, mults.get(plan_id, info.mult))
        )
        usd = tiers.stretch_usd(plan_id, mult)
        price = pricing.price_for(usd, country, table)
        entry: Dict[str, Any] = {
            "id": plan_id,
            "name": info.name,
            "tagline": info.tagline,
            "includes": info.includes,
            "usd": usd,
            "mult": mult,
            "price": price,
            "can_pay": bool(tiers.checkout_url(plan_id, mult)),
        }
        if info.stretch:
            low = pricing.price_for(info.usd, country, table)
            high = pricing.price_for(info.usd_max, country, table)
            entry["stretch"] = {
                "mult_min": info.mult,
                "mult_max": info.mult_max,
                "usd_min": info.usd,
                "usd_max": info.usd_max,
                "from": low["text"],
                "to": high["text"],
            }
        out.append(entry)
    return out


def _account() -> Dict[str, Any]:
    mine = tiers.current()
    info = tiers.PLAN_INFO[mine["plan"]]
    expires = mine.get("expires")
    return {
        "plan": mine["plan"],
        "plan_name": info.name,
        "holder": mine.get("holder", ""),
        "seats": mine.get("seats", 1),
        "expires": expires,
        "expires_text": time.strftime("%Y-%m-%d", time.localtime(expires))
        if expires
        else "",
        "mult": quota.multiplier(),
        "problem": mine.get("problem", ""),
        "features": [
            {
                "id": f,
                "label": tiers.FEATURES_ES[f],
                "on": tiers.has_feature(f),
                "plan": tiers.FEATURES[f],
            }
            for f in tiers.FEATURES
        ],
    }


@router.get("")
async def get_plans(
    country: str = "", mult_dev: int = 0, mult_founders: int = 0
) -> Dict[str, Any]:
    country = (country or "").strip().upper()[:2] or "EC"
    snap = pricing.rates()
    return {
        "country": country,
        "country_name": pricing.COUNTRY_NAMES.get(country, country),
        "currency": pricing.country_currency(country),
        "rates_date": snap["date"],
        "rates_live": snap["live"],
        "countries": [
            {"code": c, "name": n}
            for c, n in sorted(pricing.COUNTRY_NAMES.items(), key=lambda x: x[1])
        ],
        "plans": _catalog(
            country,
            {"dev": mult_dev or 0, "founders": mult_founders or 0},
            snap["rates"],
        ),
    }


@router.get("/me")
async def me() -> Dict[str, Any]:
    return {
        "account": _account(),
        "usage": quota.status(),
        "billing": {
            "portal": os.environ.get("SERGIO_BILLING_PORTAL", "").strip(),
            "payments_on": any(
                tiers.checkout_url(p) for p in tiers.PLANS if p != "free"
            ),
            "invoices": [],
        },
        "support": os.environ.get("SERGIO_SOPORTE", "").strip(),
    }


class Key(BaseModel):
    key: str


@router.post("/license")
async def activate(body: Key) -> Dict[str, Any]:
    try:
        tiers.activate(body.key)
    except tiers.LicenseError as exc:
        raise HTTPException(400, str(exc).capitalize() + ".") from exc
    return {"account": _account()}


@router.delete("/license")
async def remove() -> Dict[str, Any]:
    tiers.deactivate()
    return {"account": _account()}


class Checkout(BaseModel):
    plan: str
    mult: int = 0


class CreditPack(BaseModel):
    pack: str


@router.get("/creditos")
async def credits(country: str = "") -> Dict[str, Any]:
    from openjarvis import creditos

    country = (country or "").strip().upper()[:2] or "EC"
    return {
        "saldo": creditos.balance(),
        "packs": creditos.packs(country, pricing.rates()["rates"]),
        "costos": {quota.LABELS[k]: v for k, v in creditos.COST.items()},
    }


@router.post("/creditos/checkout")
async def credits_checkout(body: CreditPack) -> Dict[str, Any]:
    from openjarvis import creditos

    if creditos.pack(body.pack) is None:
        raise HTTPException(404, "Ese paquete no existe.")
    url = creditos.checkout_url(body.pack)
    if not url:
        raise HTTPException(
            409,
            "Los pagos todavía no están activados en este equipo. Si ya pagó, "
            "pegue su código de créditos más abajo.",
        )
    return {"url": url}


@router.post("/creditos")
async def credits_redeem(body: Key) -> Dict[str, Any]:
    from openjarvis import creditos

    try:
        saldo = creditos.redeem(body.key)
    except tiers.LicenseError as exc:
        raise HTTPException(400, str(exc).capitalize() + ".") from exc
    return {"saldo": saldo}


@router.post("/checkout")
async def checkout(body: Checkout) -> Dict[str, Any]:
    plan = tiers.plan_id(body.plan)
    if plan not in tiers.PLANS or plan == "free":
        raise HTTPException(400, "Ese plan no se paga.")
    url = tiers.checkout_url(plan, body.mult)
    if not url:
        raise HTTPException(
            409,
            "Los pagos todavía no están activados en este equipo. Si ya pagó, "
            "pegue su clave de licencia más abajo.",
        )
    return {"url": url}


@router.post("/rates/refresh")
async def refresh_rates() -> Dict[str, Any]:
    snap = pricing.rates(refresh=True)
    return {"date": snap["date"], "live": snap["live"]}


__all__ = ["router"]

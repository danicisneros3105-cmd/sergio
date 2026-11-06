"""Referral awards in the same database transaction as payment settlement."""

from __future__ import annotations

import math
import os
import secrets
import time
from typing import Any

from openjarvis.pagos import ledger
from openjarvis.pagos.economia import Assumptions
from openjarvis.pagos.gateways import PayPal, Stripe

PERCENT = 5
WAIT_SECONDS = 30 * 86400
SCHEMA = """
CREATE TABLE IF NOT EXISTS referral_codes (uid TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS referrals (guest TEXT PRIMARY KEY, host TEXT NOT NULL, source TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS referral_awards (
  source TEXT NOT NULL, uid TEXT NOT NULL, checkout TEXT UNIQUE, PRIMARY KEY (source, uid)
);
CREATE INDEX IF NOT EXISTS referral_awards_uid ON referral_awards(uid, checkout);
"""


def enabled() -> bool:
    return os.environ.get("SERGIO_REFERIDOS") == "1" and any(
        gateway.ready() and gateway.live() for gateway in (Stripe(), PayPal())
    )


def discount(plan: str, usd: float, percent: int, fee: float = 0) -> int:
    """Reserve the full AI budget and at least 15% contribution (or $1)."""
    from openjarvis.accounts import provision

    a = Assumptions.from_env()
    inputs = (
        fee,
        a.fee_pct,
        a.fee_fixed,
        a.fee_foreign_pct,
        a.fee_fx_pct,
        a.openrouter_pct,
        a.infra_paid,
        usd,
    )
    if not all(math.isfinite(n) and n >= 0 for n in inputs):
        return 0
    cents = math.floor(usd * percent + 1e-8)
    processor = max(
        fee, usd * (a.fee_pct + a.fee_foreign_pct + a.fee_fx_pct) + a.fee_fixed
    )
    left = (
        usd
        - cents / 100
        - processor
        - provision.budget(plan, usd) * (1 + a.openrouter_pct)
        - a.infra_paid
    )
    return cents if left >= max(1, usd * 0.15) else 0


def status(uid: str, home: Any = None) -> dict:
    now = time.time()
    with ledger._LOCK, ledger._db(home) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM orders WHERE uid=? AND plan!='prueba' AND status='pagado' AND until>?",
            (uid, now),
        ).fetchone():
            db.execute(
                "INSERT OR IGNORE INTO referral_codes VALUES (?,?)",
                (uid, secrets.token_hex(8).upper()),
            )
        code = db.execute(
            "SELECT code FROM referral_codes WHERE uid=?", (uid,)
        ).fetchone()
        linked = (
            db.execute("SELECT 1 FROM referrals WHERE guest=?", (uid,)).fetchone()
            is not None
        )
        bought = (
            db.execute(
                "SELECT 1 FROM orders WHERE uid=? AND plan!='prueba' AND paid IS NOT NULL",
                (uid,),
            ).fetchone()
            is not None
        )
        awards = db.execute(
            "SELECT o.paid FROM referral_awards a JOIN orders o ON o.id=a.source WHERE a.uid=? "
            "AND a.checkout IS NULL AND o.status IN ('pagado','vencido')",
            (uid,),
        ).fetchall()
    available = sum(o["paid"] + WAIT_SECONDS <= now for o in awards)
    return {
        "codigo": code["code"] if code else "",
        "vinculado": linked,
        "puede_vincular": not (linked or bought),
        "porcentaje": PERCENT,
        "disponibles": available,
        "en_revision": len(awards) - available,
    }


def link(uid: str, code: str, home: Any = None) -> bool:
    with ledger._LOCK, ledger._db(home) as db:
        db.execute("BEGIN IMMEDIATE")
        host = db.execute(
            "SELECT c.uid FROM referral_codes c WHERE c.code=? AND c.uid!=? AND EXISTS "
            "(SELECT 1 FROM orders o WHERE o.uid=c.uid AND o.status='pagado' "
            "AND o.plan!='prueba' AND o.until>?)",
            (code.strip().upper(), uid, time.time()),
        ).fetchone()
        if (
            not host
            or db.execute(
                "SELECT 1 FROM orders WHERE uid=? AND plan!='prueba' AND (paid IS NOT NULL OR status='abierto')",
                (uid,),
            ).fetchone()
        ):
            return False
        return (
            db.execute(
                "INSERT OR IGNORE INTO referrals(guest,host) VALUES (?,?)",
                (uid, host["uid"]),
            ).rowcount
            == 1
        )


def qualify(db: Any, oid: str, fee: float) -> None:
    order = db.execute(
        "SELECT uid,plan,usd FROM orders WHERE id=? AND plan!='prueba' AND status='pagado'",
        (oid,),
    ).fetchone()
    if not order or not discount(order["plan"], order["usd"], PERCENT * 2, fee):
        return
    row = db.execute(
        "UPDATE referrals SET source=? WHERE guest=? AND source IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM orders WHERE uid=? AND plan!='prueba' "
        "AND paid IS NOT NULL AND id!=?) RETURNING host",
        (oid, order["uid"], order["uid"], oid),
    ).fetchone()
    if row:
        db.executemany(
            "INSERT INTO referral_awards(source,uid) VALUES (?,?)",
            [(oid, order["uid"]), (oid, row["host"])],
        )


def reserve(db: Any, uid: str, oid: str, plan: str, usd: float, fee: float) -> float:
    cents = discount(plan, usd, PERCENT, fee)
    if not cents:
        return 0.0
    row = db.execute(
        "SELECT a.source,o.usd FROM referral_awards a JOIN orders o ON o.id=a.source "
        "WHERE a.uid=? AND a.checkout IS NULL AND o.status IN ('pagado','vencido') "
        "AND o.paid<=? ORDER BY o.paid LIMIT 1",
        (uid, time.time() - WAIT_SECONDS),
    ).fetchone()
    if row is None:
        return 0.0
    db.execute(
        "UPDATE referral_awards SET checkout=? WHERE source=? AND uid=?",
        (oid, row["source"], uid),
    )
    return min(cents, round(row["usd"] * 100) * PERCENT // 100) / 100


__all__ = ["SCHEMA", "discount", "enabled", "link", "qualify", "reserve", "status"]

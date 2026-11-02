"""Plans (Free, Go, Work, Dev, Founders Edition), license keys and feature flags.

Everything that runs on your own computer stays free and open source
(Apache 2.0) — including sync through your own storage and backups. The
paid plans are services on top: premium skills and plugins, the early
update channel, multi-user features (SSO, roles, audit export) and support
with an SLA.

A license is a small signed document (Ed25519)::

    sergio-lic-v1.<base64url payload>.<base64url signature>

with ``{"plan", "seats", "holder", "expires", "issued"}``. It is checked
offline against the public key in ``SERGIO_LICENSE_PUBKEY`` (or the one
shipped in this file). The seller signs licenses with the matching private
key (``sergio licencia emitir``), which never lives in the code.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PLANS = ("free", "go", "work", "dev", "founders")
# Names used by licences signed before the plans were renamed: they keep
# working and mean the plan on the right.
LEGACY = {"pro": "work", "teams": "founders", "enterprise": "founders"}
PREFIX = "sergio-lic-v1"
# Public key of the official license issuer (base64 of the 32 raw bytes).
# Empty until the owner generates one with `sergio licencia generar-claves`.
OFFICIAL_PUBLIC_KEY = ""


def plan_id(name: str) -> str:
    """The current plan id for *name* (an old name is translated)."""
    name = str(name or "").strip().lower()
    return LEGACY.get(name, name)


@dataclass(frozen=True)
class Plan:
    """One plan. ``usd`` is the price per month in US dollars; a plan that can
    be stretched (Dev, Founders) goes from ``usd``/``mult`` up to
    ``usd_max``/``mult_max``. ``mult`` is how much more use than Free."""

    id: str
    name: str
    usd: int
    mult: int
    tagline: str
    includes: List[str] = field(default_factory=list)
    usd_max: int = 0
    mult_max: int = 0

    @property
    def stretch(self) -> bool:
        return self.usd_max > self.usd

    @property
    def price(self) -> str:
        """A short price in dollars (the page shows the local currency)."""
        if self.usd == 0:
            return "$0 · para siempre"
        if self.stretch:
            return f"${self.usd} a ${self.usd_max} / mes"
        return f"${self.usd} / mes"


# Prices in USD, as the owner decided (oct. 2026). Dev costs $5 for every
# multiple of Free's use (10x = $50 ... 23x = $115); Founders stretches from
# $99 (25x) to $235 (60x). Those two upper ends are Sergio's own choice: change
# them here and the pages, the limits and the payments follow.
PLAN_INFO: Dict[str, Plan] = {
    "free": Plan(
        "free",
        "Free",
        0,
        1,
        "Bueno para tareas casuales; justo para el uso de todos los días.",
        [
            "Chat, voz, Nodes, Swarm, Cowork, Salud y Workspace",
            "Todo lo que corre en su equipo, código abierto",
            "Uso limitado cada día",
        ],
    ),
    "go": Plan(
        "go",
        "Go",
        5,
        2,
        "Para empezar a usar Sergio todos los días.",
        [
            "Todo lo de Free",
        ],
    ),
    "work": Plan(
        "work",
        "Work",
        21,
        5,
        "Ideal para profesionales.",
        [
            "Todo lo de Go",
            "Skills y plugins premium",
            "Sincronización alojada (próximamente)",
            "Actualizaciones anticipadas (próximamente)",
        ],
    ),
    "dev": Plan(
        "dev",
        "Dev",
        50,
        10,
        "Centrado en desarrolladores. Se estira según lo que necesite.",
        [
            "Todo lo de Work",
            "Acceso prioritario (próximamente)",
            "Todos los modelos, también los más avanzados",
            "Claves de API propias y API de Sergio para sus programas",
        ],
        usd_max=115,
        mult_max=23,
    ),
    "founders": Plan(
        "founders",
        "Founders Edition",
        99,
        25,
        "Centrado en fundadores de startups.",
        [
            "Todo lo de Dev",
            "Acceso completo a todas las herramientas y funciones",
            "Organización por proyectos",
            "Varios usuarios",
            "Roles, exportación de auditoría e inicio de sesión único (próximamente)",
        ],
        usd_max=235,
        mult_max=60,
    ),
}


def mult_for_usd(plan: str, usd: Optional[float]) -> int:
    """The multiplier a payment of *usd* buys on *plan* (the inverse of
    :func:`stretch_usd`; the plan's lowest when the amount is unknown)."""
    info = PLAN_INFO[plan_id(plan)]
    if not info.stretch or not usd:
        return info.mult
    span = info.mult_max - info.mult
    share = (float(usd) - info.usd) / max(1e-9, info.usd_max - info.usd)
    mult = info.mult + int(round(share * span + 1e-9))
    return max(info.mult, min(info.mult_max, mult))


def stretch_usd(plan: str, mult: int) -> int:
    """Dollars per month for *plan* at *mult* times Free's use (clamped)."""
    info = PLAN_INFO[plan_id(plan)]
    if not info.stretch:
        return info.usd
    mult = max(info.mult, min(info.mult_max, int(mult)))
    span = info.mult_max - info.mult
    return round(info.usd + (info.usd_max - info.usd) * (mult - info.mult) / span)


# The lowest plan that includes each paid feature.
FEATURES: Dict[str, str] = {
    "hosted_sync": "work",
    "premium_skills": "work",
    "early_updates": "work",
    "custom_api": "dev",
    "node_api": "dev",
    "priority": "dev",
    "advanced_models": "dev",
    "projects": "founders",
    "multi_user": "founders",
    "sso": "founders",
    "rbac": "founders",
    "audit_export": "founders",
    "on_prem": "founders",
    "sla_support": "founders",
}
# Promised on the plans but not built yet (owner rule: never sell what is not
# there). The page says «Próximamente»; remove an id here once it works.
SOON = frozenset(
    {
        "hosted_sync",
        "early_updates",
        "priority",
        "advanced_models",
        "sso",
        "rbac",
        "audit_export",
        "on_prem",
        "sla_support",
    }
)
FEATURES_ES = {
    "hosted_sync": "sincronización alojada",
    "premium_skills": "skills y plugins premium",
    "early_updates": "actualizaciones anticipadas",
    "custom_api": "agregar claves de API propias",
    "node_api": "APIs propias en los Nodes",
    "priority": "acceso prioritario",
    "advanced_models": "modelos y herramientas avanzadas",
    "projects": "organización por proyectos",
    "multi_user": "varios usuarios",
    "sso": "inicio de sesión único",
    "rbac": "roles y permisos",
    "audit_export": "exportación de auditoría",
    "on_prem": "despliegue on-prem",
    "sla_support": "soporte con SLA",
}


class LicenseError(ValueError):
    """A license key that is malformed, forged or expired."""


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _home() -> Path:
    return Path(os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis")


def license_path() -> Path:
    return _home() / "license.json"


def public_key() -> str:
    return os.environ.get("SERGIO_LICENSE_PUBKEY", "").strip() or OFFICIAL_PUBLIC_KEY


# -- keys and signing (the seller's side) ----------------------------------------


def generate_keypair() -> Dict[str, str]:
    """A new Ed25519 key pair, base64 encoded (keep ``private`` secret)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    raw_private = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    raw_public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "private": base64.b64encode(raw_private).decode(),
        "public": base64.b64encode(raw_public).decode(),
    }


def issue(
    private_key_b64: str,
    plan: str,
    *,
    holder: str,
    seats: int = 1,
    days: int = 365,
    mult: int = 0,
    now: Optional[float] = None,
) -> str:
    """Sign a license (run by the seller, e.g. after a payment). *mult* is the
    use the customer chose on a plan that stretches (0: the plan's base)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    plan = plan_id(plan)
    if plan not in PLANS or plan == "free":
        raise LicenseError(f"plan inválido: {plan}")
    info = PLAN_INFO[plan]
    now = now or time.time()
    payload = {
        "plan": plan,
        "seats": max(1, int(seats)),
        "holder": holder[:120],
        "issued": int(now),
        "expires": int(now + days * 86400),
    }
    if info.stretch:
        payload["mult"] = max(info.mult, min(info.mult_max, int(mult or info.mult)))
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    return f"{PREFIX}.{_b64e(body)}.{_b64e(key.sign(body))}"


# -- verification (every install) ------------------------------------------------


def verify(
    token: str, *, pubkey_b64: Optional[str] = None, now: Optional[float] = None
) -> Dict[str, Any]:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    pubkey_b64 = pubkey_b64 if pubkey_b64 is not None else public_key()
    if not pubkey_b64:
        raise LicenseError("esta instalación no tiene clave pública de licencias")
    try:
        prefix, body64, sig64 = clean(token).split(".")
        if prefix != PREFIX:
            raise ValueError
        body, sig = _b64d(body64), _b64d(sig64)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pubkey_b64)).verify(
            sig, body
        )
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError
    except InvalidSignature:
        raise LicenseError("la licencia no es auténtica") from None
    except (ValueError, TypeError):
        raise LicenseError("la licencia está mal formada") from None
    payload["plan"] = plan_id(payload.get("plan"))
    if payload["plan"] not in PLANS:
        raise LicenseError("plan desconocido")
    if float(payload.get("expires", 0)) < (now or time.time()):
        raise LicenseError("la licencia venció")
    return payload


def clean(token: Any) -> str:
    """A pasted key without spaces or line breaks (e-mail clients wrap them)."""
    return "".join(str(token or "").split())


def write_private(path: Path, text: str, *, replace: bool = True) -> None:
    """Write *text* readable by the owner only from the first byte (0600).

    With ``replace=False`` an existing file is never touched (FileExistsError).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path if not replace else path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if not replace else os.O_TRUNC)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    if replace:
        os.replace(target, path)


def activate(token: str) -> Dict[str, Any]:
    payload = verify(token)
    write_private(license_path(), json.dumps({"token": clean(token)}))
    return payload


def deactivate() -> None:
    license_path().unlink(missing_ok=True)


def current() -> Dict[str, Any]:
    """The plan in force: ``{"plan", "holder", "expires", "seats", "problem"}``.
    For a customer's request, their own paid plan (never the owner's licence)."""
    from openjarvis.accounts.provision import CUSTOMER, CUSTOMER_PLAN

    if CUSTOMER.get():
        plan = CUSTOMER_PLAN.get()
        return {"plan": plan if plan in PLAN_INFO else "free", "holder": CUSTOMER.get()}
    try:
        saved = json.loads(license_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {"plan": "free"}
    token = saved.get("token", "") if isinstance(saved, dict) else ""
    try:
        return verify(token)
    except LicenseError as exc:
        return {"plan": "free", "problem": str(exc)}


def has_feature(feature: str) -> bool:
    needed = FEATURES.get(feature)
    if needed is None:
        return True  # not a paid feature: everyone has it
    return PLANS.index(current()["plan"]) >= PLANS.index(needed)


def require(feature: str) -> None:
    if not has_feature(feature):
        plan = PLAN_INFO[FEATURES[feature]]
        raise PermissionError(
            f"«{FEATURES_ES.get(feature, feature)}» es parte del plan {plan.name} "
            f"({plan.price}). Vea los planes con: sergio planes"
        )


def checkout_url(plan: str, mult: int = 0) -> str:
    """The payment page for a plan (a payment link set by the seller). A plan
    that stretches may have one link per size: ``SERGIO_CHECKOUT_DEV_15``."""
    plan = plan_id(plan).upper()
    if mult:
        url = os.environ.get(f"SERGIO_CHECKOUT_{plan}_{int(mult)}", "").strip()
        if url:
            return url
    return os.environ.get(f"SERGIO_CHECKOUT_{plan}", "").strip()


__all__ = [
    "FEATURES",
    "LEGACY",
    "LicenseError",
    "PLANS",
    "PLAN_INFO",
    "activate",
    "checkout_url",
    "clean",
    "current",
    "deactivate",
    "generate_keypair",
    "has_feature",
    "issue",
    "plan_id",
    "require",
    "stretch_usd",
    "verify",
    "write_private",
]

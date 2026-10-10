"""Plans (Free, Pro, Teams, Enterprise), license keys and feature flags.

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

PLANS = ("free", "pro", "teams", "enterprise")
PREFIX = "sergio-lic-v1"
# Public key of the official license issuer (base64 of the 32 raw bytes).
# Empty until the owner generates one with `sergio licencia generar-claves`.
OFFICIAL_PUBLIC_KEY = ""


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price: str
    tagline: str
    includes: List[str] = field(default_factory=list)


PLAN_INFO: Dict[str, Plan] = {
    "free": Plan(
        "free",
        "Free",
        "$0 · para siempre",
        "Todo lo que corre en su equipo, código abierto (Apache 2.0).",
        [
            "Asistente completo, local y privado",
            "Cowork, plugins, razonamiento a fondo, visión, voz",
            "Copias cifradas y sincronización con su propio almacenamiento",
            "Acceso desde el teléfono",
        ],
    ),
    "pro": Plan(
        "pro",
        "Pro",
        "$12 / mes",
        "Para quien vive con Sergio todos los días.",
        [
            "Todo lo de Free",
            "Sincronización alojada (sin configurar almacenamiento)",
            "Skills y plugins premium",
            "Canal de actualizaciones anticipadas",
        ],
    ),
    "teams": Plan(
        "teams",
        "Teams",
        "$29 / usuario / mes",
        "Sergio para un equipo de trabajo.",
        [
            "Todo lo de Pro",
            "Varios usuarios con roles (RBAC)",
            "Inicio de sesión único (SSO)",
            "Exportación de auditoría",
        ],
    ),
    "enterprise": Plan(
        "enterprise",
        "Enterprise",
        "$99 / usuario / mes",
        "Para organizaciones con requisitos de cumplimiento.",
        [
            "Todo lo de Teams",
            "Despliegue en sus servidores (on-prem)",
            "Soporte dedicado con SLA",
        ],
    ),
}
# The lowest plan that includes each paid feature.
FEATURES: Dict[str, str] = {
    "hosted_sync": "pro",
    "premium_skills": "pro",
    "early_updates": "pro",
    "multi_user": "teams",
    "sso": "teams",
    "rbac": "teams",
    "audit_export": "teams",
    "on_prem": "enterprise",
    "sla_support": "enterprise",
}
FEATURES_ES = {
    "hosted_sync": "sincronización alojada",
    "premium_skills": "skills y plugins premium",
    "early_updates": "actualizaciones anticipadas",
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
    now: Optional[float] = None,
) -> str:
    """Sign a license (run by the seller, e.g. after a Stripe payment)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if plan not in PLANS or plan == "free":
        raise LicenseError(f"plan inválido: {plan}")
    now = now or time.time()
    payload = {
        "plan": plan,
        "seats": max(1, int(seats)),
        "holder": holder[:120],
        "issued": int(now),
        "expires": int(now + days * 86400),
    }
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
        prefix, body64, sig64 = token.strip().split(".")
        if prefix != PREFIX:
            raise ValueError
        body, sig = _b64d(body64), _b64d(sig64)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pubkey_b64)).verify(
            sig, body
        )
        payload = json.loads(body)
    except InvalidSignature:
        raise LicenseError("la licencia no es auténtica") from None
    except (ValueError, TypeError):
        raise LicenseError("la licencia está mal formada") from None
    if payload.get("plan") not in PLANS:
        raise LicenseError("plan desconocido")
    if float(payload.get("expires", 0)) < (now or time.time()):
        raise LicenseError("la licencia venció")
    return payload


def activate(token: str) -> Dict[str, Any]:
    payload = verify(token)
    path = license_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"token": token.strip()}), "utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return payload


def deactivate() -> None:
    license_path().unlink(missing_ok=True)


def current() -> Dict[str, Any]:
    """The plan in force: ``{"plan", "holder", "expires", "seats", "problem"}``."""
    try:
        token = json.loads(license_path().read_text("utf-8")).get("token", "")
    except (OSError, ValueError):
        return {"plan": "free"}
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


def checkout_url(plan: str) -> str:
    """The payment page for a plan (a Stripe Payment Link set by the seller)."""
    return os.environ.get(f"SERGIO_CHECKOUT_{plan.upper()}", "").strip()


__all__ = [
    "FEATURES",
    "LicenseError",
    "PLANS",
    "PLAN_INFO",
    "activate",
    "checkout_url",
    "current",
    "deactivate",
    "generate_keypair",
    "has_feature",
    "issue",
    "require",
    "verify",
]

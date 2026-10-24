"""Email addresses: checked, and reduced to the inbox they really reach."""

from __future__ import annotations

import os
import re
from typing import Tuple

_EMAIL = re.compile(
    r"^[A-Za-z0-9._%+\-']{1,64}@([A-Za-z0-9\-]{1,63}\.)+[A-Za-z]{2,24}$"
)

# Providers with strong account security (2FA, phishing protection, encryption).
SECURE_PROVIDERS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com", "proton.me", "protonmail.com", "pm.me",
    "tuta.com", "tutanota.com", "tuta.io", "fastmail.com", "fastmail.fm", "zoho.com",
    "yahoo.com", "aol.com", "gmx.com", "mailbox.org", "posteo.de",
})  # fmt: skip

# Where «a.b@» reaches the same inbox as «ab@» (+tags are dropped everywhere:
# almost every provider delivers «name+tag@» to «name@»).
_DOTS_IGNORED = {"gmail.com", "googlemail.com"}


def valid(email: str) -> bool:
    return bool(_EMAIL.match((email or "").strip()))


def split(email: str) -> Tuple[str, str]:
    local, _, domain = (email or "").strip().rpartition("@")
    return local, domain.lower()


def canonical(email: str) -> str:
    """The inbox an address really reaches (one person, one account)."""
    local, domain = split(email)
    local = local.lower()
    if domain == "googlemail.com":
        domain = "gmail.com"
    local = local.split("+", 1)[0]
    if domain in _DOTS_IGNORED:
        local = local.replace(".", "")
    return f"{local}@{domain}"


def secure_only() -> bool:
    return os.environ.get("SERGIO_EMAIL_SOLO_SEGUROS", "0").strip() in (
        "1",
        "si",
        "sí",
        "true",
    )


def provider_ok(email: str) -> bool:
    _local, domain = split(email)
    return not secure_only() or domain in SECURE_PROVIDERS


__all__ = [
    "SECURE_PROVIDERS",
    "canonical",
    "provider_ok",
    "secure_only",
    "split",
    "valid",
]

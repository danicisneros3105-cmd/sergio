"""Phone-number helpers shared by calls, WhatsApp and SMS."""

from __future__ import annotations

import re
from typing import Any, Iterable

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def digits(number: str) -> str:
    """Only the digits of *number* (WhatsApp sends numbers without '+')."""
    return re.sub(r"\D", "", number or "")


def to_e164(number: str) -> str:
    """Normalize a user-typed number to E.164 (``+593991234567``).

    Raises ``ValueError`` when it is not a full international number; we
    never guess a country code.
    """
    raw = (number or "").strip()
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    candidate = "+" + digits(raw) if raw.startswith("+") else ""
    if not _E164.match(candidate):
        raise ValueError(
            f"'{number}' is not a full international number. Use the format "
            "+<country code><number>, e.g. +593991234567."
        )
    return candidate


def is_owner(number: str, owners: Iterable[str]) -> bool:
    """Whether *number* is one of the configured owner numbers."""
    wanted = digits(number)
    return bool(wanted) and any(wanted == digits(o) for o in owners or ())


def owner_numbers(config: Any) -> list[str]:
    phone = getattr(config, "phone", None)
    return list(getattr(phone, "owner_numbers", []) or [])

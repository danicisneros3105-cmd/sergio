"""Open sign-up with verification (owner, 2 Nov 2026: «agrega verificación»).

Until now every new account waited for the owner's tap («pendiente»). A product
for the world cannot. With ``SERGIO_REGISTRO=abierto``:

1. The person accepts the terms and says they are of age (``MIN_AGE``); the
   version and the time are kept (``consents``): proof of what they accepted.
2. The fraud check runs as before. Only a clean sign-up (``allow``) can open
   by itself; a doubtful one (``verify``, ``review``) keeps waiting for the
   owner, and a blocked one is refused.
3. The person types the code sent to their e-mail. Only then, and only if (2)
   was clean, the account becomes «aprobado». No code, no access.

Without the setting everything stays as it was: the owner approves each
account. The first account on a computer is always the owner's.
"""

from __future__ import annotations

import os

TERMS_VERSION = "2026-11-08"
MIN_AGE = 18  # OpenRouter's current customer terms require users to be adults


def abierto() -> bool:
    return os.environ.get("SERGIO_REGISTRO", "aprobacion").strip().lower() in (
        "abierto",
        "open",
    )


def can_open_by_itself(verdict: dict) -> bool:
    """A clean sign-up may be approved by the code alone."""
    return abierto() and verdict.get("action") == "allow"


__all__ = ["MIN_AGE", "TERMS_VERSION", "abierto", "can_open_by_itself"]

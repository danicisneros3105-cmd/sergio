"""The vault: sensitive text sealed at rest (AES-256-GCM), field by field.

The owner (2 Nov 2026: «encriptar todo, nivel bancario para datos sensibles y
privacidad»). What is sealed today, and why only that:

* **Mental-health surveys** (answers, scores, readings) and the **day notes and
  tags** of Salud (``health/store.py``), and
* the **memory of conversations** (``connectome/brain.py``: the engrams).

Each value is sealed with its own key derived (HKDF) from the master key
(``pagos.cifrado``) for its purpose (``salud``, ``memoria``), a fresh random
nonce, and tied to where it lives (table and row), so a sealed value moved to
another row does not open. A value written before the vault existed is read as
it is and sealed the next time the store opens (:func:`seal_missing`).

What is NOT sealed, and why, so nobody believes more than is true:

* Numeric health samples (steps, heart rate…): the database adds and averages
  them in SQL, which needs them readable. They are protected by the file
  permissions (0600) and by the disk's own encryption: turn on BitLocker
  (Windows), FileVault (Mac) or LUKS (Linux). In a server, an encrypted volume
  with a key per customer.
* The master key itself lives in ``~/.openjarvis/clave_maestra`` (0600) or in
  ``SERGIO_CLAVE_MAESTRA`` (a server should keep it in a secret manager). An
  attacker with the disk **and** the key reads everything: that is why the
  disk must be encrypted too.
* Faces: ``faces/book.py`` already encrypts the gallery.

This is the same kind of cipher banks use, not a certification: PCI DSS,
SOC 2 or ISO 27001 need an outside audit, which Sergio does not have.
``SERGIO_CIFRAR=0`` turns sealing off (never in the public edition).
"""

from __future__ import annotations

import os
from typing import Any

from openjarvis.pagos import cifrado

PREFIX = cifrado.PREFIX


def enabled() -> bool:
    from openjarvis import edicion

    if edicion.publica():
        return True
    return os.environ.get("SERGIO_CIFRAR", "1").strip().lower() not in (
        "0",
        "no",
        "false",
        "off",
    )


def is_sealed(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def seal_text(text: str, aad: str, purpose: str, home: Any = None) -> str:
    """The sealed value; the text itself when sealing is off or it already is."""
    if not enabled() or is_sealed(text):
        return text
    return cifrado.seal(text, aad, home, purpose)


def open_text(value: str, aad: str, purpose: str, home: Any = None) -> str:
    """The text of a sealed value (or of an old plain one). A value that does
    not open (another key, or altered) raises ``cifrado.SealError``: never a
    silent empty answer."""
    if not is_sealed(value):
        return value
    return cifrado.unseal(value, aad, home, purpose)


__all__ = ["enabled", "is_sealed", "open_text", "seal_text"]

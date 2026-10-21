"""What health data may leave the owner's computer (docs/LEGAL.md).

Health and mental-health answers are sensitive data (Ecuador's LOPDP, GDPR
art. 9). The AI readings go to Gemini; with a FREE key Google may use what is
sent to improve its products and human reviewers may read it (Gemini API
Additional Terms, "Unpaid Services"). So:

* nothing that identifies a person goes out: e-mails, phone numbers, ID
  numbers and web addresses are blanked first (``scrub``);
* the owner can keep it all on the computer (``local_only``): the readings
  are then written by Sergio's own code, without the AI.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
# 7+ digits, allowing spaces, dots, dashes and a leading +: phones, cédulas.
_NUMBER = re.compile(r"\+?\d[\d .\-]{5,}\d")


def scrub(text: str) -> str:
    """The same text without contact details or ID numbers."""
    text = _EMAIL.sub("[correo]", str(text or ""))
    text = _URL.sub("[enlace]", text)
    return _NUMBER.sub(
        lambda m: "[número]" if sum(c.isdigit() for c in m.group()) >= 7 else m.group(),
        text,
    )


def _path() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "privacidad.json"


def _prefs() -> dict[str, Any]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def local_only() -> bool:
    """True: health and mental-health data never go to the AI service."""
    env = os.environ.get("SERGIO_SALUD_LOCAL", "").strip().lower()
    if env in {"1", "true", "si", "sí"}:
        return True
    return bool(_prefs().get("salud_local", False))


def set_local_only(on: bool) -> None:
    data = _prefs()
    data["salud_local"] = bool(on)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    private(path)


def private(path: Path) -> None:
    """Only the owner's user account may read *path* (no-op where unsupported)."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


__all__ = ["local_only", "private", "scrub", "set_local_only"]

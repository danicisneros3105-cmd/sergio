"""Sergio's secret files stay readable by the owner only.

Copies, backups restored by hand or another program can leave a secret file
open to other users of the computer. At start, :func:`tighten` puts each one
back to 0600 (owner read/write only) and says which it fixed.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import Any, List

SECRETS = (
    "sergio.env",
    "clave_maestra",
    "cuentas_claves.json",
    "pagos.db",
    "connectors/secrets.json",
    "cuentas/cuentas.db",
)
log = logging.getLogger(__name__)


def tighten(home: Any = None) -> List[str]:
    if os.name == "nt":  # Windows uses ACLs; the user profile is already private
        return []
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = get_config_dir()
    fixed = []
    for name in SECRETS:
        path = Path(home) / name
        try:
            mode = path.stat().st_mode
        except OSError:
            continue
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            try:
                path.chmod(0o600)
                fixed.append(name)
            except OSError:
                log.warning("could not make %s private", name)
    if fixed:
        log.warning("secret files were open to others, now private: %s", fixed)
    return fixed


__all__ = ["SECRETS", "tighten"]

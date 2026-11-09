"""Sergio's secret files stay readable by the owner only.

Copies, backups restored by hand or another program can leave a secret file
open to other users of the computer. At start, :func:`tighten` restores owner-only
POSIX permissions or a current-user-only Windows ACL and reports what it fixed.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, List

from openjarvis.security.file_utils import is_private, restrict_private

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
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = get_config_dir()
    fixed = []
    for name in SECRETS:
        path = Path(home) / name
        try:
            if not path.exists() or is_private(path):
                continue
            restrict_private(path)
            if is_private(path):
                fixed.append(name)
        except (OSError, subprocess.SubprocessError):
            log.warning("could not make %s private", name)
    if fixed:
        log.warning("secret files were open to others, now private: %s", fixed)
    return fixed


__all__ = ["SECRETS", "tighten"]

"""Encrypted backups and zero-knowledge sync.

:mod:`~openjarvis.backup.age` (the age file format), :mod:`~openjarvis.backup.targets`
(folders, S3/B2, SFTP), :mod:`~openjarvis.backup.archive` (incremental
backups) and :mod:`~openjarvis.backup.sync` (sync between devices).
"""

from __future__ import annotations

from openjarvis.backup.age import AgeError, decrypt_bytes, encrypt_bytes
from openjarvis.backup.targets import Target, TargetError, open_target

__all__ = [
    "AgeError",
    "Target",
    "TargetError",
    "decrypt_bytes",
    "encrypt_bytes",
    "open_target",
]

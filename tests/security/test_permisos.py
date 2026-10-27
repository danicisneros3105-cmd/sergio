"""Secret files left open to others are made private again."""

import os

import pytest

from openjarvis.security import permisos


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_open_secret_files_become_private(tmp_path):
    (tmp_path / "sergio.env").write_text("X=1")
    (tmp_path / "sergio.env").chmod(0o644)
    (tmp_path / "clave_maestra").write_text("k")
    (tmp_path / "clave_maestra").chmod(0o600)
    assert permisos.tighten(tmp_path) == ["sergio.env"]
    assert (tmp_path / "sergio.env").stat().st_mode & 0o077 == 0
    assert permisos.tighten(tmp_path) == []

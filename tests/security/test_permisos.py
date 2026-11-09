"""Secret files left open to others are made private again."""

from openjarvis.security import permisos
from openjarvis.security.file_utils import is_private


def test_open_secret_files_become_private(tmp_path):
    (tmp_path / "sergio.env").write_text("X=1")
    (tmp_path / "clave_maestra").write_text("k")
    assert permisos.tighten(tmp_path) == ["sergio.env", "clave_maestra"]
    assert is_private(tmp_path / "sergio.env")
    assert is_private(tmp_path / "clave_maestra")
    assert permisos.tighten(tmp_path) == []

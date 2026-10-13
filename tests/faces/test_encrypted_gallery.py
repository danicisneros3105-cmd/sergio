"""A missing encryption key must not silently replace the owner's identity."""

import pytest

from openjarvis.faces.book import FaceBook, FaceError, Match


def test_encrypted_gallery_and_missing_key_fail_closed(tmp_path):
    book = FaceBook(root=tmp_path / "faces")
    book._save({"Señor": {"embeddings": []}})
    raw = book._db.read_bytes()
    assert b"Se\xc3\xb1or" not in raw and raw.startswith(b"gAAAA")
    assert book._key_path.stat().st_mode & 0o077 == 0
    assert book._db.stat().st_mode & 0o077 == 0
    book._key_path.unlink()
    with pytest.raises(FaceError):
        book._load(strict=True)
    assert book._db.read_bytes() == raw and not book._key_path.exists()


def test_bad_quality_is_not_a_strong_match():
    assert not Match(
        name="Señor", score=0.99, box=(0, 0, 120, 120), margin=1, quality="borrosa"
    ).strong


def test_valid_legacy_gallery_is_encrypted_on_first_read(tmp_path):
    book = FaceBook(root=tmp_path / "faces")
    book._root.mkdir()
    book._db.write_text("{}", encoding="utf-8")
    assert book._load(strict=True) == {}
    assert book._db.read_bytes().startswith(b"gAAAA")

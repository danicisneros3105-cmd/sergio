"""The keyring: versions, rotation and the passphrase that wraps it."""

from __future__ import annotations

import base64
import json
import secrets

import pytest

from openjarvis.pagos import cifrado


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("SERGIO_CLAVE_MAESTRA", raising=False)
    monkeypatch.delenv("SERGIO_FRASE_MAESTRA", raising=False)
    cifrado._CACHE.clear()
    yield
    cifrado._CACHE.clear()


def test_values_carry_the_key_version(tmp_path):
    box = cifrado.seal("secreto", aad="a", home=tmp_path)
    kid = cifrado.status(tmp_path)["activa"]
    assert box.startswith(f"v2:{kid}:")
    assert cifrado.unseal(box, aad="a", home=tmp_path) == "secreto"
    with pytest.raises(cifrado.SealError):
        cifrado.unseal(box, aad="otra-fila", home=tmp_path)


def test_a_keyring_of_before_still_opens_its_values(tmp_path):
    """The single base64 key and v1 values from installs before the keyring."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = secrets.token_bytes(32)
    (tmp_path / "clave_maestra").write_bytes(base64.b64encode(key))
    nonce = secrets.token_bytes(12)
    old = (
        "v1:"
        + base64.urlsafe_b64encode(
            nonce
            + AESGCM(cifrado._derive("cifrar", key)).encrypt(nonce, b"viejo", b"x")
        ).decode()
    )
    assert cifrado.unseal(old, aad="x", home=tmp_path) == "viejo"
    sig = cifrado.sign("linea", home=tmp_path)
    cifrado.rotate(tmp_path)
    assert cifrado.unseal(old, aad="x", home=tmp_path) == "viejo"
    assert cifrado.sign("linea", home=tmp_path) == sig  # the ledger chain holds


def test_rotation_new_key_for_new_values_old_ones_still_open(tmp_path):
    before = cifrado.seal("antes", home=tmp_path)
    first = cifrado.status(tmp_path)["activa"]
    new = cifrado.rotate(tmp_path)
    assert new != first and len(cifrado.status(tmp_path)["claves"]) == 2
    after = cifrado.seal("después", home=tmp_path)
    assert after.startswith(f"v2:{new}:") and cifrado.needs_reseal(before, tmp_path)
    assert not cifrado.needs_reseal(after, tmp_path)
    assert cifrado.unseal(before, home=tmp_path) == "antes"
    assert cifrado.unseal(after, home=tmp_path) == "después"


def test_a_passphrase_leaves_no_usable_key_on_disk(tmp_path, monkeypatch):
    box = cifrado.seal("privado", home=tmp_path)
    with pytest.raises(cifrado.SealError):
        cifrado.protect("corta", home=tmp_path)
    cifrado.protect("una frase bien larga", home=tmp_path)
    raw = json.loads((tmp_path / "clave_maestra").read_text())
    assert "envuelta" in raw and "claves" not in raw
    from openjarvis.security.file_utils import is_private

    assert is_private(tmp_path / "clave_maestra")
    cifrado._CACHE.clear()
    with pytest.raises(cifrado.SealError, match="SERGIO_FRASE_MAESTRA"):
        cifrado.unseal(box, home=tmp_path)
    monkeypatch.setenv("SERGIO_FRASE_MAESTRA", "otra frase equivocada")
    with pytest.raises(cifrado.SealError, match="frase"):
        cifrado.unseal(box, home=tmp_path)
    monkeypatch.setenv("SERGIO_FRASE_MAESTRA", "una frase bien larga")
    cifrado._CACHE.clear()
    assert cifrado.unseal(box, home=tmp_path) == "privado"
    assert cifrado.status(tmp_path)["protegida_con_frase"]
    # rotating keeps it wrapped
    cifrado.rotate(tmp_path)
    assert "envuelta" in json.loads((tmp_path / "clave_maestra").read_text())
    cifrado.unprotect("una frase bien larga", home=tmp_path)
    monkeypatch.delenv("SERGIO_FRASE_MAESTRA")
    cifrado._CACHE.clear()
    assert cifrado.unseal(box, home=tmp_path) == "privado"


def test_a_tampered_keyring_is_refused(tmp_path):
    cifrado.seal("x", home=tmp_path)
    data = json.loads((tmp_path / "clave_maestra").read_text())
    data["claves"][0]["kid"] = "00000000"
    (tmp_path / "clave_maestra").write_text(json.dumps(data))
    cifrado._CACHE.clear()
    with pytest.raises(cifrado.SealError, match="dañado"):
        cifrado.seal("x", home=tmp_path)


def test_with_a_key_from_the_environment_rotation_is_the_secret_managers(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "SERGIO_CLAVE_MAESTRA", base64.b64encode(secrets.token_bytes(32)).decode()
    )
    assert cifrado.status(tmp_path)["origen"] == "entorno"
    with pytest.raises(cifrado.SealError, match="gestor"):
        cifrado.rotate(tmp_path)

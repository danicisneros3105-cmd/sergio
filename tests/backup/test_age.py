"""The age v1 passphrase format: round trips, tampering, and the real `age` tool."""

from __future__ import annotations

import os
import shutil

import pytest

from openjarvis.backup.age import CHUNK, AgeError, decrypt_bytes, encrypt_bytes

pytest.importorskip("cryptography")


@pytest.mark.parametrize("size", [0, 1, CHUNK - 1, CHUNK, CHUNK + 1, 3 * CHUNK])
def test_round_trip_across_chunk_edges(size):
    data = os.urandom(size)
    sealed = encrypt_bytes(data, "una frase larga", work=10)
    assert sealed.startswith(b"age-encryption.org/v1\n-> scrypt ")
    assert decrypt_bytes(sealed, "una frase larga") == data


def test_wrong_passphrase_and_tampering():
    sealed = bytearray(encrypt_bytes(b"secreto" * 1000, "correcta", work=10))
    with pytest.raises(AgeError, match="incorrecta"):
        decrypt_bytes(bytes(sealed), "otra")
    sealed[-5] ^= 1
    with pytest.raises(AgeError, match="dañado"):
        decrypt_bytes(bytes(sealed), "correcta")
    with pytest.raises(AgeError):
        decrypt_bytes(b"not age at all", "x")
    with pytest.raises(AgeError):
        encrypt_bytes(b"x", "")


def test_truncation_is_detected():
    sealed = encrypt_bytes(os.urandom(CHUNK * 2 + 10), "frase", work=10)
    with pytest.raises(AgeError):
        decrypt_bytes(sealed[: -(CHUNK // 2)], "frase")


def _run_age(args, passphrase):
    """Drive the real `age` CLI through a pseudo-terminal (it reads the
    passphrase from the terminal only)."""
    import pty
    import select
    import time

    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - child
        os.execvp("age", ["age", *args])
    out, sent, deadline = b"", 0, time.time() + 60
    while time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.5)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 1024)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
        if out.lower().count(b"passphrase") > sent:
            os.write(fd, passphrase.encode() + b"\n")
            sent += 1
    _, status = os.waitpid(pid, 0)
    return status


@pytest.mark.skipif(
    not shutil.which("age") or os.name != "posix", reason="needs the age CLI"
)
def test_interoperates_with_the_age_cli(tmp_path):
    data = os.urandom(150_000)
    (tmp_path / "ours.age").write_bytes(encrypt_bytes(data, "frase de prueba", work=10))
    assert (
        _run_age(
            ["-d", "-o", str(tmp_path / "ours.out"), str(tmp_path / "ours.age")],
            "frase de prueba",
        )
        == 0
    )
    assert (tmp_path / "ours.out").read_bytes() == data
    (tmp_path / "plain").write_bytes(data)
    assert (
        _run_age(
            ["-p", "-o", str(tmp_path / "theirs.age"), str(tmp_path / "plain")],
            "otra frase",
        )
        == 0
    )
    assert decrypt_bytes((tmp_path / "theirs.age").read_bytes(), "otra frase") == data

import pytest


@pytest.fixture(autouse=True)
def _fast_scrypt(monkeypatch):
    # age's real work factor (2^18) takes ~1 s and 256 MiB per call.
    monkeypatch.setenv("SERGIO_AGE_WORK", "10")

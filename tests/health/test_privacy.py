"""Health data: contact details never reach the AI; «solo en este equipo»."""

from __future__ import annotations

import stat

from openjarvis.health import mind, privacy


def test_scrub_blanks_contact_details_and_ids():
    text = "Escríbame a ana.p@correo.ec o al +593 99 123 4567, cédula 0102030405, ver https://x.y/z. Duermo 7 h."
    out = privacy.scrub(text)
    assert "correo.ec" not in out and "4567" not in out and "0102030405" not in out
    assert "https" not in out and "Duermo 7 h." in out


def test_local_only_keeps_the_reading_on_the_computer(tmp_path, monkeypatch):
    path = tmp_path / "privacidad.json"
    monkeypatch.setattr(privacy, "_path", lambda: path)
    monkeypatch.delenv("SERGIO_SALUD_LOCAL", raising=False)
    assert not privacy.local_only()
    privacy.set_local_only(True)
    assert privacy.local_only()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    called = []
    monkeypatch.setattr(mind, "fallback_reading", lambda s, a: "en código")

    def generate(**kw):
        called.append(kw)
        return {"content": "x" * 200}

    assert mind.write_reading({"scales": [], "pictures": []}, {}, generate) == (
        "en código",
        "codigo",
    )
    assert not called


def test_env_switch(monkeypatch):
    monkeypatch.setenv("SERGIO_SALUD_LOCAL", "1")
    assert privacy.local_only()

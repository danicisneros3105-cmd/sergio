"""Cowork can only certify supported outcomes from actual tool receipts."""

import json

from openjarvis.cowork.runner import verified_read


def test_expected_source_and_text_must_match_the_tool_receipt():
    check = "https://aula.test/tareas | Entrega de matemáticas"
    receipt = {
        "estado": "leido",
        "url": "https://aula.test/tareas",
        "texto": "Entrega de Matemáticas: jueves.",
        "evidencia": {"verificado": True},
    }

    def tool(data):
        return [
            {
                "tool_name": "en_segundo_plano",
                "success": True,
                "content": json.dumps(data),
            }
        ]

    assert verified_read(tool(receipt), check)
    assert not verified_read([], check)
    assert not verified_read(
        tool({**receipt, "url": "https://otro.test/tareas"}), check
    )
    assert not verified_read(tool({**receipt, "texto": "Entrega de historia"}), check)
    assert not verified_read(tool({**receipt, "estado": "espera_su_si"}), check)
    assert not verified_read(tool(receipt), "El modelo dijo que terminó")


def test_persistent_browser_is_explicitly_opt_in(monkeypatch):
    from openjarvis.cowork.runner import personal_browser_enabled, usable_tools

    monkeypatch.delenv("SERGIO_COWORK_PERSONAL_BROWSER", raising=False)
    assert not personal_browser_enabled()
    assert "en_segundo_plano" not in usable_tools(["en_segundo_plano"])
    monkeypatch.setenv("SERGIO_COWORK_PERSONAL_BROWSER", "1")
    assert "en_segundo_plano" in usable_tools(["en_segundo_plano"])

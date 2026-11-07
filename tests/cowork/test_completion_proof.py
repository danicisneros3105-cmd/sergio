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
    from openjarvis.core.registry import ToolRegistry
    from openjarvis.cowork.runner import personal_browser_enabled, usable_tools
    from openjarvis.tools.asistente_tools import SegundoPlanoTool

    # The suite deliberately clears registries before each test.
    ToolRegistry.register("en_segundo_plano")(SegundoPlanoTool)
    monkeypatch.delenv("SERGIO_COWORK_PERSONAL_BROWSER", raising=False)
    assert not personal_browser_enabled()
    assert "en_segundo_plano" not in usable_tools(["en_segundo_plano"])
    monkeypatch.setenv("SERGIO_COWORK_PERSONAL_BROWSER", "1")
    assert "en_segundo_plano" in usable_tools(["en_segundo_plano"])


def test_sdk_completion_uses_tool_evidence_instead_of_model_claim(monkeypatch):
    from unittest.mock import MagicMock

    from openjarvis import sdk
    from openjarvis.cowork import runner

    url = "https://aula.test/tareas"
    sdk_instance = MagicMock()
    sdk_instance.ask_full.return_value = {
        "content": "TERMINADO: la entrega vence el viernes",
        "tool_results": [
            {
                "tool_name": "en_segundo_plano",
                "success": True,
                "content": json.dumps(
                    {
                        "estado": "leido",
                        "url": url,
                        "texto": "Entrega de matemáticas: jueves.\nAula 7.",
                        "evidencia": {"verificado": True},
                    }
                ),
            }
        ],
    }
    monkeypatch.setattr(sdk, "Jarvis", lambda **_kw: sdk_instance)
    answer, used = runner.sdk_step_runner(
        "comprueba la entrega", [], 5, expected_check=f"{url} | matemáticas"
    )
    assert used == 1
    assert url in answer and "jueves" in answer
    assert "viernes" not in answer


def test_cowork_confirms_a_written_file_only_after_readback(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from openjarvis import sdk
    from openjarvis.cowork import runner
    from openjarvis.tools.file_read import FileReadTool
    from openjarvis.tools.file_write import FileWriteTool

    target = tmp_path / "acta QA.txt"
    expected = "Entregar el jueves"
    write = FileWriteTool().execute(path=str(target), content=f"Acuerdos: {expected}")
    read = FileReadTool().execute(path=str(target))
    assert write.success and read.success

    def receipt(result):
        return {
            "tool_name": result.tool_name,
            "success": result.success,
            "content": result.content,
            "file_path": result.metadata["path"],
        }

    sdk_instance = MagicMock()
    monkeypatch.setattr(sdk, "Jarvis", lambda **_kw: sdk_instance)
    for receipts, finished in (
        ([receipt(write), receipt(read)], True),
        ([receipt(read)], False),
        (
            [
                receipt(write),
                {**receipt(read), "file_path": str(tmp_path / "otro.txt")},
            ],
            False,
        ),
        ([receipt(write), {**receipt(read), "content": "Entregar el viernes"}], False),
        ([receipt(write), receipt(read), receipt(write)], False),
    ):
        sdk_instance.ask_full.return_value = {
            "content": "TERMINADO: no importa lo que diga el archivo",
            "tool_results": receipts,
        }
        answer, used = runner.sdk_step_runner(
            "crear un acta",
            ["file_write", "file_read"],
            5,
            expected_check=f"ARCHIVO | {target.resolve()} | {expected}",
        )
        assert used == len(receipts)
        assert answer.startswith("TERMINADO:" if finished else "NO POSIBLE:")
        if finished:
            assert str(target.resolve()) in answer
    assert sdk_instance.ask_full.call_args.kwargs["file_receipts"] is True

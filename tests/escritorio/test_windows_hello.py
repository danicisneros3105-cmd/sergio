"""Consent is an OS result for the displayed action, never a face label."""

import threading

import httpx
import pytest
from sergio_escritorio.platform_auth import Consent, verify


def test_verifier_is_fail_closed_on_non_windows_and_exceptions(monkeypatch):
    monkeypatch.setattr("sergio_escritorio.platform_auth.sys.platform", "linux")
    assert not verify(123, "Eliminar archivo").verified

    def broken(*args):
        raise OSError("Windows unavailable")

    assert not verify(123, "Eliminar archivo", backend=broken).verified
    assert not verify(123, "Eliminar archivo", backend=lambda *a: True).verified
    assert not verify(
        123, "Eliminar archivo", backend=lambda *a: Consent(True, "foto", "webcam")
    ).verified


def test_cancellation_wins_even_after_a_successful_result():
    cancel = threading.Event()

    def success(*args):
        cancel.set()
        return Consent(True, "Verified")

    assert not verify(123, "Publicar", cancel=cancel, backend=success).verified


@pytest.mark.parametrize(
    "decision",
    [
        None,
        {"approved": True},
        {"approved": True, "what": "Borrar", "method": "webcam"},
        {"approved": "true", "what": "Borrar", "method": "windows_hello"},
        {"approved": True, "what": "Otra acción", "method": "windows_hello"},
    ],
)
def test_photo_boolean_or_unbound_result_never_authorizes(monkeypatch, decision):
    from openjarvis.tools.desktop_tools import FaceApprovalTool

    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "test-companion-only")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"ok": True, "result": decision})
        )
    )
    with client:
        assert not FaceApprovalTool(http=client).execute(what="Borrar").success


def test_exact_system_confirmation_is_required(monkeypatch):
    from openjarvis.tools.desktop_tools import FaceApprovalTool

    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "test-companion-only")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "approved": True,
                        "what": "Borrar",
                        "method": "windows_hello",
                    },
                },
            )
        )
    ) as client:
        assert FaceApprovalTool(http=client).execute(what="Borrar").success


def test_dialog_never_animates_success_for_a_failed_verification():
    from PySide6.QtWidgets import QApplication
    from sergio_escritorio.facegate import ConsentDialog

    app = QApplication.instance() or QApplication([])
    dialog = ConsentDialog("Eliminar un documento", reduce_motion=True)
    dialog._finish(Consent(False, "Cancelled"))
    assert not dialog.verified and not dialog.timer.isActive()
    dialog.reject()
    dialog._finish(Consent(True, "Verified"))
    assert not dialog.verified and dialog.cancelled.is_set()
    app.processEvents()


def test_long_action_is_reviewable_in_plain_text_without_truncation():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit
    from sergio_escritorio.facegate import ConsentDialog

    app = QApplication.instance() or QApplication([])
    request = "<b>Publicar</b>\n" + "Detalle del archivo. " * 60
    dialog = ConsentDialog(request, reduce_motion=True)
    assert dialog.findChild(QPlainTextEdit).toPlainText() == request
    assert any(
        label.textFormat() == Qt.TextFormat.PlainText
        for label in dialog.findChildren(QLabel)
    )
    dialog.reject()
    app.processEvents()


def test_windows_answers_are_explained_in_plain_words():
    from sergio_escritorio.platform_auth import result_text

    assert result_text(0) == "verificado"
    assert "no está configurado" in result_text(2)
    assert "ocupado" in result_text(4)
    assert "PIN" in result_text(5)
    assert "código 42" in result_text(42)


def test_the_dialog_asks_windows_at_once_when_shown():
    import threading
    import time

    from PySide6.QtWidgets import QApplication
    from sergio_escritorio.facegate import ConsentDialog

    app = QApplication.instance() or QApplication([])
    asked = threading.Event()

    def verifier(hwnd, message, cancel):
        asked.set()
        return Consent(False, "Cancelado.")

    dialog = ConsentDialog("Borrar un archivo", verifier=verifier, reduce_motion=True)
    dialog.show()
    end = time.monotonic() + 2
    while not asked.is_set() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    assert asked.is_set()  # no click needed before the Windows prompt
    dialog.reject()
    app.processEvents()

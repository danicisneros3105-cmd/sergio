"""Sensitive operations require explicit, action-specific local consent."""

import json

import pytest
from sergio_escritorio.control import Controller


@pytest.mark.parametrize(
    "action",
    [
        {"action": "python", "code": "print(42)"},
        {"action": "terminal", "command": "Get-Process"},
        {"action": "blender", "script": "print('scene')"},
        {"action": "organize", "target": "Downloads", "apply": True},
    ],
)
def test_missing_or_rejected_consent_never_calls_backend(desktop, action):
    for approve in (None, lambda _: False, lambda _: "yes"):
        controller = Controller(desktop, approve=approve)
        with pytest.raises(PermissionError):
            controller.act(action)
        assert desktop.calls == []


def test_consent_displays_exact_payload_and_pausing_still_blocks(desktop):
    seen = []
    controller = Controller(desktop)

    def approve(text):
        seen.append(json.loads(text))
        controller.enabled = False
        return True

    controller.approve = approve
    action = {"action": "python", "code": "print('private')", "seconds": 15}
    with pytest.raises(PermissionError):
        controller.act(action)
    assert seen == [action]
    assert not desktop.calls


def test_dialog_defaults_to_no_and_explicit_yes_is_required():
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from sergio_escritorio.consent import confirm_dialog

    app = QApplication.instance() or QApplication([])

    def accept():
        box = next(
            w
            for w in app.topLevelWidgets()
            if isinstance(w, QMessageBox) and w.isVisible()
        )
        assert box.defaultButton() == box.button(QMessageBox.StandardButton.No)
        box.done(QMessageBox.StandardButton.Yes)

    QTimer.singleShot(10, accept)
    assert confirm_dialog("Ejecutar print(42)", seconds=1)
    assert not confirm_dialog("Ejecutar print(42)", seconds=0.01)

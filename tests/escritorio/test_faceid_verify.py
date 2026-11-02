"""Actions are approved with Sergio's own Visage (owner, 26 Oct 2026)."""

import threading

import numpy as np
from sergio_escritorio import faceid_verify


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


class _Http:
    def __init__(self, *unlocks, challenge=None):
        self.unlocks = list(unlocks)
        self.challenge = challenge or {"nonce": "n1", "say": "Gire a la izquierda"}
        self.sent = []

    def post(self, url, **kw):
        if url.endswith("/challenge"):
            return _Resp(self.challenge)
        self.sent.append(kw)
        return _Resp(self.unlocks.pop(0))


class _Feed:
    def jpeg(self, wait=4.0):
        return b"first"

    def frame(self):
        return np.zeros((8, 8, 3), dtype=np.uint8)


def _fast(monkeypatch):
    monkeypatch.setattr(faceid_verify, "READ_FIRST", 0)
    monkeypatch.setattr(faceid_verify, "EVERY", 0)


def test_a_recognised_face_approves(monkeypatch):
    _fast(monkeypatch)
    http = _Http({"ok": True, "ms": 120})
    said = []
    out = faceid_verify.verify(
        http, "b", _Feed(), cancel=threading.Event(), say=said.append
    )
    assert out.verified and out.method == "faceid"
    assert http.sent[0]["data"]["nonce"] == "n1"
    assert len(http.sent[0]["files"]) == faceid_verify.FRAMES
    assert any("izquierda" in s for s in said)


def test_bad_light_tries_again_without_spending_an_attempt(monkeypatch):
    _fast(monkeypatch)
    http = _Http({"ok": False, "retry": True, "message": "Más luz"}, {"ok": True})
    assert faceid_verify.verify(http, "b", _Feed(), cancel=threading.Event()).verified


def test_a_wrong_face_is_refused(monkeypatch):
    _fast(monkeypatch)
    http = _Http({"ok": False, "message": "No le reconozco.", "attempts_left": 3})
    out = faceid_verify.verify(http, "b", _Feed(), cancel=threading.Event())
    assert not out.verified and "3 intentos" in out.reason


def test_the_backup_code_is_asked_when_face_id_needs_it(monkeypatch):
    _fast(monkeypatch)
    http = _Http(challenge={"passcode_required": True, "reason": "Use su código."})
    out = faceid_verify.verify(http, "b", _Feed(), cancel=threading.Event())
    assert not out.verified and out.method == "codigo"


def test_no_server_or_camera_never_approves(monkeypatch):
    _fast(monkeypatch)

    class Down:
        def post(self, *a, **k):
            raise OSError("off")

    assert not faceid_verify.verify(
        Down(), "b", _Feed(), cancel=threading.Event()
    ).verified

    class NoCam(_Feed):
        def jpeg(self, wait=4.0):
            raise RuntimeError("No encuentro la cámara")

    out = faceid_verify.verify(
        _Http({"ok": True}), "b", NoCam(), cancel=threading.Event()
    )
    assert not out.verified and "cámara" in out.reason


def test_the_sheet_falls_back_to_the_code():
    from PySide6.QtWidgets import QApplication
    from sergio_escritorio.facegate import ConsentDialog
    from sergio_escritorio.platform_auth import Consent

    app = QApplication.instance() or QApplication([])
    dialog = ConsentDialog(
        "Borrar un archivo",
        check_code=lambda code: code == "123456",
        reduce_motion=True,
    )
    dialog._finish(Consent(False, "Use su código.", "codigo"))
    assert not dialog.code.isHidden()
    dialog.code.setText("000000")
    dialog._use_code()
    assert not dialog.verified
    dialog.code.setText("123456")
    dialog._use_code()
    assert dialog.verified
    dialog.reject()
    app.processEvents()


def test_one_sergio_window_is_recognised():
    from sergio_escritorio.launch import is_sergio_window

    assert is_sergio_window("Sergio", "msedge.exe")
    assert not is_sergio_window("Sergio", "python.exe")  # the notch, not the app
    assert not is_sergio_window("Sergio Ramos - YouTube", "chrome.exe")

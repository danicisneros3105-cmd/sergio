"""Approving an action with Sergio's own Face ID (no Windows Hello).

The owner (26 Oct 2026): «todo se verifica vía nuestro propio ultra Visage».
The same check as the web's Visage page: the server gives a one-time
challenge (a gentle head turn), the webcam takes a short burst of frames, and
``/v1/faces/faceid/unlock`` decides (live face, looking at the screen, the
owner and nobody else). Light or a missed movement does not spend an attempt;
after five wrong faces, or when Visage has not been used for a while, only
Sergio's backup code works (``passcode_required``).

It fails closed: no camera, no server or no Visage set up means «no».
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from sergio_escritorio.platform_auth import Consent

FRAMES = 14
EVERY = 0.15  # seconds between frames: ~2 s of movement
READ_FIRST = 0.9  # time to read the instruction before counting


def _frames(feed: Any, cancel: threading.Event) -> list[bytes]:
    import cv2

    first = feed.jpeg(wait=4.0)  # starts the camera and lets it settle
    out = [first]
    while len(out) < FRAMES and not cancel.is_set():
        time.sleep(EVERY)
        frame = feed.frame()
        if frame is None:
            continue
        ok, data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            out.append(data.tobytes())
    return out


def verify(
    http: Any,
    base: str,
    feed: Any,
    *,
    cancel: threading.Event,
    say: Callable[[str], None] = lambda _text: None,
    tries: int = 2,
) -> Consent:
    """One approval with Visage; ``Consent.method`` is ``"faceid"``, or
    ``"codigo"`` with ``verified=False`` when only the backup code is left."""
    for _ in range(max(1, tries)):
        if cancel.is_set():
            return Consent(False, "Cancelado.", "faceid")
        try:
            challenge = http.post(f"{base}/v1/faces/faceid/challenge", timeout=10)
            if challenge.status_code >= 400:
                return Consent(False, "Primero configure Visage en Sergio.", "faceid")
            challenge = challenge.json()
        except Exception:  # noqa: BLE001 — fail closed
            return Consent(False, "Sergio no responde: no puedo verificar.", "faceid")
        if challenge.get("passcode_required"):
            return Consent(False, str(challenge.get("reason") or "Use su código."), "codigo")
        say(f"Mire a la pantalla. {challenge.get('say', '')}…")
        time.sleep(READ_FIRST)
        try:
            frames = _frames(feed, cancel)
        except Exception as exc:  # noqa: BLE001 — no camera: say it, never approve
            return Consent(False, str(exc) or "La cámara no responde.", "faceid")
        if cancel.is_set():
            return Consent(False, "Cancelado.", "faceid")
        say("Verificando…")
        try:
            out = http.post(
                f"{base}/v1/faces/faceid/unlock",
                data={"nonce": challenge.get("nonce", "")},
                files=[("images", (f"f{i}.jpg", b, "image/jpeg")) for i, b in enumerate(frames)],
                timeout=20,
            ).json()
        except Exception:  # noqa: BLE001
            return Consent(False, "No pude verificar su cara.", "faceid")
        if out.get("ok") is True:
            return Consent(True, f"Reconocido en {out.get('ms', 0)} ms.", "faceid")
        if out.get("passcode_required"):
            return Consent(False, str(out.get("reason") or "Use su código."), "codigo")
        if not out.get("retry"):
            left = out.get("attempts_left")
            more = f" Le quedan {left} intentos." if isinstance(left, int) else ""
            return Consent(False, f"{out.get('message') or 'No le reconozco.'}{more}", "faceid")
        say(f"{out.get('message') or 'Otra vez'}: este intento no cuenta.")
    return Consent(False, "No pude verlo bien. Inténtelo con más luz.", "faceid")


__all__ = ["verify"]

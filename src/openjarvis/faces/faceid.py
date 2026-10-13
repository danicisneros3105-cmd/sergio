"""Webcam recognition with attention and movement checks, not Face ID security.

These checks reduce simple replay errors, but RGB images do not provide trusted
depth capture, hardware-backed keys or Apple's anti-spoofing guarantees. This
module never grants sensitive desktop action approval: the companion delegates
that to explicit consent and Windows Hello. The backup code belongs to Sergio's
recognition state, not to Windows authentication.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MAX_FAILS = 5
INACTIVE_S = 48 * 3600
PASSCODE_STALE_S = 156 * 3600
RECENT_FACE_S = 4 * 3600
CHALLENGE_TTL = 20.0
ACTIONS = ("izquierda", "derecha", "arriba", "parpadee")
ACTION_ES = {
    "izquierda": "Gire la cabeza despacio hacia su izquierda",
    "derecha": "Gire la cabeza despacio hacia su derecha",
    "arriba": "Levante un poco la barbilla",
    "parpadee": "Parpadee una vez, mirando a la pantalla",
}
FRONT_DEG = 18.0  # "looking at the screen"
TURN_DEG = 12.0  # how far a turn must go to count
OWNER_STRONG = 0.55
OWNER_FRAME = 0.50
OWNER_MARGIN = 0.12
MIN_FRAMES = 4
MAX_FRAMES = 16
# Wrong passcodes: after the 5th, wait (seconds) — longer each time (Apple).
PASSCODE_WAITS = (60, 300, 900, 3600)


def _now() -> float:
    return time.time()


def hash_passcode(code: str, salt: bytes | None = None) -> dict[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(code.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return {"salt": salt.hex(), "hash": digest.hex()}


def passcode_matches(code: str, stored: dict[str, str]) -> bool:
    try:
        salt = bytes.fromhex(stored["salt"])
        want = bytes.fromhex(stored["hash"])
    except (KeyError, ValueError):
        return False
    got = hashlib.scrypt(code.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(got, want)


def valid_passcode(code: str) -> bool:
    return code.isdigit() and 6 <= len(code) <= 12


@dataclass
class Challenge:
    nonce: str
    action: str
    expires: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "nonce": self.nonce,
            "action": self.action,
            "say": ACTION_ES[self.action],
            "expires_in": max(0, round(self.expires - _now())),
        }


@dataclass
class Gate:
    """Passcode, attempts and the rules for when Face ID may be used."""

    root: Path
    clock: Callable[[], float] = _now
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _challenges: dict[str, Challenge] = field(default_factory=dict)
    _passcode_since_boot: bool = False

    @property
    def _path(self) -> Path:
        return Path(self.root) / "faceid.json"

    def _state(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, state: dict[str, Any]) -> None:
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        os.chmod(tmp, 0o600)
        tmp.replace(path)

    # -- the passcode ------------------------------------------------------

    def has_passcode(self) -> bool:
        return bool(self._state().get("passcode"))

    def set_passcode(self, code: str, current: str = "") -> None:
        if not valid_passcode(code):
            raise ValueError("El código debe tener de 6 a 12 cifras.")
        with self._lock:
            state = self._state()
            if state.get("passcode") and not passcode_matches(
                current, state["passcode"]
            ):
                raise PermissionError("El código actual no es correcto.")
            state["passcode"] = hash_passcode(code)
            state["last_passcode"] = state["last_unlock"] = self.clock()
            state["fails"] = 0
            state["locked"] = False
            self._save(state)
            self._passcode_since_boot = True

    def check_passcode(self, code: str) -> dict[str, Any]:
        """Unlock with the passcode. Wrong codes wait longer each time."""
        with self._lock:
            state = self._state()
            now = self.clock()
            wait = float(state.get("passcode_wait_until") or 0) - now
            if wait > 0:
                return {"ok": False, "wait": round(wait)}
            if not state.get("passcode") or not passcode_matches(
                code, state["passcode"]
            ):
                wrong = int(state.get("passcode_wrong") or 0) + 1
                state["passcode_wrong"] = wrong
                if wrong >= MAX_FAILS:
                    step = min(wrong - MAX_FAILS, len(PASSCODE_WAITS) - 1)
                    state["passcode_wait_until"] = now + PASSCODE_WAITS[step]
                self._save(state)
                return {"ok": False, "wait": 0, "wrong": wrong}
            state.update(
                passcode_wrong=0,
                passcode_wait_until=0,
                fails=0,
                locked=False,
                last_passcode=now,
                last_unlock=now,
            )
            self._save(state)
            self._passcode_since_boot = True
            return {"ok": True}

    def lock_now(self) -> None:
        """«Bloquear ahora»: the next unlock needs the passcode."""
        with self._lock:
            state = self._state()
            state["locked"] = True
            self._save(state)

    # -- when Face ID may be used ------------------------------------------

    def passcode_reason(self) -> str:
        """Why the passcode is needed now ('' = Face ID may be used)."""
        state = self._state()
        now = self.clock()
        if not state.get("passcode"):
            return "sin_codigo"
        if state.get("locked"):
            return "bloqueado"
        if not self._passcode_since_boot:
            return "reinicio"
        if int(state.get("fails") or 0) >= MAX_FAILS:
            return "intentos"
        if now - float(state.get("last_unlock") or 0) > INACTIVE_S:
            return "inactivo"
        if (
            now - float(state.get("last_passcode") or 0) > PASSCODE_STALE_S
            and now - float(state.get("last_face") or 0) > RECENT_FACE_S
        ):
            return "codigo_antiguo"
        return ""

    def status(self) -> dict[str, Any]:
        state = self._state()
        reason = self.passcode_reason()
        return {
            "passcode_set": bool(state.get("passcode")),
            "face_allowed": not reason,
            "passcode_reason": reason,
            "attempts_left": max(0, MAX_FAILS - int(state.get("fails") or 0)),
        }

    def challenge(self) -> Challenge:
        now = self.clock()
        with self._lock:
            for key in [k for k, c in self._challenges.items() if c.expires < now]:
                del self._challenges[key]
            c = Challenge(
                secrets.token_urlsafe(18),
                secrets.choice(ACTIONS),
                now + CHALLENGE_TTL,
            )
            self._challenges[c.nonce] = c
            return c

    def take(self, nonce: str) -> Challenge | None:
        """A challenge is valid once, and only while fresh."""
        with self._lock:
            c = self._challenges.pop(nonce or "", None)
        return c if c and c.expires >= self.clock() else None

    def record(self, ok: bool) -> int:
        """Count a Face ID attempt; returns the attempts left."""
        with self._lock:
            state = self._state()
            now = self.clock()
            if ok:
                state.update(fails=0, last_face=now, last_unlock=now)
            else:
                state["fails"] = int(state.get("fails") or 0) + 1
            self._save(state)
            return max(0, MAX_FAILS - int(state.get("fails") or 0))


# -- what the camera shows ---------------------------------------------------


@dataclass
class Frame:
    feature: Any  # unit SFace embedding of the largest face
    yaw: float
    pitch: float
    eyes_open: bool
    crop: Any  # small grey face crop, to spot an injected still image
    faces: int
    eyes_seen: int = 2  # eyes the detector found open (0, 1 or 2)
    eye_light: float = (
        1.0  # eye patches' brightness / the face's: lids are lighter than pupils
    )


def eye_state(image: Any, row: Any) -> tuple[int, float]:
    """(open eyes found, eye brightness relative to the face).

    OpenCV's eye detector fires on open eyes; a closed lid also makes the
    eye patch lighter (skin covers the dark iris and pupil). Both signals
    together tell a real blink from a detector flicker on a still photo."""
    import cv2

    try:
        rx, ry, lx, ly = (float(v) for v in row[4:8])
        bx, by, bw, bh = (int(v) for v in row[:4])
    except (TypeError, ValueError, IndexError):
        return 0, 1.0
    iod = max(1.0, ((lx - rx) ** 2 + (ly - ry) ** 2) ** 0.5)
    half = int(iod * 0.38)
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    face = grey[max(0, by) : by + bh, max(0, bx) : bx + bw]
    face_mean = float(face.mean()) if face.size else 1.0
    cascade = _cascade()
    found = 0
    light = []
    for x, y in ((rx, ry), (lx, ly)):
        x0, y0 = max(0, int(x - half)), max(0, int(y - half))
        patch = grey[y0 : int(y + half), x0 : int(x + half)]
        if patch.size == 0:
            return 0, 1.0
        inner = patch[patch.shape[0] // 4 : -patch.shape[0] // 4 or None, :]
        light.append(float(inner.mean()) if inner.size else float(patch.mean()))
        patch = cv2.resize(patch, (64, 64))
        eyes = cascade.detectMultiScale(patch, 1.08, 3, minSize=(14, 14))
        found += 1 if len(eyes) else 0
    return found, (sum(light) / len(light)) / max(1.0, face_mean)


def eyes_open(image: Any, row: Any) -> bool:
    """Both eyes found open."""
    return eye_state(image, row)[0] == 2


_CASCADE: Any = None


def _cascade() -> Any:
    global _CASCADE
    if _CASCADE is None:
        import cv2

        _CASCADE = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"
        )
    return _CASCADE


def read_frames(book: Any, frames: list[bytes]) -> list[Frame]:
    """The largest face of each frame, with its pose and open eyes."""
    import cv2
    import numpy as np

    from openjarvis.faces.book import FaceError, head_pose

    detector, recognizer = book._models()
    out: list[Frame] = []
    for data in frames[:MAX_FRAMES]:
        try:
            image = book._decode(data)
        except FaceError:
            continue
        with book._lock:
            h, w = image.shape[:2]
            detector.setInputSize((w, h))
            _, found = detector.detect(image)
            if found is None or not len(found):
                continue
            rows = sorted(found, key=lambda r: -float(r[2] * r[3]))
            row = rows[0]
            aligned = recognizer.alignCrop(image, row)
            feature = recognizer.feature(aligned).flatten()
        feature = feature / (np.linalg.norm(feature) + 1e-9)
        yaw, pitch = head_pose(row)
        crop = cv2.resize(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), (48, 48))
        seen, light = eye_state(image, row)
        out.append(
            Frame(
                feature,
                yaw,
                pitch,
                seen == 2,
                crop.astype(np.float32),
                len(rows),
                seen,
                light,
            )
        )
    return out


def alive(frames: list[Frame], action: str) -> tuple[bool, str]:
    """Did the face do what was asked, and is it moving like a person?"""
    import numpy as np

    if len(frames) < MIN_FRAMES:
        return False, "No vi su cara lo bastante: acérquese y mire a la pantalla."
    diffs = [
        float(np.mean(np.abs(a.crop - b.crop))) for a, b in zip(frames, frames[1:])
    ]
    if max(diffs) < 0.8:
        return False, "La imagen no se mueve: parece una foto."
    if action in ("izquierda", "derecha", "arriba"):
        if turned(
            [f.pitch if action == "arriba" else f.yaw for f in frames],
            -1 if action == "derecha" else 1,
        ):
            return True, ""
    elif action == "parpadee" and blinked(frames):
        return True, ""
    return False, f"No vi el movimiento pedido ({ACTION_ES[action].lower()})."


def turned(angles: list[float], sign: int) -> bool:
    """A real, sustained turn: the end settles ≥ TURN_DEG away from a steady
    start, and the head never teleports. Pose noise (a shaking hand holding a
    photo) jumps around; it does not settle somewhere else. Turning a flat
    photo does not move the nose against the eyes, so it gives no turn."""
    import statistics

    if len(angles) < MIN_FRAMES:
        return False
    k = max(2, len(angles) // 4)
    start, end = angles[:k], angles[-k:]
    if statistics.pstdev(start) > 5.0:
        return False  # it did not start still and facing the screen
    if max(abs(b - a) for a, b in zip(angles, angles[1:])) > 25.0:
        return False
    return sign * (statistics.median(end) - statistics.median(start)) >= TURN_DEG


def blinked(frames: list[Frame]) -> bool:
    """Open, then both lids closed (no eye found AND the eye patches clearly
    lighter) for a moment, then open again: a blink, not a flicker."""
    import statistics

    open_light = [f.eye_light for f in frames if f.eyes_seen == 2]
    if len(open_light) < 3:
        return False
    base = statistics.median(open_light)
    states = [
        "open"
        if f.eyes_seen == 2
        else "closed"
        if f.eyes_seen == 0 and f.eye_light >= base * 1.08
        else "?"
        for f in frames
    ]
    for i, state in enumerate(states):
        if state != "closed":
            continue
        run = 1
        while i + run < len(states) and states[i + run] == "closed":
            run += 1
        if run <= 4 and "open" in states[:i] and "open" in states[i + run :]:
            return True
    return False


def attentive(frames: list[Frame]) -> bool:
    return any(
        abs(f.yaw) <= FRONT_DEG and abs(f.pitch) <= FRONT_DEG and f.eyes_open
        for f in frames
    )


def match_owner(
    frames: list[Frame], gallery: dict[str, Any], owner: str
) -> tuple[bool, float, str]:
    """(matched, best score, reason) for the owner against everyone enrolled."""
    import numpy as np

    mine = gallery.get(owner)
    if mine is None or not len(mine):
        return False, 0.0, "Aún no hay un Face ID guardado."
    others = [v for k, v in gallery.items() if k != owner and len(v)]
    scores = [float(np.max(mine @ f.feature)) for f in frames]
    best = max(scores)
    strong = sum(1 for s in scores if s >= OWNER_FRAME)
    rival = max(
        (float(np.max(v @ f.feature)) for v in others for f in frames), default=0.0
    )
    same_person = all(
        float(np.dot(a.feature, b.feature)) >= 0.45 for a, b in zip(frames, frames[1:])
    )
    if not same_person:
        return False, best, "Vi más de una cara distinta durante la prueba."
    if best >= OWNER_STRONG and strong >= 2 and best - rival >= OWNER_MARGIN:
        return True, best, ""
    return False, best, "No le reconozco."


def unlock(
    book: Any, gate: Gate, nonce: str, frames: list[bytes], owner: str
) -> dict[str, Any]:
    """One Face ID attempt: passcode rules, challenge, attention, match."""
    reason = gate.passcode_reason()
    if reason:
        return {"ok": False, "passcode_required": True, "reason": reason}
    challenge = gate.take(nonce)
    if challenge is None:
        return {
            "ok": False,
            "retry": True,
            "message": "El reto caducó: inténtelo de nuevo.",
        }
    t0 = time.perf_counter()
    seen = read_frames(book, frames)
    ok_live, why = alive(seen, challenge.action)
    message = why
    ok = False
    score = 0.0
    if ok_live and not attentive(seen):
        message = "Mire a la pantalla con los ojos abiertos."
    elif ok_live:
        ok, score, message = match_owner(seen, book._gallery(), owner)
    left = gate.record(ok)
    if ok:
        front = max(
            (f for f in seen if abs(f.yaw) <= FRONT_DEG),
            key=lambda f: float(f.eyes_open),
            default=seen[0],
        )
        try:
            book._learn(owner, front.feature, (front.yaw, front.pitch))
        except Exception:  # noqa: BLE001 — learning is a bonus, never a failure
            pass
    return {
        "ok": ok,
        "name": owner if ok else "",
        "message": "" if ok else message,
        "attempts_left": left,
        "passcode_required": left == 0,
        "ms": round((time.perf_counter() - t0) * 1000),
        "score": round(score, 3),
    }


__all__ = [
    "ACTIONS",
    "ACTION_ES",
    "Challenge",
    "Frame",
    "Gate",
    "MAX_FAILS",
    "alive",
    "attentive",
    "hash_passcode",
    "match_owner",
    "passcode_matches",
    "unlock",
    "valid_passcode",
]

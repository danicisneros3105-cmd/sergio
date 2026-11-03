"""Sergio's Face ID follows Apple's published rules (faceid.py)."""

from __future__ import annotations

import numpy as np
import pytest

from openjarvis.faces import faceid
from openjarvis.faces.faceid import Frame, Gate


class Clock:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def gate(tmp_path):
    clock = Clock()
    g = Gate(tmp_path, clock=clock)
    g.clock_ref = clock  # type: ignore[attr-defined]
    return g


def test_face_id_needs_a_passcode_first(gate):
    assert gate.passcode_reason() == "sin_codigo"
    with pytest.raises(ValueError):
        gate.set_passcode("123")  # too short
    gate.set_passcode("246810")
    assert gate.passcode_reason() == ""
    assert (gate.root / "faceid.json").stat().st_mode & 0o077 == 0
    assert "246810" not in (gate.root / "faceid.json").read_text()


def test_restart_requires_the_passcode_once(gate, tmp_path):
    gate.set_passcode("246810")
    restarted = Gate(tmp_path, clock=gate.clock)
    assert restarted.passcode_reason() == "reinicio"
    assert restarted.check_passcode("246810")["ok"]
    assert restarted.passcode_reason() == ""


def test_five_failed_matches_then_passcode(gate):
    gate.set_passcode("246810")
    for left in (4, 3, 2, 1):
        assert gate.record(False) == left
    assert gate.record(False) == 0
    assert gate.passcode_reason() == "intentos"
    assert gate.check_passcode("246810")["ok"]
    assert gate.status()["attempts_left"] == 5


def test_48_hours_without_unlock_and_the_156_hour_rule(gate):
    clock = gate.clock_ref
    gate.set_passcode("246810")
    clock.t += 47 * 3600
    assert gate.passcode_reason() == ""
    clock.t += 2 * 3600
    assert gate.passcode_reason() == "inactivo"
    gate.check_passcode("246810")
    # Visage unlocks every day, but the passcode is not used for 156 h ...
    for _ in range(7):
        clock.t += 23 * 3600
        gate.record(True)
    assert gate.passcode_reason() == ""  # Visage used in the last 4 hours
    clock.t += 5 * 3600
    assert gate.passcode_reason() == "codigo_antiguo"


def test_wrong_passcodes_wait_longer_each_time(gate):
    gate.set_passcode("246810")
    for _ in range(4):
        assert not gate.check_passcode("000000")["ok"]
    assert gate.check_passcode("000000").get("wait") == 0
    blocked = gate.check_passcode("246810")
    assert not blocked["ok"] and blocked["wait"] > 0  # even the right code waits
    gate.clock_ref.t += 61
    assert gate.check_passcode("246810")["ok"]


def test_lock_now(gate):
    gate.set_passcode("246810")
    gate.lock_now()
    assert gate.passcode_reason() == "bloqueado"


def test_changing_the_passcode_needs_the_current_one(gate):
    gate.set_passcode("246810")
    with pytest.raises(PermissionError):
        gate.set_passcode("135790", current="000000")
    gate.set_passcode("135790", current="246810")
    assert gate.check_passcode("135790")["ok"]


def test_a_challenge_is_random_used_once_and_expires(gate):
    gate.set_passcode("246810")
    actions = {gate.challenge().action for _ in range(60)}
    assert actions == set(faceid.ASKED)  # only gentle turns are asked
    c = gate.challenge()
    assert gate.take(c.nonce) is c
    assert gate.take(c.nonce) is None  # once
    c = gate.challenge()
    gate.clock_ref.t += 21
    assert gate.take(c.nonce) is None  # expired


def _frame(yaw=0.0, pitch=0.0, eyes=True, seed=0, feature=None, light=None):
    rng = np.random.default_rng(seed)
    f = feature if feature is not None else np.ones(128, np.float32) / np.sqrt(128)
    crop = rng.uniform(0, 255, (48, 48)).astype(np.float32)
    seen = 2 if eyes else 0
    return Frame(
        f,
        yaw,
        pitch,
        eyes,
        crop,
        1,
        seen,
        light if light is not None else (0.8 if eyes else 0.95),
    )


def test_a_still_photo_is_refused():
    still = _frame()
    frames = [Frame(still.feature, 0, 0, True, still.crop, 1) for _ in range(6)]
    ok, why = faceid.alive(frames, "izquierda")
    assert not ok and "foto" in why


def test_the_asked_movement_must_happen():
    turning = [
        _frame(yaw=y, seed=i) for i, y in enumerate((0, 1, 4, 9, 15, 18, 19, 20))
    ]
    assert faceid.alive(turning, "izquierda")[0]
    # A real turn the other way is still a live person (owner, oct. 2026:
    # setup failed too often); a still face is not.
    assert faceid.alive(turning, "derecha")[0]
    still = [_frame(seed=i) for i in range(8)]
    assert not faceid.alive(still, "derecha")[0]
    up = [_frame(pitch=p, seed=i) for i, p in enumerate((0, 1, 5, 10, 14, 16, 17, 17))]
    assert faceid.alive(up, "arriba")[0]
    blink = [
        _frame(eyes=e, seed=i)
        for i, e in enumerate((True, True, True, False, True, True))
    ]
    assert faceid.alive(blink, "parpadee")[0]
    no_blink = [_frame(eyes=True, seed=i) for i in range(6)]
    assert not faceid.alive(no_blink, "parpadee")[0]


def test_a_shaking_photo_is_not_a_turn_nor_a_blink():
    # A hand holding a photo: the pose jumps with noise but settles nowhere.
    noise = [0, 13, -6, 9, -11, 4, 12, -3]
    assert not faceid.alive(
        [_frame(yaw=y, seed=i) for i, y in enumerate(noise)], "izquierda"
    )[0]
    # The eye detector flickers on a still photo, but the lids never cover the
    # eyes: the eye patches do not get lighter.
    flicker = [
        _frame(eyes=e, seed=i, light=0.8)
        for i, e in enumerate((True, True, True, False, True, True))
    ]
    assert not faceid.alive(flicker, "parpadee")[0]


def test_attention_needs_open_eyes_looking_at_the_screen():
    assert faceid.attentive([_frame(yaw=30), _frame(eyes=True)])
    assert not faceid.attentive([_frame(yaw=30), _frame(eyes=False)])


def _unit(v):
    v = np.asarray(v, np.float32)
    return v / np.linalg.norm(v)


def test_only_the_owner_matches_and_twins_are_not_guessed():
    rng = np.random.default_rng(3)
    me = _unit(rng.normal(size=128))
    other = _unit(rng.normal(size=128))
    gallery = {"Daniel": np.stack([me]), "Ana": np.stack([other])}
    mine = [
        _frame(feature=_unit(me + rng.normal(0, 0.03, 128)), seed=i) for i in range(4)
    ]
    assert faceid.match_owner(mine, gallery, "Daniel")[0]
    stranger = [_frame(feature=other, seed=i) for i in range(4)]
    assert not faceid.match_owner(stranger, gallery, "Daniel")[0]
    twin = {
        "Daniel": np.stack([me]),
        "Gemelo": np.stack([_unit(me + rng.normal(0, 0.02, 128))]),
    }
    assert not faceid.match_owner(mine, twin, "Daniel")[0]  # no clear winner
    mixed = mine[:2] + stranger[:2]
    ok, _, why = faceid.match_owner(mixed, gallery, "Daniel")
    assert not ok and "más de una cara" in why


def test_face_id_endpoints_refuse_requests_relayed_from_outside(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import openjarvis.faces.routes as routes
    from openjarvis.faces.book import FaceBook

    monkeypatch.setattr(routes, "_book", FaceBook(tmp_path / "faces"))
    monkeypatch.setattr(routes, "_gate", None)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app, client=("127.0.0.1", 5000))
    assert client.get("/v1/faces/faceid").json()["passcode_reason"] == "sin_codigo"
    relayed = {"cf-connecting-ip": "203.0.113.9"}
    assert client.get("/v1/faces/faceid", headers=relayed).status_code == 403
    assert (
        client.post(
            "/v1/faces/faceid/passcode", data={"code": "246810"}, headers=relayed
        ).status_code
        == 403
    )
    assert client.post("/v1/faces/faceid/passcode", data={"code": "246810"}).json()[
        "passcode_set"
    ]
    challenge = client.post("/v1/faces/faceid/challenge").json()
    assert challenge["action"] in ("izquierda", "derecha", "arriba", "parpadee")
    relayed_challenge = client.post("/v1/faces/faceid/challenge", headers=relayed)
    assert relayed_challenge.status_code == 403


def test_a_camera_problem_never_spends_an_attempt(gate, monkeypatch):
    gate.set_passcode("246810")
    left = gate.status()["attempts_left"]
    still = [_frame(seed=i) for i in range(8)]  # no movement at all
    monkeypatch.setattr(faceid, "read_frames", lambda book, frames: still)
    c = gate.challenge()
    out = faceid.unlock(object(), gate, c.nonce, [b"x"] * 8, "Dani")
    assert not out["ok"] and out["retry"]
    assert out["attempts_left"] == left == gate.status()["attempts_left"]


def _q(**kw):
    f = _frame()
    for k, v in kw.items():
        setattr(f, k, v)
    return f


def test_picture_quality_is_a_retry_with_a_plain_reason():
    assert faceid.quality([_q() for _ in range(4)]) == (True, "")
    assert "Acérquese" in faceid.quality([_q(face_px=40.0)])[1]
    assert "poca luz" in faceid.quality([_q(bright=20.0)])[1]
    assert "demasiada luz" in faceid.quality([_q(bright=250.0)])[1]
    assert "borrosa" in faceid.quality([_q(sharp=1.0)])[1]
    assert not faceid.quality([])[0]


def test_a_tilted_photo_in_the_hand_is_not_a_live_turn():
    # The yaw looks like a real turn, but the eye line swings like a photo.
    yaws = (0, 1, 4, 9, 15, 18, 19, 20)
    rolls = (0, 20, -18, 25, -20, 18, -15, 20)
    frames = [_q(yaw=y, roll=r, seed=0) for y, r in zip(yaws, rolls)]
    for i, f in enumerate(frames):
        f.crop = _frame(seed=i).crop
    ok, why = faceid.alive(frames, "izquierda")
    assert not ok and "foto" in why
    level = [_q(yaw=y, roll=2.0) for y in yaws]
    for i, f in enumerate(level):
        f.crop = _frame(seed=i).crop
    assert faceid.alive(level, "izquierda")[0]


def test_one_lucky_frame_is_not_enough():
    rng = np.random.default_rng(5)
    me = _unit(rng.normal(size=128))
    gallery = {"Daniel": np.stack([me])}
    # Every frame is a different person except one that matches.
    frames = [_frame(feature=me, seed=0)] + [
        _frame(feature=_unit(me + rng.normal(0, 0.9, 128)), seed=i) for i in range(1, 4)
    ]
    assert not faceid.match_owner(frames, gallery, "Daniel")[0]


def test_head_roll_and_fit():
    row = [0, 0, 100, 100, 30, 50, 70, 50]
    assert abs(faceid.head_roll(row)) < 1e-6
    row = [0, 0, 100, 100, 30, 50, 70, 80]
    assert faceid.head_roll(row) == pytest.approx(36.87, abs=0.01)  # a 3-4-5 triangle
    big = np.zeros((1080, 1920, 3), np.uint8)
    small, scale = faceid.fit(big)
    assert max(small.shape[:2]) == faceid.DETECT_SIDE and scale == pytest.approx(1 / 3)
    tiny, one = faceid.fit(np.zeros((200, 300, 3), np.uint8))
    assert tiny.shape[:2] == (200, 300) and one == 1.0


def test_attempts_are_logged_without_pictures_or_names(gate):
    gate.audit(False, "poca luz", 0.0, 120)
    gate.audit(True, "", 0.71, 95)
    rows = gate.recent()
    assert [r["ok"] for r in rows] == [False, True]
    assert set(rows[0]) == {"t", "ok", "why", "score", "ms"}
    for i in range(faceid.LOG_LINES + 30):
        gate.audit(True, "", 0.7, 1)
    assert len(gate.recent(10_000)) == faceid.LOG_LINES

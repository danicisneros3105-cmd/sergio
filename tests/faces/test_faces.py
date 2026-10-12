"""Face recognition: storage, consent, API and tools (OpenCV mocked)."""

from __future__ import annotations

import numpy as np
import pytest

from openjarvis.faces import book as book_mod
from openjarvis.faces.book import FaceBook, FaceError


def _unit(vec):
    v = np.asarray(vec, dtype=np.float32)
    return v / np.linalg.norm(v)


ANA = _unit([1, 0, 0, 0])
LUIS = _unit([0, 1, 0, 0])


@pytest.fixture
def book(tmp_path, monkeypatch):
    b = FaceBook(tmp_path / "faces")
    faces_by_image = {
        b"ana": [(ANA, (1, 2, 130, 140))],
        b"ana2": [(_unit([0.95, 0.05, 0, 0]), (5, 6, 120, 130))],
        b"luis": [(LUIS, (0, 0, 90, 90))],
        b"group": [
            (ANA, (0, 0, 100, 100)),
            (_unit([0, 0, 1, 0]), (200, 0, 100, 100)),
        ],
        b"empty": [],
    }

    def fake_faces(data, **_kw):
        if data not in faces_by_image:
            raise FaceError("The file is not a readable image.")
        return faces_by_image[data]

    monkeypatch.setattr(b, "_faces", fake_faces)
    return b


def test_enroll_requires_consent_valid_name_and_one_face(book):
    with pytest.raises(FaceError, match="consent"):
        book.enroll("Ana", b"ana", consent=False)
    with pytest.raises(FaceError, match="plain name"):
        book.enroll("../etc", b"ana", consent=True)
    with pytest.raises(FaceError, match="exactly one face"):
        book.enroll("Ana", b"group", consent=True)
    assert book.enroll("Ana", b"ana", consent=True) == 1
    assert book.enroll("Ana", b"ana2", consent=True) == 2
    assert book.people()[0]["name"] == "Ana" and book.people()[0]["samples"] == 2


def test_identify_names_only_enrolled_people(book):
    book.enroll("Ana", b"ana", consent=True)
    faces = book.identify(b"group")
    assert [f.name for f in faces] == ["Ana", ""]
    assert faces[0].to_dict()["name"] == "Ana" and faces[1].to_dict()["name"] is None
    assert book.identify(b"luis")[0].name == ""


def test_forget_removes_everything_and_file_is_private(book, tmp_path):
    book.enroll("Ana", b"ana", consent=True)
    assert (tmp_path / "faces" / "people.json").stat().st_mode & 0o077 == 0
    assert book.forget("Ana") is True and book.people() == []
    assert book.forget("Ana") is False


def test_samples_are_capped(book):
    for _ in range(book_mod.MAX_SAMPLES + 5):
        book.enroll("Ana", b"ana", consent=True)
    assert book.people()[0]["samples"] == book_mod.MAX_SAMPLES


def test_model_download_is_checksum_verified(tmp_path, monkeypatch):
    import io

    monkeypatch.setattr(
        book_mod.urllib.request, "urlopen", lambda url, timeout: io.BytesIO(b"evil")
    )
    with pytest.raises(FaceError, match="checksum"):
        book_mod.ensure_model("detector", tmp_path)
    assert not list(tmp_path.iterdir())


def test_api_and_tools(book, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.faces import routes

    monkeypatch.delenv("SERGIO_OWNER_NAME", raising=False)
    monkeypatch.setattr("openjarvis.tools.desktop_tools._config_owner", lambda: "")
    from openjarvis.tools.face_tools import FaceIdentifyTool, FaceListTool

    routes._book = book
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    files = {"image": ("a.jpg", b"ana", "image/jpeg")}
    assert (
        client.post("/v1/faces/enroll", data={"name": "Ana"}, files=files).status_code
        == 400
    )
    ok = client.post(
        "/v1/faces/enroll", data={"name": "Ana", "consent": "true"}, files=files
    )
    assert ok.json() == {"name": "Ana", "samples": 1}
    faces = client.post(
        "/v1/faces/identify", files={"image": ("g.jpg", b"group", "image/jpeg")}
    ).json()["faces"]
    assert [f["name"] for f in faces] == ["Ana", None]
    # the first person enrolled is the owner (Sergio calls them «señor»)
    assert [f["owner"] for f in faces] == [True, False]
    assert client.get("/v1/faces/owner").json() == {"owner": "Ana"}
    assert client.get("/v1/faces").json()["people"][0]["name"] == "Ana"
    assert client.get("/v1/faces/mesh/Ana").status_code == 404

    photo = tmp_path / "group.jpg"
    photo.write_bytes(b"group")
    result = FaceIdentifyTool(book=book).execute(image_path=str(photo))
    assert result.success and "Ana, unknown person" in result.content
    assert "Ana (1)" in FaceListTool(book=book).execute().content
    assert not FaceIdentifyTool(book=book).execute(image_path="/nope.jpg").success

    assert client.delete("/v1/faces/Ana").status_code == 200
    assert client.delete("/v1/faces/Ana").status_code == 404
    routes._book = None


def test_no_enrollment_tool_exists():
    import openjarvis.tools.face_tools as ft

    assert not hasattr(ft, "FaceEnrollTool")


def test_damaged_file_is_never_overwritten(book, tmp_path):
    book.enroll("Ana", b"ana", consent=True)
    db = tmp_path / "faces" / "people.json"
    db.write_text("{truncated")
    with pytest.raises(FaceError, match="damaged"):
        book.enroll("Luis", b"luis", consent=True)
    with pytest.raises(FaceError, match="damaged"):
        book.forget("Ana")
    assert db.read_text() == "{truncated"  # nothing lost
    assert book.people() == []  # reading stays tolerant


# -- "not everyone is Daniel": stricter matching, guests, clean names --------
def _near(vec, noise, seed):
    rng = np.random.default_rng(seed)
    return _unit(np.asarray(vec, dtype=np.float32) + rng.normal(0, noise, len(vec)))


def test_names_are_cleaned_and_old_entries_merged(tmp_path):
    import json

    from openjarvis.faces.book import clean_name

    assert clean_name("daniel cisneros .") == "Daniel Cisneros"
    assert clean_name("  maría  DE la  o, ") == "María de la O"
    root = tmp_path / "faces"
    root.mkdir()
    (root / "people.json").write_text(
        json.dumps(
            {
                "Daniel Cisneros .": {"embeddings": [[1, 0]], "enrolled_at": 1},
                "daniel cisneros": {"embeddings": [[0, 1]], "enrolled_at": 2},
            }
        )
    )
    people = FaceBook(root).people()
    assert people == [
        {
            "name": "Daniel Cisneros",
            "samples": 2,
            "enrolled_at": 1,
            "signatures": 0,
            "angles": 0,
            "scanned": False,
            "mesh3d": False,
            "learned": 0,
        }
    ]


def test_a_stranger_is_not_the_only_enrolled_person(tmp_path, monkeypatch):
    """With one person enrolled, a look-alike scoring 0.38 used to be "Dani"."""
    dim = 128
    rng = np.random.default_rng(0)
    dani = _unit(rng.normal(size=dim))
    stranger = _unit(0.38 * dani + 0.92 * _unit(rng.normal(size=dim)))
    b = FaceBook(tmp_path / "faces")
    photos = {
        f"dani{i}".encode(): [(_near(dani, 0.05, i), (0, 0, 150, 150), 0.97)]
        for i in range(8)
    }
    photos[b"stranger"] = [(stranger, (0, 0, 150, 150), 0.97)]
    photos[b"dani_live"] = [(_near(dani, 0.08, 99), (0, 0, 150, 150), 0.95)]
    monkeypatch.setattr(b, "_faces", lambda data, **_kw: photos[data])
    for i in range(8):
        b.enroll("Dani", f"dani{i}".encode(), consent=True)
    assert b.identify(b"dani_live")[0].name == "Dani"
    unknown = b.identify(b"stranger")[0]
    assert unknown.name == "" and unknown.guest == 1
    # the same stranger keeps the same number; a second one gets the next
    assert b.identify(b"stranger")[0].guest == 1
    other = _unit(rng.normal(size=dim))
    photos[b"other"] = [(other, (0, 0, 150, 150), 0.97)]
    assert b.identify(b"other")[0].guest == 2


def test_two_similar_people_need_a_clear_winner(tmp_path, monkeypatch):
    b = FaceBook(tmp_path / "faces")
    a = _unit([1, 0.0, 0, 0])
    c = _unit([1, 0.15, 0, 0])  # siblings: both match well
    photos = {
        b"a": [(a, (0, 0, 100, 100), 0.99)],
        b"c": [(c, (0, 0, 100, 100), 0.99)],
        b"between": [(_unit([1, 0.075, 0, 0]), (0, 0, 100, 100), 0.99)],
    }
    monkeypatch.setattr(b, "_faces", lambda data, **_kw: photos[data])
    b.enroll("Ana", b"a", consent=True)
    # Carla's face is almost Ana's: saving it under a new name is refused...
    with pytest.raises(FaceError, match="ya está guardada como Ana"):
        b.enroll("Carla", b"c", consent=True)
    # ...but if both were saved before (twins), it is never guessed.
    # (the file is encrypted at rest: edit it through the book)
    people = b._load()
    people["Carla"] = {"embeddings": [c.tolist()], "enrolled_at": 2}
    b._save(people)
    assert b.identify(b"a")[0].name == ""  # too close to call: not guessed
    assert b.identify(b"between")[0].name == ""


def test_tiny_or_blurry_faces_are_not_named(tmp_path, monkeypatch):
    b = FaceBook(tmp_path / "faces")
    photos = {
        b"ana": [(ANA, (0, 0, 120, 120), 0.99)],
        b"far": [(ANA, (0, 0, 24, 24), 0.99)],
        b"blur": [(ANA, (0, 0, 120, 120), 0.6)],
    }
    monkeypatch.setattr(b, "_faces", lambda data, **_kw: photos[data])
    b.enroll("Ana", b"ana", consent=True)
    far, blur = b.identify(b"far")[0], b.identify(b"blur")[0]
    assert (far.name, far.quality) == ("", "pequeña")
    assert (blur.name, blur.quality) == ("", "borrosa")
    assert b.identify(b"ana")[0].to_dict()["quality"] == "ok"


def test_a_stranger_saved_as_the_owner_is_refused_and_old_mistakes_repaired(
    tmp_path, monkeypatch
):
    """Everyone was "Daniel Cisneros": strangers' photos had been saved as him."""
    import json

    from openjarvis.faces.book import purify

    rng = np.random.default_rng(3)
    dani, other = _unit(rng.normal(size=128)), _unit(rng.normal(size=128))
    b = FaceBook(tmp_path / "faces")
    photos = {
        f"d{i}".encode(): [(_near(dani, 0.05, i), (0, 0, 150, 150), 0.97)]
        for i in range(4)
    }
    photos[b"other"] = [(_near(other, 0.05, 50), (0, 0, 150, 150), 0.97)]
    monkeypatch.setattr(b, "_faces", lambda data, **_kw: photos[data])
    for i in range(3):
        b.enroll("Daniel Cisneros", f"d{i}".encode(), consent=True)
    with pytest.raises(FaceError, match="no parece de Daniel Cisneros"):
        b.enroll("Daniel Cisneros", b"other", consent=True)
    assert b.enroll("Ana", b"other", consent=True) == 1  # with her own name: fine
    # A file damaged by the old bug: 6 photos of Dani and 4 of someone else.
    emb = [_near(dani, 0.05, i).tolist() for i in range(6)] + [
        _near(other, 0.05, 60 + i).tolist() for i in range(4)
    ]
    (tmp_path / "faces" / "people.json").write_text(
        json.dumps({"Daniel Cisneros": {"embeddings": emb, "enrolled_at": 1}})
    )
    assert b.people()[0]["samples"] == 6
    assert b.identify(b"other")[0].name == ""
    assert b.identify(b"d3")[0].name == "Daniel Cisneros"
    kept, sigs = purify(emb[:2], [None, None])  # too few to judge: untouched
    assert len(kept) == 2 and len(sigs) == 2


def test_face_enroll_tool_never_guesses_the_name():
    from openjarvis.tools.desktop_tools import FaceEnrollTool

    result = FaceEnrollTool().execute(name="")
    assert not result.success and "Cómo se llama" in result.content


def test_head_angle_from_the_five_points():
    from openjarvis.faces.book import angle_of, head_pose

    # x, y, w, h, right eye, left eye, nose, right mouth, left mouth
    front = [0, 0, 100, 100, 30, 40, 70, 40, 50, 57, 35, 70, 65, 70]
    yaw, pitch = head_pose(front)
    assert abs(yaw) < 5 and abs(pitch) < 8 and angle_of((yaw, pitch)) == "C-M"
    turned = [
        0,
        0,
        100,
        100,
        30,
        40,
        70,
        40,
        66,
        57,
        35,
        70,
        65,
        70,
    ]  # nose to one side
    assert angle_of(head_pose(turned)) == "R-M"
    up = [0, 0, 100, 100, 30, 40, 70, 40, 50, 46, 35, 70, 65, 70]  # nose near the eyes
    assert angle_of(head_pose(up)) == "C-U"
    assert head_pose([1, 2]) == (0.0, 0.0)


def _scan_book(tmp_path, monkeypatch, person, *, other=None):
    """Frames named "<angle>-<i>" show *person* at that head angle."""
    poses = {
        "C-M": (0, 0),
        "L-M": (-30, 0),
        "R-M": (30, 0),
        "C-U": (0, 25),
        "C-D": (0, -25),
    }
    b = FaceBook(tmp_path / "faces")
    frames = {}
    for angle, pose in poses.items():
        for i in range(3):
            # turning the head lowers SFace's score: farther from the front
            drift = 0.25 if angle != "C-M" else 0.05
            frames[f"{angle}-{i}".encode()] = [
                (
                    _near(person, drift, sum(map(ord, angle)) * 10 + i),
                    (0, 0, 150, 150),
                    0.97,
                    pose,
                    50.0 + i,
                )
            ]
    if other is not None:
        frames[b"other"] = [(other, (0, 0, 150, 150), 0.97, (0, 0), 60.0)]
    frames[b"two"] = [
        (person, (0, 0, 150, 150), 0.97, (0, 0), 60.0),
        (_unit(np.ones(person.size)), (200, 0, 140, 140), 0.97, (0, 0), 60.0),
    ]
    monkeypatch.setattr(b, "_faces", lambda data, **_kw: frames[data])
    return b, frames


def test_scan_keeps_the_sharpest_photos_of_each_head_angle(tmp_path, monkeypatch):
    rng = np.random.default_rng(3)
    dani = _unit(rng.normal(size=128))
    b, frames = _scan_book(tmp_path, monkeypatch, dani)
    mesh = {"points": [[0.0, 0.0, 0.0]] * 478, "unit": "mm"}
    out = b.scan(
        "Dani", [k for k in frames if k not in (b"two",)], consent=True, mesh=mesh
    )
    assert out["angles"] == ["C-D", "C-M", "C-U", "L-M", "R-M"]
    assert out["added"] == 10  # two per angle, the sharpest ones
    person = b.people()[0]
    assert person["angles"] == 5 and person["scanned"] and person["mesh3d"]
    assert b.mesh("dani")["unit"] == "mm"
    # a frame with two people in it is not used (it is not one face)
    with pytest.raises(FaceError, match="No vi la cara"):
        b.scan("Dani", [b"two", b"C-M-0"], consent=True)


def test_scan_needs_consent_and_several_angles(tmp_path, monkeypatch):
    rng = np.random.default_rng(4)
    b, frames = _scan_book(tmp_path, monkeypatch, _unit(rng.normal(size=128)))
    with pytest.raises(FaceError, match="consent"):
        b.scan("Dani", list(frames), consent=False)
    with pytest.raises(FaceError, match="ángulo"):
        b.scan("Dani", [b"C-M-0", b"C-M-1", b"C-M-2"], consent=True)


def test_a_scan_of_someone_already_saved_under_another_name_is_refused(
    tmp_path, monkeypatch
):
    rng = np.random.default_rng(5)
    dani = _unit(rng.normal(size=128))
    b, frames = _scan_book(tmp_path, monkeypatch, dani)
    b.scan("Dani", list(k for k in frames if k != b"two"), consent=True)
    with pytest.raises(FaceError, match="ya está guardada como Dani"):
        b.scan("Ana", list(k for k in frames if k != b"two"), consent=True)


def test_strong_matches_are_named_at_once_and_it_learns_missing_angles(
    tmp_path, monkeypatch
):
    rng = np.random.default_rng(6)
    dani = _unit(rng.normal(size=128))
    b = FaceBook(tmp_path / "faces")
    photos = {
        f"p{i}".encode(): [(_near(dani, 0.03, i), (0, 0, 150, 150), 0.97, (0, 0), 50.0)]
        for i in range(3)
    }
    photos[b"side"] = [(_near(dani, 0.04, 77), (0, 0, 150, 150), 0.97, (35, 0), 50.0)]
    photos[b"side2"] = [(_near(dani, 0.04, 78), (0, 0, 150, 150), 0.97, (35, 0), 50.0)]
    monkeypatch.setattr(b, "_faces", lambda data, **_kw: photos[data])
    for i in range(3):
        b.enroll("Dani", f"p{i}".encode(), consent=True)
    seen = b.identify(b"side", learn=True)[0]
    assert seen.name == "Dani" and seen.strong and seen.to_dict()["strong"] is True
    assert seen.learned and seen.to_dict()["angle"] == "R-M"
    assert b.people()[0]["learned"] == 1 and b.people()[0]["samples"] == 4
    # at most one photo a minute: the next look does not add another
    assert b.identify(b"side2", learn=True)[0].learned is False
    # without learn=True it never writes
    clock = [1e12]
    monkeypatch.setattr(book_mod.time, "time", lambda: clock[0])
    assert b.identify(b"side2")[0].learned is False
    assert b.people()[0]["samples"] == 4


def test_learnt_photos_are_dropped_first_when_full(tmp_path, monkeypatch):
    from openjarvis.faces.book import _add_samples

    person = {"embeddings": [], "enrolled_at": 1}
    _add_samples(person, [([1.0, 0.0], None, (0, 0), "escaneo")] * 6)
    _add_samples(person, [([1.0, 0.1], None, (0, 0), "auto")] * 4)
    _add_samples(
        person, [([1.0, 0.2], None, (0, 0), "foto")] * (book_mod.MAX_SAMPLES - 10)
    )
    assert len(person["embeddings"]) == book_mod.MAX_SAMPLES
    _add_samples(person, [([1.0, 0.3], None, (0, 0), "foto")] * 3)
    assert person["sources"].count("auto") == 1  # the learnt ones went first
    assert person["sources"].count("escaneo") == 6  # the scan's angles stay
    assert (
        len(person["poses"]) == len(person["embeddings"]) == len(person["signatures"])
    )


def test_gallery_is_cached_until_the_file_changes(book):
    book.enroll("Ana", b"ana", consent=True)
    first = book._gallery()
    assert book._gallery() is first  # no re-reading on every look
    book.enroll("Ana", b"ana2", consent=True)
    assert book._gallery() is not first and len(book._gallery()["Ana"]) == 2


def test_purify_keeps_the_extra_columns_aligned():
    from openjarvis.faces.book import purify

    a = [1.0, 0.0, 0.0]
    b2 = [0.0, 1.0, 0.0]
    embs, sigs, poses = purify([a, a, a, b2], ["s1", "s2", "s3", "x"], [1, 2, 3, 9])
    assert len(embs) == 3 and sigs == ["s1", "s2", "s3"] and poses == [1, 2, 3]


def test_scan_api(tmp_path, monkeypatch):
    import json

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.faces import routes

    rng = np.random.default_rng(9)
    b, frames = _scan_book(tmp_path, monkeypatch, _unit(rng.normal(size=128)))
    routes._book = b
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    files = [
        ("images", (f"{k.decode()}.jpg", k, "image/jpeg"))
        for k in frames
        if k != b"two"
    ]
    mesh = {"points": [[1.0, 2.0, 3.0]] * 478, "unit": "mm"}
    refused = client.post("/v1/faces/scan", data={"name": "Dani"}, files=files)
    assert refused.status_code == 400 and "consent" in refused.json()["detail"]
    done = client.post(
        "/v1/faces/scan",
        data={"name": "dani", "consent": "true", "mesh": json.dumps(mesh)},
        files=files,
    ).json()
    assert (
        done["name"] == "Dani"
        and len(done["angles"]) == 5
        and "de frente" in done["words"]
    )
    assert client.get("/v1/faces/mesh/Dani").json()["points"][0] == [1.0, 2.0, 3.0]
    routes._book = None


def test_face_enroll_tool_runs_the_scan_on_the_companion(monkeypatch):
    from openjarvis.tools.desktop_tools import FaceEnrollTool

    calls = []

    def fake_call(self, method, path, **kw):
        calls.append((method, path, kw.get("json")))
        return {
            "ok": True,
            "result": "Listo: ya conozco la cara de Ana desde 6 ángulos.",
        }

    monkeypatch.setattr(FaceEnrollTool, "_call", fake_call)
    result = FaceEnrollTool().execute(name="Ana")
    assert result.success and "6 ángulos" in result.content
    assert calls == [("POST", "/skill", {"name": "face_scan", "args": {"name": "Ana"}})]


def test_face_enroll_tool_falls_back_to_photos_on_an_old_companion(
    monkeypatch, tmp_path
):
    import base64

    from openjarvis.tools import desktop_tools

    shots = []

    def fake_call(self, method, path, **kw):
        if path == "/skill":
            raise RuntimeError("unknown skill")
        shots.append(path)
        return {"image_jpeg_b64": base64.b64encode(b"ana").decode()}

    class Book:
        def enroll(self, name, data, consent):
            return 3

    monkeypatch.setattr(desktop_tools.FaceEnrollTool, "_call", fake_call)
    monkeypatch.setattr("openjarvis.faces.FaceBook", lambda: Book())
    monkeypatch.setattr("time.sleep", lambda s: None)
    result = desktop_tools.FaceEnrollTool().execute(name="Ana")
    assert result.success and shots == ["/camera"] * 5


def test_faces_are_encrypted_at_rest_and_old_plain_files_still_read(tmp_path):
    import json

    root = tmp_path / "faces"
    root.mkdir()
    db = root / "people.json"
    db.write_text(json.dumps({"Ana": {"embeddings": [[1, 0]], "enrolled_at": 1}}))
    book = FaceBook(root)
    assert [p["name"] for p in book.people()] == ["Ana"]  # plain file still read
    book._save(book._load())
    raw = db.read_bytes()
    assert raw.startswith(b"gAAAA") and b"Ana" not in raw and b"embeddings" not in raw
    key = tmp_path / "keys" / "faces.key"
    assert key.stat().st_mode & 0o077 == 0
    assert [p["name"] for p in FaceBook(root).people()] == ["Ana"]
    key.write_bytes(
        b"x" * 44
    )  # the wrong key: unreadable, never "empty and overwritten"
    with pytest.raises(FaceError, match="damaged"):
        FaceBook(root)._load(strict=True)

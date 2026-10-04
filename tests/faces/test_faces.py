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

    def fake_faces(data):
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


def test_api_and_tools(book, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.faces import routes
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
    assert client.get("/v1/faces").json()["people"][0]["name"] == "Ana"

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
        {"name": "Daniel Cisneros", "samples": 2, "enrolled_at": 1}
    ]


def test_a_stranger_is_not_the_only_enrolled_person(tmp_path, monkeypatch):
    """With one person enrolled, a look-alike scoring 0.38 used to be "Dani"."""
    dim = 128
    rng = np.random.default_rng(0)
    dani = _unit(rng.normal(size=dim))
    stranger = _unit(0.38 * dani + 0.92 * _unit(rng.normal(size=dim)))
    b = FaceBook(tmp_path / "faces")
    photos = {f"dani{i}".encode(): [(_near(dani, 0.05, i), (0, 0, 150, 150), 0.97)] for i in range(8)}
    photos[b"stranger"] = [(stranger, (0, 0, 150, 150), 0.97)]
    photos[b"dani_live"] = [(_near(dani, 0.08, 99), (0, 0, 150, 150), 0.95)]
    monkeypatch.setattr(b, "_faces", lambda data: photos[data])
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
    monkeypatch.setattr(b, "_faces", lambda data: photos[data])
    b.enroll("Ana", b"a", consent=True)
    b.enroll("Carla", b"c", consent=True)
    assert b.identify(b"a")[0].name == ""  # too close to call: not guessed
    assert b.identify(b"between")[0].name == ""


def test_tiny_or_blurry_faces_are_not_named(tmp_path, monkeypatch):
    b = FaceBook(tmp_path / "faces")
    photos = {
        b"ana": [(ANA, (0, 0, 120, 120), 0.99)],
        b"far": [(ANA, (0, 0, 24, 24), 0.99)],
        b"blur": [(ANA, (0, 0, 120, 120), 0.6)],
    }
    monkeypatch.setattr(b, "_faces", lambda data: photos[data])
    b.enroll("Ana", b"ana", consent=True)
    far, blur = b.identify(b"far")[0], b.identify(b"blur")[0]
    assert (far.name, far.quality) == ("", "pequeña")
    assert (blur.name, blur.quality) == ("", "borrosa")
    assert b.identify(b"ana")[0].to_dict()["quality"] == "ok"

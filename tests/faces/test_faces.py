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
        b"ana": [(ANA, (1, 2, 3, 4))],
        b"ana2": [(_unit([0.95, 0.05, 0, 0]), (5, 6, 7, 8))],
        b"luis": [(LUIS, (0, 0, 9, 9))],
        b"group": [(ANA, (0, 0, 1, 1)), (_unit([0, 0, 1, 0]), (2, 2, 1, 1))],
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

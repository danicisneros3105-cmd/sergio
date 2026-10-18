"""Everyday document ingestion, invalid batches, and server responsiveness."""

import asyncio
import io
import threading
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from openjarvis.connectors.store import KnowledgeStore
from openjarvis.server import upload_router as uploads


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        uploads, "_get_store", lambda: KnowledgeStore(tmp_path / "knowledge.db")
    )
    app = FastAPI()
    app.include_router(uploads.router)
    return TestClient(app)


def test_professional_notes_and_source_files_are_searchable(client, tmp_path):
    response = client.post(
        "/v1/connectors/upload/ingest/files",
        files=[
            ("files", ("design.md", b"Migration rollout checklist")),
            ("files", ("metrics.csv", b"latency,120\nerrors,0")),
        ],
    )
    assert response.status_code == 200
    assert response.json()["chunks_added"] == 2
    with KnowledgeStore(tmp_path / "knowledge.db") as store:
        assert store.retrieve("Migration")[0].content == "Migration rollout checklist"


def test_invalid_batch_writes_no_partial_documents(client, tmp_path):
    response = client.post(
        "/v1/connectors/upload/ingest/files",
        files=[
            ("files", ("ok.txt", b"valid note")),
            ("files", ("bad.exe", b"invalid")),
        ],
    )
    assert response.status_code == 400
    assert not (tmp_path / "knowledge.db").exists()


def test_file_and_batch_limits(client, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_FILE_BYTES", 8)
    monkeypatch.setattr(uploads, "MAX_BATCH_BYTES", 10)
    for files in [
        [("files", ("large.txt", b"x" * 9))],
        [("files", ("a.txt", b"x" * 6)), ("files", ("b.txt", b"x" * 6))],
        [("files", ("a.txt", b"x"))] * (uploads.MAX_FILES + 1),
    ]:
        assert (
            client.post("/v1/connectors/upload/ingest/files", files=files).status_code
            == 413
        )


def _has_pdf_reader() -> bool:
    for name in ("pdfplumber", "PyPDF2"):
        try:
            __import__(name)
            return True
        except ImportError:
            continue
    return False


@pytest.mark.skipif(not _has_pdf_reader(), reason="no PDF reader installed")
def test_malformed_pdf_rejected(client):
    assert (
        client.post(
            "/v1/connectors/upload/ingest/files",
            files={"files": ("bad.pdf", b"not PDF")},
        ).status_code
        == 400
    )


def test_expanded_docx_rejected(client, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_BATCH_BYTES", 300)
    archive = io.BytesIO()
    with ZipFile(archive, "w", compression=8) as z:
        z.writestr("word/document.xml", "x" * 1000)
    assert (
        client.post(
            "/v1/connectors/upload/ingest/files",
            files={"files": ("bomb.docx", archive.getvalue())},
        ).status_code
        == 413
    )


@pytest.mark.asyncio
async def test_slow_parser_does_not_block_event_loop(monkeypatch):
    from starlette.datastructures import UploadFile

    started, release = threading.Event(), threading.Event()

    def slow_parse(data, ext):
        started.set()
        assert release.wait(3)
        return "content"

    monkeypatch.setattr(uploads, "_parse_upload_bounded", slow_parse)
    monkeypatch.setattr(uploads, "_store_documents", lambda docs: len(docs))
    task = asyncio.create_task(
        uploads.ingest_files(
            [UploadFile(io.BytesIO(b"data"), filename="report.pdf")], title=None
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 2)
        assert not task.done()
    finally:
        release.set()
        await task


def test_paste_length_and_empty_content(client):
    assert (
        client.post("/v1/connectors/upload/ingest", json={"content": "   "}).status_code
        == 400
    )
    assert (
        client.post(
            "/v1/connectors/upload/ingest",
            json={"content": "x" * (uploads.MAX_TEXT_CHARS + 1)},
        ).status_code
        == 422
    )

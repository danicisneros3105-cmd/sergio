"""Real SQLite rollback, parser workers and pre-multipart body limits."""

import asyncio
import io
from unittest.mock import MagicMock

import pytest

from openjarvis.connectors.store import KnowledgeStore
from openjarvis.server import upload_router as uploads
from openjarvis.server.upload_limits import UploadLimitsMiddleware


def test_sqlite_failure_rolls_back_entire_batch_and_fts(tmp_path, monkeypatch):
    path = tmp_path / "knowledge.db"
    store = KnowledgeStore(path)
    store.store("existing knowledge", source="upload")
    store._conn.execute("""CREATE TRIGGER fail_chunk BEFORE INSERT ON knowledge_chunks
                          WHEN NEW.content = 'fail' BEGIN SELECT RAISE(ABORT, 'disk failure'); END""")
    store._conn.commit()
    bus = MagicMock()
    monkeypatch.setattr("openjarvis.connectors.store.get_event_bus", lambda: bus)
    monkeypatch.setattr(uploads, "_get_store", lambda: store)
    with pytest.raises(Exception, match="disk failure"):
        uploads._store_documents(
            [("new migration", "md", "plan"), ("fail", "txt", "bad")]
        )
    bus.publish.assert_not_called()
    with KnowledgeStore(path) as reopened:
        assert reopened.retrieve("existing")
        assert not reopened.retrieve("migration")
        assert (
            reopened._conn.execute("SELECT count(*) FROM knowledge_chunks").fetchone()[
                0
            ]
            == 1
        )


def test_successful_transaction_emits_only_after_commit(tmp_path, monkeypatch):
    with KnowledgeStore(tmp_path / "db") as store:
        bus = MagicMock()
        monkeypatch.setattr("openjarvis.connectors.store.get_event_bus", lambda: bus)
        with store.transaction():
            store.store("design review")
            store.store("release checklist")
            bus.publish.assert_not_called()
        assert bus.publish.call_count == 2
        assert store.retrieve("checklist")


def test_real_pdf_worker_extracts_professional_report():
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(50, 700, "Professional rollout checklist")
    pdf.save()
    assert "rollout checklist" in uploads._parse_upload_bounded(
        stream.getvalue(), ".pdf"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [[], [(b"content-length", b"1000")]])
async def test_oversized_body_is_rejected_before_parser(headers):
    calls, sent = [], []

    async def app(scope, receive, send):
        calls.append(True)

    frames = iter(
        [
            {"type": "http.request", "body": b"x" * 6, "more_body": True},
            {"type": "http.request", "body": b"y" * 6, "more_body": False},
        ]
    )

    async def receive():
        return next(frames)

    async def send(message):
        sent.append(message)

    middleware = UploadLimitsMiddleware(app, max_bytes=10)
    await middleware(
        {
            "type": "http",
            "path": "/v1/connectors/upload/ingest/files",
            "headers": headers,
        },
        receive,
        send,
    )
    assert sent[0]["status"] == 413 and not calls


@pytest.mark.asyncio
async def test_upload_concurrency_and_replay():
    entered, release = asyncio.Event(), asyncio.Event()
    bodies, statuses = [], []

    async def app(scope, receive, send):
        bodies.append((await receive())["body"])
        entered.set()
        await release.wait()

    async def receive():
        return {"type": "http.request", "body": b"report", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    middleware = UploadLimitsMiddleware(app, max_concurrent=1)
    scope = {"type": "http", "path": "/v1/connectors/upload/ingest", "headers": []}
    first = asyncio.create_task(middleware(scope, receive, send))
    await entered.wait()
    try:
        await middleware(scope, receive, send)
        assert statuses == [429]
    finally:
        release.set()
        await first
    assert bodies == [b"report"]

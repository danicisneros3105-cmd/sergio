"""Upload / Paste router for ingesting documents into the knowledge store."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from openjarvis.connectors.store import KnowledgeStore
from openjarvis.core.config import DEFAULT_CONFIG_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/connectors/upload", tags=["upload"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".docx"}
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_BATCH_BYTES = 50 * 1024 * 1024
MAX_FILES = 10
MAX_TEXT_CHARS = 5 * 1024 * 1024


def _chunk_text(text: str, max_chars: int = 1000) -> List[str]:
    """Split *text* into ~max_chars pieces at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current.strip():
        chunks.append(current.strip())
    # Guard against very large paragraphs that exceed max_chars
    final: List[str] = []
    for chunk in chunks:
        while len(chunk) > max_chars:
            # Find last space within limit
            split_at = chunk.rfind(" ", 0, max_chars)
            if split_at == -1:
                split_at = max_chars
            final.append(chunk[:split_at].strip())
            chunk = chunk[split_at:].strip()
        if chunk:
            final.append(chunk)
    return final


def _bounded_text(parts) -> str:
    pages, length = [], 0
    for part in parts:
        length += len(part) + 2
        if length > MAX_TEXT_CHARS:
            raise HTTPException(413, "Extracted document text is too large")
        pages.append(part)
    return "\n\n".join(pages)


def _extract_text_from_pdf(data: bytes) -> str:
    """Extract text from a PDF using pdfplumber or PyPDF2."""
    # Try pdfplumber first
    try:
        import pdfplumber  # type: ignore[import-untyped]

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return _bounded_text(p.extract_text() or "" for p in pdf.pages)
    except ImportError:
        pass

    # Fall back to PyPDF2
    try:
        from PyPDF2 import PdfReader  # type: ignore[import-untyped]

        reader = PdfReader(io.BytesIO(data))
        return _bounded_text(p.extract_text() or "" for p in reader.pages)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail=(
                "PDF parsing requires pdfplumber or PyPDF2. "
                "Install one with: pip install pdfplumber"
            ),
        )


def _extract_text_from_docx(data: bytes) -> str:
    """Extract text from a .docx file using python-docx."""
    try:
        from docx import Document  # type: ignore[import-untyped]

        doc = Document(io.BytesIO(data))
        return _bounded_text(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail=(
                "DOCX parsing requires python-docx. "
                "Install with: pip install python-docx"
            ),
        )


def _get_store() -> KnowledgeStore:
    """Return a KnowledgeStore pointing at the default knowledge DB."""
    db_path = DEFAULT_CONFIG_DIR / "knowledge.db"
    return KnowledgeStore(db_path=db_path)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PasteRequest(BaseModel):
    title: str = Field(default="", max_length=512)
    content: str = Field(max_length=MAX_TEXT_CHARS)


class IngestResponse(BaseModel):
    chunks_added: int
    source: str = "upload"


def _validate_docx(data: bytes) -> None:
    from zipfile import BadZipFile, ZipFile

    try:
        with ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (
                len(entries) > 5000
                or sum(item.file_size for item in entries) > MAX_BATCH_BYTES
            ):
                raise HTTPException(413, "Expanded document is too large")
    except BadZipFile as exc:
        raise HTTPException(400, "Document could not be parsed") from exc


def _parse_upload(data: bytes, ext: str) -> str:
    try:
        if ext in (".txt", ".md", ".csv"):
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("latin-1")
        if ext == ".pdf":
            return _extract_text_from_pdf(data)
        if ext == ".docx":
            _validate_docx(data)
            return _extract_text_from_docx(data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "Document could not be parsed") from exc
    return ""


def _store_documents(documents: List[tuple[str, str, str]]) -> int:
    store = _get_store()
    total = 0
    try:
        with store.transaction():
            for text, doc_type, title in documents:
                chunks = _chunk_text(text)
                doc_id = str(uuid.uuid4())
                for idx, chunk in enumerate(chunks):
                    store.store(
                        chunk,
                        source="upload",
                        doc_type=doc_type,
                        doc_id=doc_id,
                        title=title,
                        chunk_index=idx,
                    )
                total += len(chunks)
        return total
    finally:
        store.close()


def _parse_upload_bounded(data: bytes, ext: str) -> str:
    if ext not in {".pdf", ".docx"}:
        return _parse_upload(data, ext)
    from openjarvis.security.process_runner import run_bounded

    if ext == ".docx":
        _validate_docx(data)
    # TemporaryDirectory permits reopening the file on Windows too.
    with tempfile.TemporaryDirectory(prefix="sergio-document-") as folder:
        path = Path(folder) / ("document" + ext)
        path.write_bytes(data)
        env = {
            k: os.environ[k]
            for k in ("PATH", "SystemRoot", "TEMP", "TMP")
            if k in os.environ
        }
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        result = run_bounded(
            [sys.executable, "-m", "openjarvis.server.document_worker", str(path)],
            timeout=30,
            env=env,
            max_output_bytes=MAX_TEXT_CHARS * 6 + 4096,
            max_memory_bytes=768 * 1024 * 1024,
        )
    if result.timed_out:
        raise HTTPException(408, "Document parsing timed out")
    if result.truncated:
        raise HTTPException(413, "Extracted document text is too large")
    if result.returncode:
        raise HTTPException(400, "Document parser exceeded its budget or failed")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Invalid document parser response") from exc
    if "status" in payload:
        raise HTTPException(payload["status"], payload["detail"])
    return payload["text"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=IngestResponse)
async def ingest_paste(body: PasteRequest) -> IngestResponse:
    """Ingest pasted text into the knowledge store."""
    text = body.content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Content is empty")

    count = await asyncio.to_thread(
        _store_documents,
        [(text, "paste", body.title or "Pasted text")],
    )
    return IngestResponse(chunks_added=count)


@router.post("/ingest/files", response_model=IngestResponse)
async def ingest_files(
    files: List[UploadFile] = File(...),
    title: Optional[str] = Form(None),
) -> IngestResponse:
    """Ingest uploaded files into the knowledge store."""
    if len(files) > MAX_FILES:
        raise HTTPException(413, f"At most {MAX_FILES} files are allowed")
    if title and len(title) > 512:
        raise HTTPException(400, "Title is too long")
    documents = []
    total_bytes = 0
    total_text = 0

    for upload in files:
        filename = upload.filename or "untitled"
        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()

        if ext not in _ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(_ALLOWED_EXTENSIONS))
            raise HTTPException(
                status_code=400,
                detail=(f"Unsupported file type: {ext}. Allowed: {allowed}"),
            )

        data = await upload.read(MAX_FILE_BYTES + 1)
        total_bytes += len(data)
        if len(data) > MAX_FILE_BYTES or total_bytes > MAX_BATCH_BYTES:
            raise HTTPException(413, "Upload is too large")
        text = await asyncio.to_thread(_parse_upload_bounded, data, ext)
        total_text += len(text)
        if total_text > MAX_TEXT_CHARS:
            raise HTTPException(413, "Extracted document text is too large")

        text = text.strip()
        if not text:
            continue

        documents.append((text, ext.lstrip("."), title or filename))

    total_chunks = await asyncio.to_thread(_store_documents, documents)
    return IngestResponse(chunks_added=total_chunks)


__all__ = [
    "ingest_files",
    "ingest_paste",
    "IngestResponse",
    "PasteRequest",
]

"""Business logic for documents. Every function takes `owner_id` and filters by it —
same tenant-scoping discipline as subjects.service. A document always belongs to a
subject, so every operation first confirms that subject exists and is owned by the
caller (reusing subjects.service — a document can't be more accessible than its subject).
"""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from app.modules.documents.chunking import chunk_text
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.documents.parsing import (
    SUPPORTED_CONTENT_TYPES,
    DocumentParseError,
    extract_text,
)
from app.modules.subjects.service import get_subject

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


class SubjectNotFoundError(Exception):
    """Raised when the given subject doesn't exist or isn't owned by the caller."""


class UnsupportedFileTypeError(Exception):
    """Raised when the upload's content type isn't one StudyMate can parse."""


class FileTooLargeError(Exception):
    """Raised when the upload exceeds MAX_UPLOAD_SIZE_BYTES."""


def _require_owned_subject(session: Session, owner_id: str, subject_id: uuid.UUID) -> None:
    if get_subject(session, owner_id, subject_id) is None:
        raise SubjectNotFoundError(subject_id)


def create_document(
    session: Session,
    owner_id: str,
    subject_id: uuid.UUID,
    filename: str,
    content_type: str,
    raw: bytes,
) -> Document:
    _require_owned_subject(session, owner_id, subject_id)

    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise UnsupportedFileTypeError(f"Unsupported content type: {content_type}")
    if len(raw) > MAX_UPLOAD_SIZE_BYTES:
        raise FileTooLargeError(f"File exceeds {MAX_UPLOAD_SIZE_BYTES} byte limit")

    try:
        text = extract_text(content_type, raw)
        parse_status = DocumentStatus.READY
    except DocumentParseError:
        text = ""
        parse_status = DocumentStatus.FAILED

    document = Document(
        subject_id=subject_id,
        owner_id=owner_id,
        filename=filename,
        content_type=content_type,
        status=parse_status,
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    # chunk_text("") == [] for a failed parse or genuinely empty extraction (e.g. a
    # scanned PDF with no text layer) — no special-casing needed, the loop is just a
    # no-op and the document is still created with its status reflecting the outcome.
    for index, chunk_content in enumerate(chunk_text(text)):
        session.add(
            DocumentChunk(
                document_id=document.id,
                owner_id=owner_id,
                chunk_index=index,
                text=chunk_content,
            )
        )
    session.commit()

    return document


def list_chunks(session: Session, owner_id: str, document_id: uuid.UUID) -> list[DocumentChunk]:
    return list(
        session.exec(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id, DocumentChunk.owner_id == owner_id)
            .order_by(DocumentChunk.chunk_index)
        )
    )


def list_documents(session: Session, owner_id: str, subject_id: uuid.UUID) -> list[Document]:
    _require_owned_subject(session, owner_id, subject_id)
    return list(
        session.exec(
            select(Document).where(Document.subject_id == subject_id, Document.owner_id == owner_id)
        )
    )


def get_document(
    session: Session, owner_id: str, subject_id: uuid.UUID, document_id: uuid.UUID
) -> Document | None:
    return session.exec(
        select(Document).where(
            Document.id == document_id,
            Document.subject_id == subject_id,
            Document.owner_id == owner_id,
        )
    ).first()

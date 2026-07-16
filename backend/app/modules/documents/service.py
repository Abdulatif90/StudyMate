"""Business logic for documents. Every function takes `owner_id` and filters by it —
same tenant-scoping discipline as subjects.service. A document always belongs to a
subject, so every operation first confirms that subject exists and is owned by the
caller (reusing subjects.service — a document can't be more accessible than its subject).
"""

from __future__ import annotations

import logging
import uuid

import inngest
from sqlmodel import Session, delete, select

from app.core import r2_client
from app.core.inngest_client import get_inngest_client, require_event_key
from app.modules.documents.chunking import chunk_text
from app.modules.documents.embedding import EmbeddingError, embed_query, embed_texts
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.documents.parsing import (
    SUPPORTED_CONTENT_TYPES,
    DocumentParseError,
    extract_text,
)
from app.modules.documents.summarization import SummarizationError, summarize_document
from app.modules.subjects.service import get_subject

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

# Emitted by create_document, consumed by the Inngest function in documents.jobs.
DOCUMENT_UPLOADED_EVENT = "document/uploaded"


class SubjectNotFoundError(Exception):
    """Raised when the given subject doesn't exist or isn't owned by the caller."""


class UnsupportedFileTypeError(Exception):
    """Raised when the upload's content type isn't one StudyMate can parse."""


class FileTooLargeError(Exception):
    """Raised when the upload exceeds MAX_UPLOAD_SIZE_BYTES."""


def require_owned_subject(session: Session, owner_id: str, subject_id: uuid.UUID) -> None:
    """Raise `SubjectNotFoundError` unless `subject_id` exists and is owned by
    `owner_id`. Public (not `_`-prefixed): also used by `app.modules.ask.service`,
    which needs the same check before creating/loading a conversation.
    """
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
    """Synchronous, on the request path: validate ownership + the file, upload the
    bytes to R2 under an owner-scoped key, insert a `pending` Document row pointing at
    that object, and return immediately. The heavy work (parse/chunk/embed) happens
    later in `process_document`, triggered by the `document/uploaded` event.

    Size is validated (below) *before* the R2 upload — never upload then reject.
    """
    require_owned_subject(session, owner_id, subject_id)

    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise UnsupportedFileTypeError(f"Unsupported content type: {content_type}")
    if len(raw) > MAX_UPLOAD_SIZE_BYTES:
        raise FileTooLargeError(f"File exceeds {MAX_UPLOAD_SIZE_BYTES} byte limit")

    # Build the row (its id is assigned now, via the model default) so the R2 key can
    # embed it, then upload to R2 *before* committing — if the upload fails, nothing is
    # persisted (no pending row pointing at a missing object). A DB failure after a
    # successful upload is the rarer path and would leave one orphaned R2 object.
    document = Document(
        subject_id=subject_id,
        owner_id=owner_id,
        filename=filename,
        content_type=content_type,
        status=DocumentStatus.PENDING,
    )
    document.r2_object_key = r2_client.build_object_key(owner_id, document.id, filename)
    r2_client.put_object(document.r2_object_key, raw, content_type)

    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def enqueue_document_processing(document: Document) -> None:
    """Emit the `document/uploaded` event so the Inngest job picks the document up.
    Kept separate from `create_document` so the DB insert stays trivially testable
    without Inngest, and so the router can enqueue only after the row is committed.
    """
    require_event_key()
    get_inngest_client().send_sync(
        inngest.Event(
            name=DOCUMENT_UPLOADED_EVENT,
            data={"document_id": str(document.id), "owner_id": document.owner_id},
        )
    )


def get_document_by_id(session: Session, owner_id: str, document_id: uuid.UUID) -> Document | None:
    """Owner-scoped lookup by id alone (no subject_id) — for the async job, which only
    carries the document_id and owner_id in its event payload."""
    return session.exec(
        select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
    ).first()


def delete_document(
    session: Session, owner_id: str, subject_id: uuid.UUID, document_id: uuid.UUID
) -> bool:
    """Delete a document and everything it owns: its `DocumentChunk` rows, its R2
    object, and the `Document` row itself. Returns `False` (router → 404) if the
    document doesn't exist, isn't owned by `owner_id`, or isn't in `subject_id` — same
    owner+subject scoping as `get_document`, so a non-owner can't delete (or even
    detect the existence of) another tenant's document.

    Order, and why: DB rows are deleted and committed *before* the R2 object. If the DB
    delete fails/rolls back, the R2 object is untouched (still consistent — nothing was
    removed that the DB still claims exists). Deleting R2 first would risk the reverse:
    a DB-delete failure after a successful R2 delete would leave a `Document` row
    pointing at a now-missing object. Once the DB delete has committed, there is no
    longer any DB row to "point at" anything, so the R2 delete afterward is best-effort
    and its exceptions are deliberately swallowed (not re-raised) — `delete_object` is
    idempotent, and a transient R2 failure at that point only leaves a harmless
    orphaned object (a storage-cost cleanup debt, not a dangling/broken reference,
    since nothing in the DB references it anymore); it must not turn an
    already-successful document deletion into a 500 for the caller.

    Chunks are deleted (and flushed) *before* the Document row for the same reason
    `ask.service.delete_conversation` flushes before its parent delete: there's no
    ORM-level `relationship()`/cascade in this codebase, so SQLAlchemy won't order the
    deletes for you — without the flush, it can emit `DELETE FROM documents` before
    `DELETE FROM document_chunks` and hit the FK constraint.
    """
    document = get_document(session, owner_id, subject_id, document_id)
    if document is None:
        return False

    session.exec(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    session.flush()
    r2_object_key = document.r2_object_key
    session.delete(document)
    session.commit()

    if r2_object_key is not None:
        try:
            r2_client.delete_object(r2_object_key)
        except Exception:
            # Best-effort — see the "Order, and why" note above. The document is
            # already gone from the DB (the source of truth for the app), so a
            # transient R2 failure here is logged and tolerated, not surfaced as a
            # failed delete.
            logging.getLogger(__name__).warning(
                "Failed to delete R2 object %s for deleted document %s", r2_object_key, document_id
            )

    return True


def process_document(session: Session, owner_id: str, document_id: uuid.UUID) -> Document | None:
    """The async job's work: fetch the file from R2, parse/chunk/embed it, generate an
    auto-summary, and resolve the document to `ready`/`failed`. Returns the document,
    or None if it no longer exists (deleted between upload and processing) — the
    caller treats that as a no-op.

    Idempotent / safe to retry (Inngest retries on unhandled failure): deletes any
    chunks from a previous attempt before re-inserting, so a retried run can't leave
    duplicate DocumentChunk rows regardless of how far the last attempt got. (Inngest
    also memoizes a *successfully* completed step, so a retry-after-success normally
    won't re-invoke this at all — but the delete-then-reinsert makes a direct re-run
    safe too.)

    The R2 object is kept after processing (R2 is the file store now, not a temp
    stash) — it stays available for re-processing and would be cleaned up by a future
    delete-document endpoint.

    A failed parse or embed (`DocumentParseError`/`EmbeddingError`) sets `status:
    failed` with zero chunks — the same invariant the synchronous path guaranteed. A
    missing COHERE_API_KEY (or an R2 fetch failure) raises instead of being caught: an
    infra/deployment problem should fail loudly and let Inngest retry, not masquerade
    as a per-document `failed`.

    Summary generation is a *separate*, best-effort step after a successful
    parse/embed: a `SummarizationError` (or a missing ANTHROPIC_API_KEY, which raises
    loudly instead — same deployment-mistake reasoning as the Cohere key) does not fail
    the document — it still becomes `ready`, just with `summary` left NULL. This
    differs from the parse/embed failure handling above on purpose: the summary is
    secondary, the retrieved/embedded chunks are the actual product.
    """
    document = get_document_by_id(session, owner_id, document_id)
    if document is None or document.r2_object_key is None:
        return document if document is not None else None

    # Clear chunks from any prior attempt (idempotency on retry).
    session.exec(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    session.commit()

    raw = r2_client.get_object(document.r2_object_key)
    try:
        text = extract_text(document.content_type, raw)
        chunks_text = chunk_text(text)
        embeddings = embed_texts(chunks_text)
        parse_status = DocumentStatus.READY
    except (DocumentParseError, EmbeddingError):
        chunks_text = []
        embeddings = []
        parse_status = DocumentStatus.FAILED

    # Empty for a failed parse/embed or genuinely empty extraction (e.g. a scanned PDF
    # with no text layer) — no special-casing needed, the loop is just a no-op.
    # `strict=True` catches a mismatched-length response from Cohere immediately
    # instead of silently pairing the wrong text with the wrong vector.
    for index, (chunk_content, vector) in enumerate(zip(chunks_text, embeddings, strict=True)):
        session.add(
            DocumentChunk(
                document_id=document.id,
                subject_id=document.subject_id,
                owner_id=owner_id,
                chunk_index=index,
                text=chunk_content,
                embedding=vector,
            )
        )

    document.status = parse_status
    # Best-effort: a summarization failure must not fail the whole job — unlike the
    # loud R2-fetch/parse/embed failures above, this is secondary. If parse/embed
    # succeeded the document still becomes `ready`, just with `summary` left NULL.
    document.summary = None
    if parse_status == DocumentStatus.READY:
        try:
            document.summary = summarize_document(text)
        except SummarizationError:
            logging.getLogger(__name__).warning(
                "Failed to generate summary for document %s; leaving summary NULL",
                document_id,
            )

    session.add(document)
    session.commit()
    session.refresh(document)
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
    require_owned_subject(session, owner_id, subject_id)
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


def get_documents_by_ids(
    session: Session, owner_id: str, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Document]:
    """Batched lookup for callers that already have a set of document ids (e.g. the
    Ask endpoint citing sources from search_chunks results) and just need each one's
    metadata (filename, ...) — one query instead of one per document.
    """
    if not document_ids:
        return {}
    documents = session.exec(
        select(Document).where(Document.owner_id == owner_id, Document.id.in_(document_ids))
    ).all()
    return {document.id: document for document in documents}


def search_chunks(
    session: Session,
    owner_id: str,
    subject_id: uuid.UUID,
    query: str,
    top_k: int = 8,
) -> list[tuple[DocumentChunk, float]]:
    """Semantic search over one subject's chunks. Returns (chunk, similarity_score)
    pairs, most similar first — `similarity_score` is `1 - cosine_distance` (higher is
    more similar).

    pgvector's `<=>` cosine-distance operator only exists on Postgres; off it (the
    SQLite test engine), every filter below (owner, subject, embedding IS NOT NULL)
    still applies — enough to unit-test tenant/subject scoping — but similarity
    ordering/scoring is skipped since there's no equivalent to run. Real ranking is
    verified against live Neon instead (see tests/test_search.py).
    """
    require_owned_subject(session, owner_id, subject_id)

    filters = (
        DocumentChunk.owner_id == owner_id,
        DocumentChunk.subject_id == subject_id,
        DocumentChunk.embedding.is_not(None),
    )

    if session.get_bind().dialect.name != "postgresql":
        chunks = session.exec(select(DocumentChunk).where(*filters).limit(top_k)).all()
        return [(chunk, 0.0) for chunk in chunks]

    query_vector = embed_query(query)
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    statement = select(DocumentChunk, distance).where(*filters).order_by(distance).limit(top_k)
    results = session.exec(statement).all()
    return [(chunk, 1 - dist) for chunk, dist in results]

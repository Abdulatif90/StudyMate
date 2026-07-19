"""Business logic for documents. Every function takes `owner_id` and filters by it —
same tenant-scoping discipline as subjects.service. A document always belongs to a
subject, so every operation first confirms that subject exists and is owned by the
caller (reusing subjects.service — a document can't be more accessible than its subject).
"""

from __future__ import annotations

import logging
import uuid

import inngest
import sqlalchemy as sa
from sqlmodel import Session, delete, select

from app.core import r2_client
from app.core.inngest_client import get_inngest_client, require_event_key
from app.core.org import OrgContext
from app.modules.billing.service import ensure_can_upload_document
from app.modules.documents.chunking import chunk_text
from app.modules.documents.embedding import EmbeddingError, embed_query, embed_texts
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus
from app.modules.documents.parsing import (
    SUPPORTED_CONTENT_TYPES,
    DocumentParseError,
    extract_text,
)
from app.modules.documents.rerank import RerankError, rerank
from app.modules.documents.rrf import reciprocal_rank_fusion
from app.modules.documents.summarization import SummarizationError, summarize_document
from app.modules.subjects.service import (
    SubjectNotFoundError,
    SubjectWriteForbiddenError,  # noqa: F401 — re-exported for existing call sites
    get_subject,
    require_readable_subject,
    require_writable_subject,
)
from app.shared.language import DEFAULT_LANGUAGE

# `SubjectNotFoundError` / `SubjectWriteForbiddenError` live in subjects.service now
# (their natural home) but are imported above and thus remain importable from here too,
# so the many existing call sites (`from app.modules.documents.service import
# SubjectNotFoundError`, `service.SubjectNotFoundError`) keep working unchanged.

# The Postgres text-search config the FTS arm queries with — MUST match the config the
# `text_search_vector` generated column was built with (`simple`, see migration
# 066f42dbed80), or lexical matching silently breaks. `simple` does no language-specific
# stemming/stopword removal, right for multilingual material.
_FTS_CONFIG = "simple"

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

# How many vector-similarity candidates search_chunks fetches before handing them to
# Cohere Rerank — wider than top_k on purpose (Rerank's cross-encoder judges relevance
# more accurately than raw cosine order, but only among whatever candidates it's given;
# a pool too close to top_k defeats the point). Bounded, not unlimited: one Rerank call
# per Ask, and cost/latency scale with how many documents are sent to it.
RERANK_CANDIDATE_POOL = 30

# Emitted by create_document, consumed by the Inngest function in documents.jobs.
DOCUMENT_UPLOADED_EVENT = "document/uploaded"


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
    language: str = DEFAULT_LANGUAGE,
    org_ctx: OrgContext | None = None,
) -> Document:
    """Synchronous, on the request path: validate write access + the file, upload the
    bytes to R2 under an owner-scoped key, insert a `pending` Document row pointing at
    that object, and return immediately. The heavy work (parse/chunk/embed) happens
    later in `process_document`, triggered by the `document/uploaded` event.

    **Write authorization** is `require_writable_subject` (the single source of truth):
    the owner of a private subject, or a teacher/admin of the org that owns an org
    subject. A student member of the owning org gets `SubjectWriteForbiddenError` (→
    403) — they can read the material but not add to it — and a caller who can't even
    read the subject gets `SubjectNotFoundError` (→ 404). The new document is owned by
    the uploading `owner_id`.

    `language` (a code from `app.shared.language.SUPPORTED_LANGUAGES`) is captured
    here — the uploader's UI locale at upload time — and stored on the row so the
    later async `process_document` step knows what language to summarize in without
    needing any request context of its own.

    Size is validated (below) *before* the R2 upload — never upload then reject.
    """
    require_writable_subject(session, owner_id, org_ctx or OrgContext(), subject_id)

    # Plan-limit guard before ANY work — specifically before the R2 upload below, so a
    # quota-rejected upload never costs storage or leaves an orphaned object. Raises
    # PlanLimitExceededError (-> 402, handled app-wide in main.py). See billing.service.
    ensure_can_upload_document(session, owner_id, subject_id)

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
        language=language,
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
    session: Session,
    owner_id: str,
    subject_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    commit: bool = True,
) -> bool:
    """Delete a document and everything it owns: its `DocumentChunk` rows, its R2
    object, and the `Document` row itself. Returns `False` (router → 404) if the
    document doesn't exist, isn't owned by `owner_id`, or isn't in `subject_id` — same
    owner+subject scoping as `get_document`, so a non-owner can't delete (or even
    detect the existence of) another tenant's document.

    Order, and why: DB rows are deleted (and, by default, committed) *before* the R2
    object. If the DB delete fails/rolls back, the R2 object is untouched (still
    consistent — nothing was removed that the DB still claims exists). Deleting R2
    first would risk the reverse: a DB-delete failure after a successful R2 delete
    would leave a `Document` row pointing at a now-missing object. The R2 delete
    afterward is best-effort and its exceptions are deliberately swallowed (not
    re-raised) — `delete_object` is idempotent, and a transient R2 failure at that
    point only leaves a harmless orphaned object (a storage-cost cleanup debt, not a
    dangling/broken reference); it must not turn an already-successful document
    deletion into a 500 for the caller.

    `commit=False` (used by `subjects.service.delete_subject`, cascading a whole
    subject's deletion in one transaction): the DB delete is `flush()`ed instead of
    committed, so the caller's own later `commit()`/rollback governs it. The R2 delete
    still happens immediately either way, not deferred — so if the *caller's*
    transaction later rolls back, an already-removed R2 object stays removed even
    though the `Document` row reappears. This is a deliberate, accepted tradeoff (the
    same one a single `commit=True` call already makes, just visible at a larger
    scale): R2 has no transaction to roll back, and re-deriving "was this specific R2
    delete part of a transaction that later rolled back" isn't worth the complexity for
    what remains a storage-cost cleanup debt, not a correctness bug (nothing in the DB
    ever points at a missing object — the surviving `Document` row's `r2_object_key`
    would just point at nothing, same as any other legacy/edge case already tolerated
    here).

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
    if commit:
        session.commit()
    else:
        session.flush()

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
            document.summary = summarize_document(text, document.language)
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


def _stride_sample(texts: list[str], limit: int) -> list[str]:
    """Down-sample `texts` to at most `limit` items by an evenly-spaced stride across the
    whole list — so a sample of an already-ordered corpus (document then chunk position)
    spans multiple documents and sections rather than just the opening of the first one.
    Shared by the owner- and reader-scoped samplers below (DRY — one sampling rule)."""
    if len(texts) <= limit:
        return texts
    step = len(texts) / limit
    return [texts[int(i * step)] for i in range(limit)]


def sample_subject_chunk_texts(
    session: Session, owner_id: str, subject_id: uuid.UUID, limit: int = 30
) -> list[str]:
    """A broad, owner+subject-scoped sample of a subject's chunk *texts* — for
    whole-subject tasks like quiz generation that want representative coverage of the
    material rather than relevance to a specific query (so, unlike `search_chunks`, no
    query and no embedding: this selects only the `text` column, never loading the
    1024-dim vectors, and makes no Cohere call).

    **Owner-scoped** — kept for callers that specifically want the caller's OWN chunks
    (e.g. quiz generation, still owner-only). The READ path (a member generating over a
    teacher's org subject) uses `sample_subject_chunk_texts_for_reader` instead.

    When there are more chunks than `limit`, takes an evenly-spaced stride sample across
    the material (ordered by document then chunk position) so the sample spans multiple
    documents and sections rather than just the opening of the first document.
    """
    require_owned_subject(session, owner_id, subject_id)
    texts = list(
        session.exec(
            select(DocumentChunk.text)
            .where(
                DocumentChunk.owner_id == owner_id,
                DocumentChunk.subject_id == subject_id,
            )
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
    )
    return _stride_sample(texts, limit)


def sample_subject_chunk_texts_for_reader(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    subject_id: uuid.UUID,
    limit: int = 30,
) -> list[str]:
    """Reader-scoped counterpart to `sample_subject_chunk_texts`, for whole-subject
    generation (flashcards) over a subject the caller may READ — including a member
    generating over a teacher's org subject.

    Verifies subject-readability first (`SubjectNotFoundError` → 404 if denied, so
    existence never leaks), then samples chunk texts filtered by `subject_id` ALONE —
    deliberately NOT by `owner_id`, exactly like `search_chunks`: on an org subject the
    chunks belong to the teacher who uploaded the material, so an owner-scoped filter
    would return nothing for a student and break generation entirely. Same evenly-spaced
    stride sample as the owner-scoped variant.
    """
    require_readable_subject(session, caller_id, org_ctx, subject_id)
    texts = list(
        session.exec(
            select(DocumentChunk.text)
            .where(DocumentChunk.subject_id == subject_id)
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
    )
    return _stride_sample(texts, limit)


def list_documents(session: Session, owner_id: str, subject_id: uuid.UUID) -> list[Document]:
    """Owner-scoped list of a subject's documents. KEPT owner-scoped (not readability-
    scoped): used by `subjects.service.delete_subject`'s cascade, which enumerates the
    subject OWNER's own documents. The READ path (a member browsing an org subject) uses
    `list_documents_for_reader` instead."""
    require_owned_subject(session, owner_id, subject_id)
    return list(
        session.exec(
            select(Document).where(Document.subject_id == subject_id, Document.owner_id == owner_id)
        )
    )


def list_documents_for_reader(
    session: Session, caller_id: str, org_ctx: OrgContext, subject_id: uuid.UUID
) -> list[Document]:
    """A subject's documents for anyone who may READ the subject (owner, or a member of
    the org that owns it). Verifies readability first (`SubjectNotFoundError` → 404 if
    denied, so existence never leaks), then fetches ALL of the subject's documents by
    `subject_id` — NOT filtered by owner, since on an org subject a member reads the
    teacher-owned documents."""
    require_readable_subject(session, caller_id, org_ctx, subject_id)
    return list(session.exec(select(Document).where(Document.subject_id == subject_id)))


def get_document(
    session: Session, owner_id: str, subject_id: uuid.UUID, document_id: uuid.UUID
) -> Document | None:
    """Owner-scoped single-document lookup — unchanged. Used internally (e.g.
    `delete_document`) and by callers that specifically want owner scoping. The read
    path uses `get_document_for_reader`."""
    return session.exec(
        select(Document).where(
            Document.id == document_id,
            Document.subject_id == subject_id,
            Document.owner_id == owner_id,
        )
    ).first()


def get_document_for_reader(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    subject_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document | None:
    """One document for anyone who may READ its subject. Verifies subject-readability
    first (raising `SubjectNotFoundError` → 404 if the subject itself is denied), then
    fetches the document by `subject_id`+`document_id` (NOT by owner), so a member reads
    a teacher-owned document. Returns None (→ 404) if no such document is in the
    subject."""
    require_readable_subject(session, caller_id, org_ctx, subject_id)
    return session.exec(
        select(Document).where(
            Document.id == document_id,
            Document.subject_id == subject_id,
        )
    ).first()


def get_documents_by_ids(
    session: Session, subject_id: uuid.UUID, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Document]:
    """Batched lookup for callers that already have a set of document ids (e.g. the
    Ask endpoint citing sources from search_chunks results) and just need each one's
    metadata (filename, ...) — one query instead of one per document.

    Scoped by `subject_id` (NOT owner): the ids come from `search_chunks` over a subject
    the caller was already authorized to read, whose chunks (and thus documents) may be
    owner by a teacher on an org subject. Constraining to the subject keeps the lookup
    from ever returning a document outside the authorized subject.
    """
    if not document_ids:
        return {}
    documents = session.exec(
        select(Document).where(Document.subject_id == subject_id, Document.id.in_(document_ids))
    ).all()
    return {document.id: document for document in documents}


def _rerank_candidates(
    query: str,
    candidates: list[tuple[DocumentChunk, float]],
    top_k: int,
) -> list[tuple[DocumentChunk, float]]:
    """Re-order `candidates` (chunk, vector-similarity-score pairs, already fetched via
    vector search, most-similar-first) using Cohere Rerank, cut down to `top_k`. Pure
    Python over an already-fetched list — no DB/dialect dependency — so this is
    unit-testable directly regardless of whether the caller's DB is Postgres or SQLite.

    On success, the returned score is Cohere's `relevance_score` (the cross-encoder's
    query↔chunk judgment), not the original cosine similarity — it's the more accurate
    signal now that it exists, and it's what actually determined the final order.

    **Graceful degradation, by design**: a `RerankError` must not break Ask — Ask
    already degrades gracefully everywhere else (see `ask/service.py`). On failure,
    this falls back to `candidates` truncated to `top_k` in its original
    vector-similarity order (score = cosine similarity, the pre-rerank meaning) rather
    than raising, exactly like `process_document`'s best-effort summary step.
    """
    if not candidates:
        return []

    texts = [chunk.text for chunk, _score in candidates]
    try:
        ranked = rerank(query, texts, top_n=top_k)
    except RerankError:
        logging.getLogger(__name__).warning(
            "Cohere rerank failed; falling back to vector-similarity order", exc_info=True
        )
        return candidates[:top_k]

    return [(candidates[index][0], relevance_score) for index, relevance_score in ranked]


def search_chunks(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    subject_id: uuid.UUID,
    query: str,
    top_k: int = 8,
) -> list[tuple[DocumentChunk, float]]:
    """Hybrid search over one subject's chunks: a vector-similarity arm and a lexical
    full-text arm, fused with Reciprocal Rank Fusion, then narrowed by Cohere Rerank.
    Returns (chunk, score) pairs, most relevant first, at most `top_k` — see
    `_rerank_candidates` for what `score` means on the reranked vs. fallback path.

    **Access is subject-READABILITY, not chunk ownership.** `require_readable_subject`
    is the single gate (raising `SubjectNotFoundError` → 404 for a caller who may not
    read the subject — including a member of a DIFFERENT org, or one with no active org).
    Once past it, chunks are filtered by `subject_id` ONLY, deliberately NOT by
    `owner_id`: on an org subject the chunks belong to the teacher who uploaded the
    material, so an owner-scoped chunk filter would return nothing for a student and
    break retrieval entirely. The subject gate is what enforces isolation; the chunk
    filter just scopes to the (already-authorized) subject.

    Both `<=>` (pgvector cosine distance) and `@@`/tsvector (full-text) are Postgres-only;
    off it (the SQLite test engine), every filter below still applies — enough to
    unit-test scoping — but both ranking arms are skipped (there's nothing to rank or
    fuse), so it returns the filtered-but-unranked chunks. Real hybrid ranking is
    verified against live Neon instead (see tests/test_search.py).

    Why two arms + RRF (not just vector): the vector arm captures semantic similarity but
    can underweight an *exact* keyword/term match (rare jargon, codes, proper nouns); the
    FTS arm catches those. Their scores are on different scales (cosine distance vs.
    `ts_rank`), so they're fused on rank position via RRF (see rrf.py), not added
    directly. Rerank stays the final, most-accurate stage over the fused pool.
    """
    require_readable_subject(session, caller_id, org_ctx, subject_id)

    filters = (
        DocumentChunk.subject_id == subject_id,
        DocumentChunk.embedding.is_not(None),
    )

    if session.get_bind().dialect.name != "postgresql":
        chunks = session.exec(select(DocumentChunk).where(*filters).limit(top_k)).all()
        return [(chunk, 0.0) for chunk in chunks]

    # Bound each arm (and the fused pool) the same way the single vector arm was bounded
    # before — one Rerank call over a bounded candidate set, regardless of corpus size.
    candidate_limit = max(top_k, RERANK_CANDIDATE_POOL)

    # Arm 1 — vector similarity (pgvector cosine distance).
    query_vector = embed_query(query)
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    vector_rows = session.exec(
        select(DocumentChunk, distance).where(*filters).order_by(distance).limit(candidate_limit)
    ).all()
    vector_ranking = [chunk for chunk, _distance in vector_rows]

    # Arm 2 — lexical full-text search over the GIN-indexed `text_search_vector` column.
    # Carries the SAME subject scoping as the vector arm (`subject_id`, access already
    # gated by require_readable_subject above) — the FTS arm is a place a cross-subject
    # leak could hide, so the filter is not optional here.
    # `websearch_to_tsquery` tolerates arbitrary user input (quotes, "or", ...) without
    # raising on syntax. `_FTS_CONFIG` matches the generated column's config exactly.
    tsvector = sa.literal_column("document_chunks.text_search_vector")
    tsquery = sa.func.websearch_to_tsquery(_FTS_CONFIG, query)
    fts_rank = sa.func.ts_rank(tsvector, tsquery)
    fts_rows = session.exec(
        select(DocumentChunk, fts_rank)
        .where(
            DocumentChunk.subject_id == subject_id,
            tsvector.op("@@")(tsquery),
        )
        .order_by(fts_rank.desc())
        .limit(candidate_limit)
    ).all()
    fts_ranking = [chunk for chunk, _rank in fts_rows]

    # Fuse the two rankings by position (RRF), keep the fused pool bounded, then hand it
    # to the existing Rerank stage. The RRF score rides along so a rerank *failure* falls
    # back to fused order (not just one arm's) — see `_rerank_candidates`.
    by_id = {chunk.id: chunk for chunk in (*vector_ranking, *fts_ranking)}
    fused = reciprocal_rank_fusion(
        [[chunk.id for chunk in vector_ranking], [chunk.id for chunk in fts_ranking]]
    )
    candidates = [(by_id[chunk_id], score) for chunk_id, score in fused[:candidate_limit]]
    return _rerank_candidates(query, candidates, top_k)

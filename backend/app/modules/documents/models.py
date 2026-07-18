"""Document — an uploaded file within a Subject.

`owner_id` mirrors `Subject.owner_id` (same tenant-scoping discipline, enforced again
here rather than relied on transitively through `subject_id`). `status` drives the
async ingest pipeline (Inngest): uploads start `pending`, and a background job
(`documents.jobs`) parses/chunks/embeds and moves them to `ready`/`failed` — see
`service.create_document` (sync, returns `pending`) and `service.process_document`
(the job's work).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlmodel import Column, Field, SQLModel

from app.modules.documents.embedding import EMBEDDING_DIM
from app.shared.language import DEFAULT_LANGUAGE


class DocumentStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


# SQLAlchemy's Enum type defaults to storing each member's *name* ("PENDING"), not its
# *value* ("pending") — values_callable overrides that so the DB column (and any raw
# SQL against it) matches what the Python/JSON side actually uses.
_status_column_type = SAEnum(DocumentStatus, values_callable=lambda cls: [e.value for e in cls])


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    subject_id: uuid.UUID = Field(foreign_key="subjects.id", index=True)
    owner_id: str = Field(index=True)
    filename: str
    content_type: str
    status: DocumentStatus = Field(
        default=DocumentStatus.PENDING, sa_column=Column(_status_column_type, nullable=False)
    )
    # R2 (S3-compatible) object key where the uploaded file's bytes live — set on
    # upload (`service.create_document`), read by the async job
    # (`service.process_document`) to parse/chunk/embed. Owner-scoped
    # (`{owner_id}/{document_id}/{filename}`, see r2_client.build_object_key).
    # Nullable only to tolerate a row that existed before this column; new uploads
    # always set it.
    r2_object_key: str | None = Field(default=None)
    # Auto-generated on successful processing (see service.process_document /
    # summarization.py). Nullable: stays NULL for legacy rows that predate this
    # column, for `failed` documents, and — deliberately — even for a `ready`
    # document whose summarization step itself failed (best-effort, doesn't fail
    # the whole job).
    summary: str | None = Field(default=None)
    # Target language (a code from app.shared.language.SUPPORTED_LANGUAGES) for the
    # auto-summary generated during processing — captured at upload time from the
    # uploader's UI locale (see documents.router.create_document), since
    # process_document runs later, async, with no request context of its own.
    language: str = Field(default=DEFAULT_LANGUAGE)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# pgvector's Vector type only means something on Postgres; SQLite (used by the test
# suite) has no vector type at all. `with_variant` swaps in a plain JSON column for the
# "sqlite" dialect specifically — same rows, same list[float] values, just no actual
# vector search capability, which the test suite never needs (it only exercises
# storage/retrieval, never similarity search). Verified round-tripping correctly
# against both a real SQLite engine and real Neon+pgvector before relying on this.
#
# `none_as_null=True` matters: SQLAlchemy's JSON type otherwise stores a Python `None`
# as the literal text "null" (JSON null), not a real SQL NULL — found by testing
# `embedding IS NOT NULL` against SQLite and getting rows back that should've been
# filtered out. Postgres/pgvector's Vector type doesn't have this quirk at all (a
# `None` there is a real column NULL), so this only needs to be set on the variant.
_embedding_column_type = Vector(EMBEDDING_DIM).with_variant(JSON(none_as_null=True), "sqlite")


class DocumentChunk(SQLModel, table=True):
    """A chunk of a Document's extracted text (see chunking.py). `owner_id` and
    `subject_id` are both duplicated here from `Document` — same defense-in-depth
    reasoning, and it lets retrieval (`service.search_chunks`) filter by owner+subject
    directly on this table, no join needed on the hot query path.
    """

    __tablename__ = "document_chunks"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID = Field(foreign_key="documents.id", index=True)
    subject_id: uuid.UUID = Field(foreign_key="subjects.id", index=True)
    owner_id: str = Field(index=True)
    chunk_index: int
    text: str
    embedding: list[float] | None = Field(default=None, sa_column=Column(_embedding_column_type))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

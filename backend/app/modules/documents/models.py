"""Document — an uploaded file within a Subject.

`owner_id` mirrors `Subject.owner_id` (same tenant-scoping discipline, enforced again
here rather than relied on transitively through `subject_id`). `status` anticipates the
future async ingest pipeline (Inngest): once that exists, uploads will start `pending`
and a background job will move them to `ready`/`failed`. For now (no async pipeline
yet) `service.py` resolves straight to `ready`/`failed` within the same request.
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

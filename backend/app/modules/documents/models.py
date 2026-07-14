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

from sqlalchemy import Enum as SAEnum
from sqlmodel import Column, Field, SQLModel


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


class DocumentChunk(SQLModel, table=True):
    """A chunk of a Document's extracted text (see chunking.py). `owner_id` is
    duplicated here too — same defense-in-depth reasoning as on `Document` itself.
    No embedding column yet; that arrives with Cohere in a later increment.
    """

    __tablename__ = "document_chunks"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID = Field(foreign_key="documents.id", index=True)
    owner_id: str = Field(index=True)
    chunk_index: int
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

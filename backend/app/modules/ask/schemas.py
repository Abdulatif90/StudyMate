"""Request/response shapes for the Ask endpoint."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class SourceChunk(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    text: str
    similarity_score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]

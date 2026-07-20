"""Request/response shapes for the Ask endpoint and conversation history."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.shared.datetime import UtcDatetime


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


class SourceChunk(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    text: str
    # Cohere Rerank's relevance_score when reranking succeeded (see
    # documents.service._rerank_candidates), or raw cosine similarity on the fallback
    # path — both are "higher is more relevant", just not on an identical scale.
    similarity_score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    conversation_id: uuid.UUID


class ConversationRead(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    title: str | None
    created_at: UtcDatetime


class ConversationTurnRead(BaseModel):
    id: uuid.UUID
    question: str
    answer: str
    sources: list[SourceChunk]
    created_at: UtcDatetime


class ConversationWithTurns(ConversationRead):
    turns: list[ConversationTurnRead]

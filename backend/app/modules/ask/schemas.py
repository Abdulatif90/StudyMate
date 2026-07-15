"""Request/response shapes for the Ask endpoint and conversation history."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


class SourceChunk(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    text: str
    similarity_score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    conversation_id: uuid.UUID


class ConversationRead(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    title: str | None
    created_at: datetime


class ConversationTurnRead(BaseModel):
    id: uuid.UUID
    question: str
    answer: str
    sources: list[SourceChunk]
    created_at: datetime


class ConversationWithTurns(ConversationRead):
    turns: list[ConversationTurnRead]

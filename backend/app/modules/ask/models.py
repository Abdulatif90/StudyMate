"""Conversation history for the Ask endpoint. A Conversation belongs to exactly one
Subject (multi-turn chat is scoped to that subject's material); each ConversationTurn
records one question/answer exchange within it, including the sources cited at the
time — stored as JSON rather than re-derived later, since the underlying chunks a
turn cited could change (re-embedded, deleted, ...) after the fact.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    subject_id: uuid.UUID = Field(foreign_key="subjects.id", index=True)
    owner_id: str = Field(index=True)
    title: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConversationTurn(SQLModel, table=True):
    __tablename__ = "conversation_turns"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(foreign_key="conversations.id", index=True)
    owner_id: str = Field(index=True)
    question: str
    answer: str
    sources: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

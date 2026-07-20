"""Telegram account-linking models.

Only a *linked* StudyMate user may talk to the bot (protects our Claude/Tavily budget
from random Telegram users and establishes the owner link). Two tables back that:

- `TelegramLink` — the durable mapping `telegram_chat_id -> owner_id`. The chat id is the
  PRIMARY KEY: one Telegram chat maps to exactly one StudyMate account. Re-linking the same
  chat (a new `/start <code>`) upserts this row rather than creating a second.
- `TelegramLinkCode` — a short-lived, single-use code an authenticated StudyMate user
  generates to prove ownership. The code carries the generating user's `owner_id`, so a
  code can only ever link a chat to the user who created it (cross-tenant safe by
  construction). Consumed (`used=True`) the moment it links a chat; rejected once used or
  expired.

`owner_id` is the Clerk user id (JWT `sub` claim), the same tenant key every other module
scopes by. Following this codebase's plain-FK-column style, there are no ORM
`relationship()`s/cascades between these tables — they're independent rows keyed by
`owner_id`/`code`.

Chat/user ids from Telegram can exceed a 32-bit INTEGER, so `telegram_chat_id` uses
`BigInteger` explicitly (SQLite's INTEGER is already 64-bit, so the test engine is fine).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column
from sqlmodel import Field, SQLModel


class TelegramLink(SQLModel, table=True):
    __tablename__ = "telegram_links"

    # The Telegram chat id IS the primary key — one chat links to exactly one account.
    telegram_chat_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    owner_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TelegramLinkCode(SQLModel, table=True):
    __tablename__ = "telegram_link_codes"

    # The code itself is the primary key: `handle_update` looks a pending link up by the
    # bare `/start <code>` payload, nothing else.
    code: str = Field(primary_key=True)
    # Whom this code links a chat TO. A code made by user A can only ever link to A — the
    # webhook never trusts a client-supplied owner id, only the one stored on the code.
    owner_id: str = Field(index=True)
    # Single-use: flipped True the moment the code links a chat; a used code is rejected.
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

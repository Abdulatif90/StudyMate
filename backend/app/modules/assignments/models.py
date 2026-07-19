"""Assignment — a teacher's broadcast task to their active organization (Phase 5
increment 3a).

A teacher (org admin/teacher) creates an `Assignment` over an org-owned subject; it is
carried on `org_id` (the creator's active org) and is visible to *every* member whose
active org matches — the same org-broadcast shape as an org-owned `Subject`, not the
usual owner-only scope. See `service.py` for the full authorization model and the
deliberate departure from the owner-only reading rule (CLAUDE.md rule 2).

`quiz_id` optionally links the assignment to one of the teacher's quizzes over the same
subject (validated in the service, never relied on transitively).

Plain FK columns, no ORM `relationship()`/cascade — consistent with the rest of the
codebase (Document/Quiz). `owner_id` is the creating teacher, kept alongside `org_id` as
the same defense-in-depth tenant-scoping discipline used everywhere else.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Assignment(SQLModel, table=True):
    __tablename__ = "assignments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # The Clerk org this assignment is broadcast to — the reading scope key. Indexed
    # because listing an org's assignments filters on it on the hot path.
    org_id: str = Field(index=True)
    # The creating teacher (Clerk user id). Indexed; used as the write/delete scope.
    owner_id: str = Field(index=True)
    subject_id: uuid.UUID = Field(foreign_key="subjects.id", index=True)
    # Optional link to one of the teacher's quizzes over the same subject (nullable).
    quiz_id: uuid.UUID | None = Field(default=None, foreign_key="quizzes.id", index=True)
    title: str
    description: str | None = Field(default=None)
    due_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

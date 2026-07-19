"""Request/response shapes for the assignments API — kept separate from
`models.Assignment` so the DB schema is never accidentally exposed over HTTP."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subject_id: uuid.UUID
    description: str | None = Field(default=None, max_length=5000)
    # Optional link to one of the creating teacher's quizzes over `subject_id`. Validated
    # in the service (exists, same subject, owned by the teacher) — a bad id is a 400/404,
    # never a 500.
    quiz_id: uuid.UUID | None = None
    due_at: datetime | None = None


class AssignmentRead(BaseModel):
    id: uuid.UUID
    org_id: str
    # The creating teacher's Clerk user id. Safe to expose to org members (an assignment
    # is a teacher broadcast — who set it is not secret within the org), and the task
    # spec is "all persisted fields". Unlike SubjectRead this is intentionally included.
    owner_id: str
    subject_id: uuid.UUID
    quiz_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    due_at: datetime | None = None
    created_at: datetime

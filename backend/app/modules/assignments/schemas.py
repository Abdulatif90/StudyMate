"""Request/response shapes for the assignments API — kept separate from
`models.Assignment` so the DB schema is never accidentally exposed over HTTP."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.shared.datetime import UtcDatetime


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
    due_at: UtcDatetime | None = None
    created_at: UtcDatetime


class AssignmentSubmissionCreate(BaseModel):
    """A student's self-reported completion payload. Both fields optional — the mere act
    of submitting records completion; `score`/`note` are extras the student may attach.
    Bounded (score 0–100, note length) so a client can't push nonsense values."""

    score: int | None = Field(default=None, ge=0, le=100)
    note: str | None = Field(default=None, max_length=2000)


class AssignmentSubmissionRead(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    # The submitting student's Clerk user id. Exposed so the teacher view can attribute
    # each submission to its student (all persisted fields).
    owner_id: str
    completed_at: UtcDatetime
    score: int | None = None
    note: str | None = None


class RosterMember(BaseModel):
    """One person on an assignment's roster — a Clerk org member, plus whether they've
    submitted and (if so) their score/timestamp. `submitted=False` rows carry no
    score/completed_at; `submitted=True` rows carry the values from their submission."""

    user_id: str
    submitted: bool
    score: int | None = None
    completed_at: UtcDatetime | None = None


class AssignmentRoster(BaseModel):
    """The teacher's roster-diff view: every org member cross-referenced against existing
    submissions, split into who HAS and who HASN'T submitted. Counts are precomputed so a
    client needn't re-derive them. `submitted` may include an ex-member who submitted then
    left the org (they no longer appear in Clerk's member list) — surfaced so their result
    isn't silently dropped; such rows are counted in `submitted_count` but never in
    `total_members` (which reflects current Clerk membership only)."""

    assignment_id: uuid.UUID
    total_members: int
    submitted_count: int
    not_submitted_count: int
    submitted: list[RosterMember]
    not_submitted: list[RosterMember]

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

from sqlmodel import Field, SQLModel, UniqueConstraint


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


class AssignmentSubmission(SQLModel, table=True):
    """A single student's completion record for an org-broadcast `Assignment` (Phase 5
    increment 3b — the "tracks" half of "teacher assigns + tracks").

    Unlike the `Assignment` itself (org-broadcast: read-scoped by `org_id`), a submission
    is **strictly owner-scoped** (CLAUDE.md rule 2): `owner_id` is the STUDENT who acted,
    and each student owns at most one submission per assignment. The presence of a row IS
    the "completed" signal — no `status` column (KISS). The optional `score`/`note` let a
    student attach a self-reported result; there is deliberately NO quiz-attempt linkage
    this increment (auto-grading is a later increment).

    The `(assignment_id, owner_id)` uniqueness is enforced at the DB level (a real
    `UniqueConstraint`), not just a service check, so a re-submit UPSERTs the same row and
    a duplicate can never be written even under a race.

    Plain FK columns, no ORM `relationship()`/cascade — consistent with the rest of the
    codebase. `service.delete_assignment` deletes an assignment's submission rows (all
    students') before the assignment itself, the same flush-before-parent-delete FK
    ordering used everywhere else (there's no ORM cascade to order it for us).
    """

    __tablename__ = "assignment_submissions"
    __table_args__ = (
        # One submission per student per assignment — the upsert in
        # service.submit_assignment relies on this to never create a second row.
        UniqueConstraint(
            "assignment_id", "owner_id", name="uq_assignment_submission_assignment_owner"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    assignment_id: uuid.UUID = Field(foreign_key="assignments.id", index=True)
    # The STUDENT who submitted (Clerk user id) — the owner scope. Indexed because a
    # student reading their own submission filters on it.
    owner_id: str = Field(index=True)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Optional self-reported result the student may attach; no quiz-attempt linkage.
    score: int | None = Field(default=None)
    note: str | None = Field(default=None)

"""Business logic + authorization for assignments (Phase 5 increment 3a).

An `Assignment` is a teacher's task broadcast to their **active organization**. Targeting
is *the whole active org*: the assignment carries `org_id` (the creator's active org) and
every member whose active org matches sees it. We deliberately never enumerate Clerk org
members here — Clerk owns membership, our DB does not — so "who is in the org" is decided
implicitly by each caller's own verified active-org claim, exactly like the org-owned
subject read model (`subjects.service.can_read_subject`).

**Deliberate scoping departure — read this before "fixing" it.** CLAUDE.md rule 2 says
every DB query is filtered by the current *owner*. Assignments break that on purpose for
*reads*: `list_assignments` / `get_assignment` are **org-scoped** (`assignment.org_id ==
caller's active org_id`), NOT owner-scoped — an assignment is a broadcast object, the
same shape already shipped for org-owned subjects. This is intentional, not an oversight.
It still fails **closed**: a caller with **no active org** (`org_ctx.org_id is None`) sees
an **empty list** and cannot read any assignment — a `None == None` match can never leak,
because `org_id` on the row is NOT NULL, so no row's `org_id` is ever `None`.

*Writes* keep the stricter scope: creating requires teacher/admin write access to the
target subject (`require_writable_subject`, which — because a teacher's org subject is
`org_id == active org` — guarantees the assignment targets the teacher's own active org);
deleting is allowed for the creator or any teacher/admin of the assignment's org.

**Out of scope this increment (later increments — do NOT infer them here):** completion /
submission tracking (who did the assignment), per-student targeting, and any frontend.
"""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from app.core.org import OrgContext, is_teacher_role
from app.modules.assignments.models import Assignment
from app.modules.assignments.schemas import AssignmentCreate
from app.modules.quiz.models import Quiz
from app.modules.subjects.service import require_writable_subject


class AssignmentNotFoundError(Exception):
    """Raised when the assignment doesn't exist OR the caller's active org doesn't own it
    (→ 404). Deliberately the SAME error for both so a caller from another org can't tell
    an assignment exists vs. not — the same 404-hides-existence discipline as
    `subjects.service.SubjectNotFoundError`."""


class AssignmentQuizInvalidError(Exception):
    """Raised when a supplied `quiz_id` is not a valid link for this assignment — the quiz
    doesn't exist, belongs to a different subject, or isn't owned by the creating teacher
    (→ 400). Never a 500: a bad linkage is a client error, handled explicitly."""


class AssignmentDeleteForbiddenError(Exception):
    """Raised when the caller may see an assignment (a member of its org) but may not
    delete it — a plain member (student), not its creator and not a teacher/admin of the
    org (→ 403). Distinct from `AssignmentNotFoundError` because the caller already knows
    it exists, so a 403 is honest and leaks nothing."""


def _get_by_id(session: Session, assignment_id: uuid.UUID) -> Assignment | None:
    """Fetch by primary key with NO org filter — for the access-checked lookups below
    only. Never expose directly to a request path; callers must run the result through
    the org check."""
    return session.exec(select(Assignment).where(Assignment.id == assignment_id)).first()


def _validate_quiz_link(
    session: Session, caller_id: str, subject_id: uuid.UUID, quiz_id: uuid.UUID
) -> None:
    """Confirm `quiz_id` is a legitimate link for an assignment over `subject_id` created
    by `caller_id`: the quiz must exist, be over the SAME subject, and be owned by the
    creating teacher (per increment 2b a teacher's quiz over a shared org subject is owned
    by the teacher / subject owner). Anything else → `AssignmentQuizInvalidError`."""
    quiz = session.exec(select(Quiz).where(Quiz.id == quiz_id)).first()
    if quiz is None or quiz.subject_id != subject_id or quiz.owner_id != caller_id:
        raise AssignmentQuizInvalidError(quiz_id)


def create_assignment(
    session: Session, caller_id: str, org_ctx: OrgContext, data: AssignmentCreate
) -> Assignment:
    """Create an assignment broadcast to the caller's active org.

    Authorization is `require_writable_subject` on `data.subject_id`: it raises
    `SubjectNotFoundError` (→ 404) if the caller can't even read the subject and
    `SubjectWriteForbiddenError` (→ 403) if they can read but not write it. A teacher/admin
    writing a subject in their active org passes, and — since such a subject is
    `org_id == active org` — the assignment necessarily targets the teacher's own active
    org (the targeting invariant we want, guaranteed rather than re-checked).

    The router's `require_teacher` guard already 403'd anyone without an active org, so
    `org_ctx.org_id` is a real string here. If `data.quiz_id` is set it must be a valid
    link (`_validate_quiz_link`), else `AssignmentQuizInvalidError` (→ 400).
    """
    require_writable_subject(session, caller_id, org_ctx, data.subject_id)

    if data.quiz_id is not None:
        _validate_quiz_link(session, caller_id, data.subject_id, data.quiz_id)

    assignment = Assignment(
        org_id=org_ctx.org_id,
        owner_id=caller_id,
        subject_id=data.subject_id,
        quiz_id=data.quiz_id,
        title=data.title,
        description=data.description,
        due_at=data.due_at,
    )
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return assignment


def list_assignments(session: Session, org_ctx: OrgContext) -> list[Assignment]:
    """Every assignment broadcast to the caller's active org, newest first.

    **Org-scoped, not owner-scoped** (the documented departure above). No active org →
    empty list (fails closed, never a leak). Ordered `created_at` desc with `id` as a
    stable tie-break so equal-timestamp rows have a deterministic order.
    """
    if org_ctx.org_id is None:
        return []
    return list(
        session.exec(
            select(Assignment)
            .where(Assignment.org_id == org_ctx.org_id)
            .order_by(Assignment.created_at.desc(), Assignment.id)
        ).all()
    )


def get_assignment(
    session: Session, org_ctx: OrgContext, assignment_id: uuid.UUID
) -> Assignment | None:
    """The assignment if it's broadcast to the caller's active org, else None (→ 404). A
    member of another org (or no org) must not learn it exists."""
    assignment = _get_by_id(session, assignment_id)
    if assignment is None or org_ctx.org_id is None or assignment.org_id != org_ctx.org_id:
        return None
    return assignment


def delete_assignment(
    session: Session, caller_id: str, org_ctx: OrgContext, assignment_id: uuid.UUID
) -> bool:
    """Delete an assignment. Allowed for the **creator OR any teacher/admin of the
    assignment's org**; a plain member (student) is forbidden.

    Returns `False` (router → 404) if the assignment doesn't exist or isn't in the
    caller's active org — same 404-hides-existence discipline as the subject model, so a
    wrong-org or nonexistent id is indistinguishable. Raises
    `AssignmentDeleteForbiddenError` (router → 403) when the caller may see it (same org)
    but is neither its creator nor a teacher/admin of the org.
    """
    assignment = _get_by_id(session, assignment_id)
    if assignment is None or org_ctx.org_id is None or assignment.org_id != org_ctx.org_id:
        return False
    if assignment.owner_id != caller_id and not is_teacher_role(org_ctx.org_role):
        raise AssignmentDeleteForbiddenError(assignment_id)
    session.delete(assignment)
    session.commit()
    return True

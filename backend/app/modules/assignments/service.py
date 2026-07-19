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
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlmodel import Session, delete, select

from app.core import clerk_api
from app.core.org import OrgContext, is_teacher_role
from app.modules.assignments.models import Assignment, AssignmentSubmission
from app.modules.assignments.schemas import (
    AssignmentCreate,
    AssignmentRoster,
    AssignmentSubmissionCreate,
    RosterMember,
)
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


class SubmissionViewForbiddenError(Exception):
    """Raised when the caller can READ an assignment (a member of its org) but may not see
    the roster of submissions — the teacher view is teacher/admin-only, so a plain member
    (student) is forbidden (→ 403). Distinct from `AssignmentNotFoundError`: the caller
    already knows the assignment exists (they're in its org), so a 403 is honest here."""


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
    # Delete the assignment's submission rows (every student's) and flush BEFORE the
    # parent assignment — the same flush-before-parent-delete FK ordering the rest of
    # this codebase follows (no ORM cascade to order it for us; deleting the assignment
    # first would violate the submissions' `assignment_id` FK → a loud 500).
    session.exec(
        delete(AssignmentSubmission).where(AssignmentSubmission.assignment_id == assignment_id)
    )
    session.flush()
    session.delete(assignment)
    session.commit()
    return True


def submit_assignment(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    assignment_id: uuid.UUID,
    data: AssignmentSubmissionCreate,
) -> AssignmentSubmission:
    """Mark an assignment complete for the CALLER (records their own owner-scoped
    submission). The primary actor is a student, but a teacher may harmlessly submit too.

    Gate: the caller must be able to READ the assignment (`get_assignment` → it's in their
    active org), else `AssignmentNotFoundError` (→ 404) — a caller from another org (or no
    org) can neither submit nor learn the assignment exists.

    UPSERT on the `(assignment_id, owner_id)` uniqueness: a re-submit updates the caller's
    existing row (`completed_at`/`score`/`note`) rather than inserting a duplicate — the
    operation is idempotent and the DB constraint holds even under a race.
    """
    if get_assignment(session, org_ctx, assignment_id) is None:
        raise AssignmentNotFoundError(assignment_id)

    submission = _upsert_submission(
        session, assignment_id, caller_id, score=data.score, note=data.note
    )
    session.commit()
    session.refresh(submission)
    return submission


def _upsert_submission(
    session: Session,
    assignment_id: uuid.UUID,
    owner_id: str,
    *,
    score: int | None,
    note: str | None,
) -> AssignmentSubmission:
    """Insert-or-update the caller's completion row for one assignment (the single upsert
    path shared by manual `submit_assignment` and quiz-driven `record_quiz_completion`).

    Relies on the `(assignment_id, owner_id)` DB uniqueness: a re-submit updates the same
    row (`completed_at`/`score`/`note`) rather than inserting a duplicate. Does NOT commit
    — the caller controls the transaction boundary (so a caller can upsert several rows in
    one commit). Presence of the row is the "completed" signal; `completed_at` is refreshed
    to now on every update so a re-completion advances the timestamp.
    """
    submission = session.exec(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.owner_id == owner_id,
        )
    ).first()

    if submission is None:
        submission = AssignmentSubmission(
            assignment_id=assignment_id,
            owner_id=owner_id,
            score=score,
            note=note,
        )
        session.add(submission)
    else:
        submission.completed_at = datetime.now(UTC)
        submission.score = score
        submission.note = note
    return submission


def record_quiz_completion(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    quiz_id: uuid.UUID,
    correct: int,
    total: int,
) -> list[AssignmentSubmission]:
    """Auto-complete every assignment in the caller's active org that links `quiz_id`,
    recording the server-graded quiz score (Phase 5 increment 4a).

    Called by the quiz-attempt endpoint AFTER `quiz.service.grade_and_record_attempt` has
    graded the attempt (router-level orchestration — neither service imports the other, so
    no module cycle). For each assignment where `quiz_id == quiz_id` AND `org_id ==
    org_ctx.org_id` (the same active-org scope assignment reads use), UPSERTS the caller's
    `AssignmentSubmission` with `score = correct` and `completed_at = now` (mark complete);
    `note` is set to None (a quiz-driven completion carries no free-text note).

    No linked assignment (or no active org) → a no-op returning `[]`: taking a quiz that
    isn't assigned still records the attempt, it just completes nothing. Fails closed on no
    active org exactly like the assignment reads (an assignment's `org_id` is never NULL, so
    a `None` active org can never match a row).
    """
    if org_ctx.org_id is None:
        return []

    assignments = session.exec(
        select(Assignment).where(Assignment.quiz_id == quiz_id, Assignment.org_id == org_ctx.org_id)
    ).all()
    if not assignments:
        return []

    submissions = [
        _upsert_submission(session, assignment.id, caller_id, score=correct, note=None)
        for assignment in assignments
    ]
    session.commit()
    for submission in submissions:
        session.refresh(submission)
    return submissions


def list_submissions(
    session: Session, caller_id: str, org_ctx: OrgContext, assignment_id: uuid.UUID
) -> list[AssignmentSubmission]:
    """The TEACHER view — every student's submission for one assignment.

    Two gates: the assignment must exist in the caller's active org (`get_assignment` →
    else `AssignmentNotFoundError` → 404, hiding existence from other orgs), AND the caller
    must hold the teacher/admin role (`is_teacher_role`) → else `SubmissionViewForbiddenError`
    (→ 403). Org-safe: the assignment is already confirmed in the caller's org and only a
    teacher of that org reaches the listing, so no cross-org submission can leak.

    **Known limitation (by design):** Clerk owns org membership, our DB does not, so we
    cannot enumerate "all students in the org" — this lists the submissions that EXIST
    (students who acted), NOT a full roster diff of who hasn't submitted. See PROGRESS.md;
    a roster diff needs a Clerk member-list call (a later increment).
    """
    if get_assignment(session, org_ctx, assignment_id) is None:
        raise AssignmentNotFoundError(assignment_id)
    if not is_teacher_role(org_ctx.org_role):
        raise SubmissionViewForbiddenError(assignment_id)
    return list(
        session.exec(
            select(AssignmentSubmission)
            .where(AssignmentSubmission.assignment_id == assignment_id)
            .order_by(AssignmentSubmission.completed_at.desc(), AssignmentSubmission.id)
        ).all()
    )


def get_my_submission(
    session: Session, caller_id: str, org_ctx: OrgContext, assignment_id: uuid.UUID
) -> AssignmentSubmission | None:
    """The caller's OWN submission for an assignment, or `None` if they haven't submitted.

    Gate on assignment readability first (`get_assignment` → else `AssignmentNotFoundError`
    → 404): a caller from another org can't probe. Owner-scoped — only ever returns the
    caller's own row, never another student's.
    """
    if get_assignment(session, org_ctx, assignment_id) is None:
        raise AssignmentNotFoundError(assignment_id)
    return session.exec(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.owner_id == caller_id,
        )
    ).first()


def build_roster_diff(
    member_ids: Iterable[str],
    submissions: Iterable[AssignmentSubmission],
) -> tuple[list[RosterMember], list[RosterMember]]:
    """PURE roster diff: `(submitted, not_submitted)` from a list of org member ids and the
    assignment's existing submissions. No DB, no Clerk, no I/O — the unit-testable core.

    Returns two lists of `RosterMember`:
      - `not_submitted`: current members with NO submission (the "who still owes it" list),
        in `member_ids` order.
      - `submitted`: current members WHO submitted, in `member_ids` order, each carrying
        their `score`/`completed_at`; followed by any **ex-member submitters** — an
        `owner_id` present in `submissions` but absent from `member_ids` (a student who
        submitted then left the org), sorted by `user_id` for determinism so their result
        is surfaced rather than silently dropped (the "handle gracefully" edge).

    A duplicated member id is de-duplicated (first occurrence wins). Multiple submissions
    for one owner shouldn't occur (DB uniqueness), but if they did the last one wins.
    """
    submission_by_owner = {submission.owner_id: submission for submission in submissions}

    submitted: list[RosterMember] = []
    not_submitted: list[RosterMember] = []
    seen_members: set[str] = set()

    for member_id in member_ids:
        if member_id in seen_members:
            continue
        seen_members.add(member_id)
        submission = submission_by_owner.get(member_id)
        if submission is not None:
            submitted.append(
                RosterMember(
                    user_id=member_id,
                    submitted=True,
                    score=submission.score,
                    completed_at=submission.completed_at,
                )
            )
        else:
            not_submitted.append(RosterMember(user_id=member_id, submitted=False))

    # Ex-member submitters: submitted but no longer in the org's member list. Surface them
    # (with their score) so their work isn't lost; sorted for a deterministic response.
    ex_member_ids = sorted(set(submission_by_owner) - seen_members)
    for owner_id in ex_member_ids:
        submission = submission_by_owner[owner_id]
        submitted.append(
            RosterMember(
                user_id=owner_id,
                submitted=True,
                score=submission.score,
                completed_at=submission.completed_at,
            )
        )

    return submitted, not_submitted


def get_submission_roster(
    session: Session, caller_id: str, org_ctx: OrgContext, assignment_id: uuid.UUID
) -> AssignmentRoster:
    """The TEACHER roster-diff view — every org member cross-referenced against who has
    submitted, so the teacher can see WHO HASN'T (which the plain submissions list can't
    show, since it only holds students who acted).

    Same teacher-gate as `list_submissions`: the assignment must exist in the caller's
    active org (`get_assignment` → else `AssignmentNotFoundError` → 404, hiding existence
    from other orgs), AND the caller must hold the teacher/admin role (`is_teacher_role`)
    → else `SubmissionViewForbiddenError` (→ 403). Both gates run BEFORE any Clerk call, so
    a non-teacher or cross-org caller never triggers an outbound request.

    Then the org's members come from Clerk (`clerk_api.list_organization_member_ids` — the
    only place we enumerate membership, since Clerk owns it, not our DB) and the diff is the
    pure `build_roster_diff`. If `CLERK_SECRET_KEY` is unset the Clerk call raises
    `ClerkConfigError`, which the router turns into a clean 503 rather than a 500.

    `org_ctx.org_id` is guaranteed non-None here: `get_assignment` only returns a row when
    `assignment.org_id == org_ctx.org_id` and an assignment's `org_id` is never NULL.
    """
    if get_assignment(session, org_ctx, assignment_id) is None:
        raise AssignmentNotFoundError(assignment_id)
    if not is_teacher_role(org_ctx.org_role):
        raise SubmissionViewForbiddenError(assignment_id)

    member_ids = clerk_api.list_organization_member_ids(org_ctx.org_id)
    submissions = session.exec(
        select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == assignment_id)
    ).all()

    submitted, not_submitted = build_roster_diff(member_ids, submissions)
    return AssignmentRoster(
        assignment_id=assignment_id,
        total_members=len(set(member_ids)),
        submitted_count=len(submitted),
        not_submitted_count=len(not_submitted),
        submitted=submitted,
        not_submitted=not_submitted,
    )

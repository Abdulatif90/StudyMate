"""Assignments HTTP routes — thin: auth/DB wiring + error→HTTP translation only. All
business logic (authorization, org-scoping, quiz-link validation) lives in `service.py`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core import clerk_api
from app.core.auth import get_current_user_id, get_org_context, require_teacher
from app.core.db import get_session
from app.core.org import OrgContext
from app.modules.assignments import service
from app.modules.assignments.models import Assignment, AssignmentSubmission
from app.modules.assignments.schemas import (
    AssignmentCreate,
    AssignmentRead,
    AssignmentRoster,
    AssignmentSubmissionCreate,
    AssignmentSubmissionRead,
)
from app.modules.subjects.service import SubjectNotFoundError, SubjectWriteForbiddenError

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def create_assignment(
    data: AssignmentCreate,
    session: Session = Depends(get_session),
    caller_id: str = Depends(get_current_user_id),
    # require_teacher 403s anyone without an active teacher/admin org — the create guard.
    org_ctx: OrgContext = Depends(require_teacher),
) -> Assignment:
    try:
        return service.create_assignment(session, caller_id, org_ctx, data)
    except SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc
    except SubjectWriteForbiddenError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You don't have permission to assign over this subject"
        ) from exc
    except service.AssignmentQuizInvalidError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Quiz is not a valid link for this assignment"
        ) from exc


@router.get("", response_model=list[AssignmentRead])
def list_assignments(
    session: Session = Depends(get_session),
    _caller_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[Assignment]:
    # Org-broadcast read: the active org's assignments (empty if no active org).
    return service.list_assignments(session, org_ctx)


@router.get("/{assignment_id}", response_model=AssignmentRead)
def get_assignment(
    assignment_id: uuid.UUID,
    session: Session = Depends(get_session),
    _caller_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> Assignment:
    assignment = service.get_assignment(session, org_ctx, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    return assignment


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: uuid.UUID,
    session: Session = Depends(get_session),
    caller_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> None:
    try:
        deleted = service.delete_assignment(session, caller_id, org_ctx, assignment_id)
    except service.AssignmentDeleteForbiddenError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You don't have permission to delete this assignment"
        ) from exc
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")


@router.post(
    "/{assignment_id}/submit",
    response_model=AssignmentSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_assignment(
    assignment_id: uuid.UUID,
    data: AssignmentSubmissionCreate,
    session: Session = Depends(get_session),
    caller_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> AssignmentSubmission:
    # Student marks the assignment complete (idempotent upsert of their own submission).
    try:
        return service.submit_assignment(session, caller_id, org_ctx, assignment_id, data)
    except service.AssignmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found") from exc


@router.get("/{assignment_id}/submissions", response_model=list[AssignmentSubmissionRead])
def list_submissions(
    assignment_id: uuid.UUID,
    session: Session = Depends(get_session),
    caller_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[AssignmentSubmission]:
    # Teacher view: every student's submission for this assignment. 404 if not in the
    # caller's org (hides existence); 403 if the caller is a plain member, not a teacher.
    try:
        return service.list_submissions(session, caller_id, org_ctx, assignment_id)
    except service.AssignmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found") from exc
    except service.SubmissionViewForbiddenError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You don't have permission to view these submissions"
        ) from exc


@router.get("/{assignment_id}/roster", response_model=AssignmentRoster)
def get_submission_roster(
    assignment_id: uuid.UUID,
    session: Session = Depends(get_session),
    caller_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> AssignmentRoster:
    # Teacher roster diff: every org member vs. who has submitted (so the teacher sees who
    # HASN'T). 404 if not in the caller's org; 403 if the caller is a plain member. The
    # member list comes from Clerk's Backend API — env-gated: if CLERK_SECRET_KEY is unset
    # we surface a clean 503 (feature unavailable), and an upstream Clerk failure is a 502,
    # so neither leaks as a 500.
    try:
        return service.get_submission_roster(session, caller_id, org_ctx, assignment_id)
    except service.AssignmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found") from exc
    except service.SubmissionViewForbiddenError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You don't have permission to view this roster"
        ) from exc
    except clerk_api.ClerkConfigError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Roster unavailable — Clerk is not configured on the server",
        ) from exc
    except clerk_api.ClerkAPIError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Roster unavailable — could not reach Clerk"
        ) from exc


@router.get("/{assignment_id}/my-submission", response_model=AssignmentSubmissionRead)
def get_my_submission(
    assignment_id: uuid.UUID,
    session: Session = Depends(get_session),
    caller_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> AssignmentSubmission:
    # The caller's own submission, or 404 if they haven't submitted (or can't read it).
    try:
        submission = service.get_my_submission(session, caller_id, org_ctx, assignment_id)
    except service.AssignmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found") from exc
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No submission found")
    return submission

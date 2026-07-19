"""Assignments HTTP routes — thin: auth/DB wiring + error→HTTP translation only. All
business logic (authorization, org-scoping, quiz-link validation) lives in `service.py`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth import get_current_user_id, get_org_context, require_teacher
from app.core.db import get_session
from app.core.org import OrgContext
from app.modules.assignments import service
from app.modules.assignments.models import Assignment
from app.modules.assignments.schemas import AssignmentCreate, AssignmentRead
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

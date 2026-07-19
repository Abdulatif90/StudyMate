"""Subjects HTTP routes — thin: auth/DB wiring only, no business logic (that's service.py)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth import get_current_user_id, get_org_context
from app.core.db import get_session
from app.core.org import OrgContext
from app.modules.subjects import service
from app.modules.subjects.models import Subject
from app.modules.subjects.schemas import SubjectCreate, SubjectRead

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.post("", response_model=SubjectRead, status_code=status.HTTP_201_CREATED)
def create_subject(
    data: SubjectCreate,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> Subject:
    # A teacher/admin acting inside an active org publishes org-owned (read-shared)
    # subjects; everyone else creates private ones — the rule lives in the service.
    return service.create_subject(session, owner_id, data, org_ctx=org_ctx)


@router.get("", response_model=list[SubjectRead])
def list_subjects(
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[Subject]:
    # Own subjects + the active org's shared subjects (deduped). No active org → only own.
    return service.list_subjects(session, owner_id, org_ctx.org_id)


@router.get("/{subject_id}", response_model=SubjectRead)
def get_subject(
    subject_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> Subject:
    subject = service.get_readable_subject(session, owner_id, org_ctx, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")
    return subject


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(
    subject_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> None:
    try:
        deleted = service.delete_subject(session, owner_id, org_ctx, subject_id)
    except service.SubjectWriteForbiddenError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You don't have permission to delete this subject"
        ) from exc
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")

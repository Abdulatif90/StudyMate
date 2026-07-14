"""Subjects HTTP routes — thin: auth/DB wiring only, no business logic (that's service.py)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.subjects import service
from app.modules.subjects.models import Subject
from app.modules.subjects.schemas import SubjectCreate, SubjectRead

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.post("", response_model=SubjectRead, status_code=status.HTTP_201_CREATED)
def create_subject(
    data: SubjectCreate,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> Subject:
    return service.create_subject(session, owner_id, data)


@router.get("", response_model=list[SubjectRead])
def list_subjects(
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> list[Subject]:
    return service.list_subjects(session, owner_id)


@router.get("/{subject_id}", response_model=SubjectRead)
def get_subject(
    subject_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> Subject:
    subject = service.get_subject(session, owner_id, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")
    return subject


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(
    subject_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> None:
    if not service.delete_subject(session, owner_id, subject_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")

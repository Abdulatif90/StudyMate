"""Progress HTTP routes — thin: auth/DB wiring + exception-to-status translation only
(all business logic lives in service.py), mirroring the other routers. Two routers,
same reasoning as `ask.router`'s `router`/`conversations_router` split: `router` is
subject-scoped (per-subject rollup, needs `subject_id` in the URL); `overall_router` is
flat and owner-scoped only (aggregates across every subject the caller owns).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.documents.service import SubjectNotFoundError
from app.modules.progress import service
from app.modules.progress.schemas import OverallProgress, SubjectProgress

router = APIRouter(prefix="/subjects/{subject_id}/progress", tags=["progress"])
overall_router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("", response_model=SubjectProgress)
def get_subject_progress(
    subject_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> SubjectProgress:
    try:
        return service.get_subject_progress(session, owner_id, subject_id)
    except SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc


@overall_router.get("", response_model=OverallProgress)
def get_overall_progress(
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> OverallProgress:
    return service.get_overall_progress(session, owner_id)

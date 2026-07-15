"""Ask HTTP route — thin: auth/DB wiring + exception-to-status translation only
(all business logic, including graceful degradation, lives in service.py)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.ask import service
from app.modules.ask.schemas import AskRequest, AskResponse
from app.modules.documents.service import SubjectNotFoundError

router = APIRouter(prefix="/subjects/{subject_id}/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
def ask_question(
    subject_id: uuid.UUID,
    data: AskRequest,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> AskResponse:
    try:
        return service.ask_question(session, owner_id, subject_id, data.question)
    except SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc

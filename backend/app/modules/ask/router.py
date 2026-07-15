"""Ask + conversation-history HTTP routes — thin: auth/DB wiring + exception-to-status
translation only (all business logic, including graceful degradation, lives in
service.py). Two routers here since they have different path prefixes: `router` for
the subject-scoped ask endpoint, `conversations_router` for the owner-scoped
conversation listing/detail/delete endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.ask import service
from app.modules.ask.schemas import (
    AskRequest,
    AskResponse,
    ConversationRead,
    ConversationTurnRead,
    ConversationWithTurns,
)
from app.modules.documents.service import SubjectNotFoundError

router = APIRouter(prefix="/subjects/{subject_id}/ask", tags=["ask"])
conversations_router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=AskResponse)
def ask_question(
    subject_id: uuid.UUID,
    data: AskRequest,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> AskResponse:
    try:
        return service.ask_question(
            session, owner_id, subject_id, data.question, conversation_id=data.conversation_id
        )
    except SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc
    except service.ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found") from exc


@conversations_router.get("", response_model=list[ConversationRead])
def list_conversations(
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
):
    return service.list_conversations(session, owner_id)


@conversations_router.get("/{conversation_id}", response_model=ConversationWithTurns)
def get_conversation(
    conversation_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> ConversationWithTurns:
    conversation = service.get_conversation(session, owner_id, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    turns = service.list_turns(session, owner_id, conversation_id)
    return ConversationWithTurns(
        id=conversation.id,
        subject_id=conversation.subject_id,
        title=conversation.title,
        created_at=conversation.created_at,
        turns=[
            ConversationTurnRead(
                id=turn.id,
                question=turn.question,
                answer=turn.answer,
                sources=turn.sources,
                created_at=turn.created_at,
            )
            for turn in turns
        ],
    )


@conversations_router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> None:
    if not service.delete_conversation(session, owner_id, conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

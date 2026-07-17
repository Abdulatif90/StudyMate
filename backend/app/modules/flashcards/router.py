"""Flashcards HTTP routes — thin: auth/DB wiring + exception-to-status translation only
(all business logic lives in service.py), mirroring the quiz/documents routers.

Two routers, same reasoning as `ask.router`'s `router`/`conversations_router` split:
`router` is subject-scoped (generate/list/due — operations that need `subject_id` in
the URL to know which subject's material to draw on or which subject's cards to list);
`flashcards_router` is flat, owner-scoped-by-id-alone (review/delete — a flashcard's id
is already unique and unguessable, so neither operation needs `subject_id` in its URL).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.documents.service import SubjectNotFoundError
from app.modules.flashcards import service
from app.modules.flashcards.generation import FlashcardGenerationError
from app.modules.flashcards.schemas import FlashcardGenerateRequest, FlashcardRead, ReviewRequest

router = APIRouter(prefix="/subjects/{subject_id}/flashcards", tags=["flashcards"])
flashcards_router = APIRouter(prefix="/flashcards", tags=["flashcards"])


def _to_read(flashcard) -> FlashcardRead:
    return FlashcardRead(
        id=flashcard.id,
        subject_id=flashcard.subject_id,
        front=flashcard.front,
        back=flashcard.back,
        repetitions=flashcard.repetitions,
        ease_factor=flashcard.ease_factor,
        interval_days=flashcard.interval_days,
        due_at=flashcard.due_at,
        last_reviewed_at=flashcard.last_reviewed_at,
        created_at=flashcard.created_at,
    )


@router.post("", response_model=list[FlashcardRead], status_code=status.HTTP_201_CREATED)
def generate_flashcards(
    subject_id: uuid.UUID,
    data: FlashcardGenerateRequest,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> list[FlashcardRead]:
    try:
        flashcards = service.generate_flashcards(
            session, owner_id, subject_id, num_cards=data.num_cards
        )
    except SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc
    except service.NoFlashcardMaterialError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "This subject has no processed material to generate flashcards from yet.",
        ) from exc
    except FlashcardGenerationError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Couldn't generate flashcards right now. Please try again.",
        ) from exc

    return [_to_read(flashcard) for flashcard in flashcards]


@router.get("", response_model=list[FlashcardRead])
def list_flashcards(
    subject_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> list[FlashcardRead]:
    try:
        flashcards = service.list_flashcards(session, owner_id, subject_id)
    except SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc
    return [_to_read(flashcard) for flashcard in flashcards]


@router.get("/due", response_model=list[FlashcardRead])
def list_due_flashcards(
    subject_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> list[FlashcardRead]:
    try:
        flashcards = service.list_due_flashcards(session, owner_id, subject_id)
    except SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc
    return [_to_read(flashcard) for flashcard in flashcards]


@flashcards_router.post("/{flashcard_id}/review", response_model=FlashcardRead)
def review_flashcard(
    flashcard_id: uuid.UUID,
    data: ReviewRequest,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> FlashcardRead:
    try:
        flashcard = service.review_flashcard(session, owner_id, flashcard_id, grade=data.grade)
    except service.InvalidGradeError as exc:
        # Defense-in-depth only — ReviewRequest.grade's ge/le already rejects an
        # out-of-range grade before this line, so this path shouldn't be reachable
        # over HTTP, but it's mapped anyway rather than surfacing as a 500.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if flashcard is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Flashcard not found")
    return _to_read(flashcard)


@flashcards_router.delete("/{flashcard_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flashcard(
    flashcard_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> None:
    if not service.delete_flashcard(session, owner_id, flashcard_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Flashcard not found")

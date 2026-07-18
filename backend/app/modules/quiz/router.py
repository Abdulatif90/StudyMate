"""Quiz HTTP routes — thin: auth/DB wiring + exception-to-status translation only
(all business logic lives in service.py), mirroring the documents/ask routers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.documents.service import SubjectNotFoundError
from app.modules.quiz import service
from app.modules.quiz.generation import QuizGenerationError
from app.modules.quiz.schemas import (
    QuizGenerateRequest,
    QuizQuestionRead,
    QuizRead,
    QuizWithQuestions,
)

router = APIRouter(prefix="/subjects/{subject_id}/quizzes", tags=["quizzes"])


def _to_with_questions(quiz, questions) -> QuizWithQuestions:
    return QuizWithQuestions(
        id=quiz.id,
        subject_id=quiz.subject_id,
        title=quiz.title,
        created_at=quiz.created_at,
        questions=[
            QuizQuestionRead(
                id=question.id,
                question=question.question,
                options=question.options,
                correct_index=question.correct_index,
                explanation=question.explanation,
                order=question.order,
            )
            for question in questions
        ],
    )


@router.post("", response_model=QuizWithQuestions, status_code=status.HTTP_201_CREATED)
def generate_quiz(
    subject_id: uuid.UUID,
    data: QuizGenerateRequest,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> QuizWithQuestions:
    try:
        quiz = service.generate_quiz(
            session,
            owner_id,
            subject_id,
            num_questions=data.num_questions,
            title=data.title,
            language=data.language,
        )
    except SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc
    except service.NoQuizMaterialError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "This subject has no processed material to build a quiz from yet.",
        ) from exc
    except QuizGenerationError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Couldn't generate a quiz right now. Please try again."
        ) from exc

    questions = service.list_questions(session, owner_id, quiz.id)
    return _to_with_questions(quiz, questions)


@router.get("", response_model=list[QuizRead])
def list_quizzes(
    subject_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> list:
    try:
        return service.list_quizzes(session, owner_id, subject_id)
    except SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc


@router.get("/{quiz_id}", response_model=QuizWithQuestions)
def get_quiz(
    subject_id: uuid.UUID,
    quiz_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> QuizWithQuestions:
    quiz = service.get_quiz(session, owner_id, subject_id, quiz_id)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    questions = service.list_questions(session, owner_id, quiz_id)
    return _to_with_questions(quiz, questions)


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(
    subject_id: uuid.UUID,
    quiz_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> None:
    if not service.delete_quiz(session, owner_id, subject_id, quiz_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")

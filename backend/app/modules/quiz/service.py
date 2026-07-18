"""Business logic for quizzes. Every function takes `owner_id` and filters by it —
same tenant-scoping discipline as the rest of this codebase. A quiz always belongs to a
subject, so mutating/creating operations first confirm that subject exists and is owned
by the caller (reusing `documents.service.require_owned_subject`, exactly as
`ask.service` does — a quiz can't be more accessible than its subject).
"""

from __future__ import annotations

import logging
import uuid

from sqlmodel import Session, select

from app.modules.billing.models import GenerationKind
from app.modules.billing.service import ensure_can_generate, record_generation
from app.modules.documents.service import require_owned_subject, sample_subject_chunk_texts
from app.modules.quiz.generation import generate_quiz_questions
from app.modules.quiz.models import Quiz, QuizQuestion
from app.shared.language import DEFAULT_LANGUAGE

# How many chunk excerpts to sample from the subject as material for one quiz — bounded
# so the generation prompt (and its cost/latency) stays predictable regardless of how
# large the subject's corpus is.
QUIZ_CHUNK_SAMPLE = 30


class NoQuizMaterialError(Exception):
    """Raised when a subject has no chunks to build a quiz from (nothing uploaded yet,
    or nothing has finished processing) — a client-actionable condition, distinct from
    an upstream model failure."""


def generate_quiz(
    session: Session,
    owner_id: str,
    subject_id: uuid.UUID,
    num_questions: int,
    title: str | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> Quiz:
    """Generate and persist a quiz for `subject_id`: verify ownership, sample the
    subject's material, generate questions via Claude tool-use, and store the `Quiz` +
    its `QuizQuestion` rows in one transaction.

    Raises `SubjectNotFoundError` (unowned/missing subject), `NoQuizMaterialError` (no
    chunks to draw on), or `QuizGenerationError` (Claude failed / returned a malformed
    quiz) — all translated to HTTP status by the router. Nothing is persisted unless
    generation fully succeeds (the `Quiz` row is only added after questions come back).
    """
    excerpts = sample_subject_chunk_texts(
        session, owner_id, subject_id, limit=QUIZ_CHUNK_SAMPLE
    )  # raises SubjectNotFoundError if unowned/missing
    if not excerpts:
        raise NoQuizMaterialError(subject_id)

    # Daily-generation guard BEFORE the Claude call below, so a quota-rejected request
    # never spends a billable API call. Raises PlanLimitExceededError (-> 402, handled
    # app-wide in main.py). See billing.service for the check/record ordering contract.
    ensure_can_generate(session, owner_id)

    # generate_quiz_questions returns questions whose correct_index is already validated
    # to be within options range (see generation._parse_questions) — no out-of-range
    # index can reach the DB to break a future grading flow.
    questions = generate_quiz_questions(excerpts, num_questions, language)

    quiz = Quiz(subject_id=subject_id, owner_id=owner_id, title=title)
    session.add(quiz)
    session.flush()  # assign quiz.id before it's referenced by the question rows
    for order, question in enumerate(questions):
        session.add(
            QuizQuestion(
                quiz_id=quiz.id,
                owner_id=owner_id,
                question=question.question,
                options=question.options,
                correct_index=question.correct_index,
                explanation=question.explanation,
                order=order,
            )
        )
    # Count this generation against today's allowance — staged on the same session, so
    # the commit below persists the counter and the quiz atomically (neither can land
    # without the other). Only after generation succeeded: a failed Claude call above
    # raised and never reached here, so it doesn't burn the user's quota.
    record_generation(session, owner_id, GenerationKind.QUIZ)
    session.commit()
    session.refresh(quiz)
    logging.getLogger(__name__).info(
        "Generated quiz %s (%d questions) for subject %s", quiz.id, len(questions), subject_id
    )
    return quiz


def list_quizzes(session: Session, owner_id: str, subject_id: uuid.UUID) -> list[Quiz]:
    require_owned_subject(session, owner_id, subject_id)
    return list(
        session.exec(
            select(Quiz)
            .where(Quiz.subject_id == subject_id, Quiz.owner_id == owner_id)
            .order_by(Quiz.created_at.desc())
        )
    )


def get_quiz(
    session: Session, owner_id: str, subject_id: uuid.UUID, quiz_id: uuid.UUID
) -> Quiz | None:
    """Owner+subject-scoped lookup — a quiz from a different subject (or another owner)
    is a 404, not a silent cross-subject read."""
    return session.exec(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.subject_id == subject_id,
            Quiz.owner_id == owner_id,
        )
    ).first()


def list_questions(session: Session, owner_id: str, quiz_id: uuid.UUID) -> list[QuizQuestion]:
    return list(
        session.exec(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id, QuizQuestion.owner_id == owner_id)
            .order_by(QuizQuestion.order)
        )
    )


def delete_quiz(
    session: Session,
    owner_id: str,
    subject_id: uuid.UUID,
    quiz_id: uuid.UUID,
    *,
    commit: bool = True,
) -> bool:
    """Delete a quiz and its questions. Returns `False` (router → 404) when the quiz
    doesn't exist, isn't owned by `owner_id`, or isn't in `subject_id` — same
    owner+subject scoping as `get_quiz`.

    Questions are deleted and **flushed** before the `Quiz` row: there's no ORM-level
    `relationship()`/cascade in this codebase, so SQLAlchemy won't order the deletes for
    you — without the flush it can emit `DELETE FROM quizzes` before `DELETE FROM
    quiz_questions` and hit the FK constraint. This is the same flush-before-parent rule
    that surfaced as a real bug in `delete_conversation`/`delete_document` before.

    `commit=False` (used by `subjects.service.delete_subject`, cascading a whole
    subject's deletion in one transaction): flushes instead of committing, so the
    caller's own commit/rollback governs this delete too.
    """
    quiz = get_quiz(session, owner_id, subject_id, quiz_id)
    if quiz is None:
        return False

    for question in list_questions(session, owner_id, quiz_id):
        session.delete(question)
    session.flush()
    session.delete(quiz)
    if commit:
        session.commit()
    else:
        session.flush()
    return True

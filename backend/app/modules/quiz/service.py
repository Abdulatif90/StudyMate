"""Business logic for quizzes.

Two access shapes, matching the org-sharing model the rest of the codebase uses (single
source of truth: `subjects.service`'s `can_read_subject` / `require_readable_subject`):

- **Read / generate** (generate, list, get, list questions) are subject-READABILITY-
  scoped: the owner of a private subject, or any member whose active org owns the
  subject, may generate/read. A member generating over a teacher's org subject gets a
  quiz **owned by the caller** (per-student, like conversations and the flashcard side) —
  the shared thing is the source material, not the derived quiz.
- **Delete** is OWNER-only (a student can't delete a teacher's shared quiz).

Crucially, subject-readability alone is NOT enough for the read path: a non-owner reader
sees only the SUBJECT OWNER's quizzes plus their OWN — never another student's private
quiz on the same shared subject (their quizzes stay `owner_id`-scoped). The reader
variants below enforce `quiz.owner_id in {caller_id, subject.owner_id}`, mirroring the
flashcard `_reader_owner_filter` and its review-path fix.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.org import OrgContext
from app.modules.billing.models import GenerationKind
from app.modules.billing.service import ensure_can_generate, record_generation
from app.modules.documents.service import (
    require_owned_subject,
    sample_subject_chunk_texts_for_reader,
)
from app.modules.quiz.generation import generate_quiz_questions
from app.modules.quiz.models import Quiz, QuizAttempt, QuizQuestion
from app.modules.quiz.schemas import QuizAttemptResult
from app.modules.subjects.models import Subject
from app.modules.subjects.service import get_readable_subject, require_readable_subject
from app.shared.language import DEFAULT_LANGUAGE

# How many chunk excerpts to sample from the subject as material for one quiz — bounded
# so the generation prompt (and its cost/latency) stays predictable regardless of how
# large the subject's corpus is.
QUIZ_CHUNK_SAMPLE = 30


class NoQuizMaterialError(Exception):
    """Raised when a subject has no chunks to build a quiz from (nothing uploaded yet,
    or nothing has finished processing) — a client-actionable condition, distinct from
    an upstream model failure."""


class QuizNotFoundError(Exception):
    """Raised when a quiz doesn't exist OR the caller can't read it (→ 404). Deliberately
    the SAME error for both so a caller can't tell a quiz exists vs. not — the same
    404-hides-existence discipline as `get_quiz_for_reader` (which returns None for both
    "missing" and "not in the shared set")."""


def generate_quiz(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    subject_id: uuid.UUID,
    num_questions: int,
    title: str | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> Quiz:
    """Generate and persist a quiz for `subject_id`: verify the caller may READ the
    subject, sample its material, generate questions via Claude tool-use, and store the
    `Quiz` + its `QuizQuestion` rows (owned by the caller) in one transaction. A member
    generating over a teacher's org subject gets their OWN quiz (`owner_id = caller_id`),
    exactly like conversations and the flashcard side.

    Raises `SubjectNotFoundError` (subject missing or not readable by the caller),
    `NoQuizMaterialError` (no chunks to draw on), or `QuizGenerationError` (Claude failed
    / returned a malformed quiz) — all translated to HTTP status by the router. Nothing
    is persisted unless generation fully succeeds (the `Quiz` row is only added after
    questions come back).
    """
    excerpts = sample_subject_chunk_texts_for_reader(
        session, caller_id, org_ctx, subject_id, limit=QUIZ_CHUNK_SAMPLE
    )  # raises SubjectNotFoundError if the caller may not read the subject
    if not excerpts:
        raise NoQuizMaterialError(subject_id)

    # Daily-generation guard BEFORE the Claude call below, so a quota-rejected request
    # never spends a billable API call. Raises PlanLimitExceededError (-> 402, handled
    # app-wide in main.py). See billing.service for the check/record ordering contract.
    ensure_can_generate(session, caller_id, org_ctx=org_ctx)

    # generate_quiz_questions returns questions whose correct_index is already validated
    # to be within options range (see generation._parse_questions) — no out-of-range
    # index can reach the DB to break a future grading flow.
    questions = generate_quiz_questions(excerpts, num_questions, language)

    quiz = Quiz(subject_id=subject_id, owner_id=caller_id, title=title)
    session.add(quiz)
    session.flush()  # assign quiz.id before it's referenced by the question rows
    for order, question in enumerate(questions):
        session.add(
            QuizQuestion(
                quiz_id=quiz.id,
                owner_id=caller_id,
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
    record_generation(session, caller_id, GenerationKind.QUIZ)
    session.commit()
    session.refresh(quiz)
    logging.getLogger(__name__).info(
        "Generated quiz %s (%d questions) for subject %s", quiz.id, len(questions), subject_id
    )
    return quiz


def _reader_owner_filter(caller_id: str, subject: Subject):
    """The `Quiz.owner_id` filter for what a reader sees on `subject`: always their OWN
    quizzes; PLUS, when they are not the subject owner, the subject OWNER's quizzes (the
    shared set). Deliberately never another student's private quiz — only the owner's
    quizzes are shared. Mirrors `flashcards.service._reader_owner_filter`."""
    own = Quiz.owner_id == caller_id
    if subject.owner_id == caller_id:
        return own
    return own | (Quiz.owner_id == subject.owner_id)


def list_quizzes(session: Session, owner_id: str, subject_id: uuid.UUID) -> list[Quiz]:
    """Owner-scoped list of a subject's quizzes. KEPT owner-scoped (not readability-
    scoped): used by `subjects.service.delete_subject`'s cascade, which enumerates the
    subject OWNER's own quizzes. The READ path uses `list_quizzes_for_reader`."""
    require_owned_subject(session, owner_id, subject_id)
    return list(
        session.exec(
            select(Quiz)
            .where(Quiz.subject_id == subject_id, Quiz.owner_id == owner_id)
            .order_by(Quiz.created_at.desc())
        )
    )


def list_all_quizzes_for_subject(session: Session, subject_id: uuid.UUID) -> list[Quiz]:
    """ALL of a subject's quizzes, EVERY owner, with NO ownership/access check —
    **cascade-only**, same spirit as `subjects.service._get_subject_by_id`. Never expose
    to a request path: used exclusively by `subjects.service.delete_subject` to enumerate
    every member's quizzes on a shared org subject (each then passed to the owner-scoped
    `delete_quiz` with its own `owner_id`), so the subject delete can't hit an FK
    violation from another member's rows."""
    return list(session.exec(select(Quiz).where(Quiz.subject_id == subject_id)))


def list_quizzes_for_reader(
    session: Session, caller_id: str, org_ctx: OrgContext, subject_id: uuid.UUID
) -> list[Quiz]:
    """A subject's quizzes for anyone who may READ it. Verifies readability first
    (`SubjectNotFoundError` → 404 if denied), then returns the caller's own quizzes PLUS
    — when the caller isn't the subject owner — the subject owner's quizzes (the shared
    set), never another student's private quiz."""
    subject = require_readable_subject(session, caller_id, org_ctx, subject_id)
    return list(
        session.exec(
            select(Quiz)
            .where(Quiz.subject_id == subject_id, _reader_owner_filter(caller_id, subject))
            .order_by(Quiz.created_at.desc())
        )
    )


def get_quiz(
    session: Session, owner_id: str, subject_id: uuid.UUID, quiz_id: uuid.UUID
) -> Quiz | None:
    """Owner+subject-scoped lookup — a quiz from a different subject (or another owner)
    is a 404, not a silent cross-subject read. KEPT owner-scoped for the delete cascade;
    the read path uses `get_quiz_for_reader`."""
    return session.exec(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.subject_id == subject_id,
            Quiz.owner_id == owner_id,
        )
    ).first()


def get_quiz_for_reader(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    subject_id: uuid.UUID,
    quiz_id: uuid.UUID,
) -> Quiz | None:
    """One quiz for anyone who may READ its subject, restricted to the shared set: the
    caller's own quiz, or the SUBJECT OWNER's quiz — never another student's. Returns
    None (→ 404) if the subject isn't readable, the quiz isn't in it, or it belongs to a
    non-owner other than the caller — so a caller can't probe for another student's quiz
    by id (their quizzes stay `owner_id`-scoped)."""
    subject = get_readable_subject(session, caller_id, org_ctx, subject_id)
    if subject is None:
        return None
    quiz = session.exec(
        select(Quiz).where(Quiz.id == quiz_id, Quiz.subject_id == subject_id)
    ).first()
    if quiz is None or quiz.owner_id not in {caller_id, subject.owner_id}:
        return None
    return quiz


def list_questions(session: Session, owner_id: str, quiz_id: uuid.UUID) -> list[QuizQuestion]:
    """Owner-scoped question list — used by the delete cascade and callers that already
    hold an owner-verified quiz. The read path uses `list_questions_for_reader`."""
    return list(
        session.exec(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id, QuizQuestion.owner_id == owner_id)
            .order_by(QuizQuestion.order)
        )
    )


def list_questions_for_reader(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    subject_id: uuid.UUID,
    quiz_id: uuid.UUID,
) -> list[QuizQuestion]:
    """A quiz's questions for a reader — resolves the quiz through the reader path FIRST
    (so access + the shared-set restriction are enforced identically to
    `get_quiz_for_reader`), then lists its questions filtered by the QUIZ's owner_id (the
    quiz owner, NOT the caller — on a shared quiz the questions belong to the subject
    owner, so a caller-scoped filter would return nothing). Returns [] if the quiz isn't
    accessible."""
    quiz = get_quiz_for_reader(session, caller_id, org_ctx, subject_id, quiz_id)
    if quiz is None:
        return []
    return list(
        session.exec(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id, QuizQuestion.owner_id == quiz.owner_id)
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
    owner+subject scoping as `get_quiz`. OWNER-only: a student can't delete a teacher's
    shared quiz (they get the same 404 as a missing quiz).

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


def grade_and_record_attempt(
    session: Session,
    caller_id: str,
    org_ctx: OrgContext,
    subject_id: uuid.UUID,
    quiz_id: uuid.UUID,
    answers: dict[uuid.UUID, int],
) -> QuizAttemptResult:
    """Grade a student's quiz attempt server-side and UPSERT their `QuizAttempt` row.

    Authorization goes through the SAME reader path as reading the quiz
    (`get_quiz_for_reader`): a student may attempt a teacher's quiz over a shared org
    subject, but a quiz they can't read raises `QuizNotFoundError` (→ 404). We grade
    against the quiz OWNER's questions (on a shared quiz the questions belong to the
    subject owner, exactly like `list_questions_for_reader`).

    Grading is **authoritative and server-side** — the client's `answers` (question id →
    chosen option index) are the only input; a client-computed score is never trusted.
    `total` = number of questions; a question is correct only when its answer equals the
    question's `correct_index`. Defensive by design: unknown question ids in `answers` are
    ignored, and a missing or out-of-range index counts as wrong (never a 500).

    One attempt row per (quiz, student): the row is UPSERTED so the **latest attempt wins**
    (no duplicate, no history this increment).
    """
    quiz = get_quiz_for_reader(session, caller_id, org_ctx, subject_id, quiz_id)
    if quiz is None:
        raise QuizNotFoundError(quiz_id)

    # The quiz owner's questions (NOT caller-scoped — on a shared quiz they belong to the
    # subject owner), same filter as list_questions_for_reader.
    questions = list(
        session.exec(
            select(QuizQuestion).where(
                QuizQuestion.quiz_id == quiz_id, QuizQuestion.owner_id == quiz.owner_id
            )
        )
    )

    total = len(questions)
    correct = sum(1 for question in questions if answers.get(question.id) == question.correct_index)

    attempt = session.exec(
        select(QuizAttempt).where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.owner_id == caller_id)
    ).first()
    if attempt is None:
        attempt = QuizAttempt(
            quiz_id=quiz_id,
            subject_id=quiz.subject_id,
            owner_id=caller_id,
            correct=correct,
            total=total,
        )
        session.add(attempt)
    else:
        # Latest attempt wins — overwrite the existing row rather than inserting a second.
        attempt.correct = correct
        attempt.total = total
        attempt.submitted_at = datetime.now(UTC)

    session.commit()
    logging.getLogger(__name__).info(
        "Graded quiz attempt: quiz=%s student=%s score=%d/%d", quiz_id, caller_id, correct, total
    )
    return QuizAttemptResult(correct=correct, total=total)

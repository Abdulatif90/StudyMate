"""Response shapes for the progress API. Read-only rollups over existing data —
`owner_id` never exposed (same rule as everywhere else).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class DocumentStatusCounts(BaseModel):
    total: int
    ready: int
    pending: int
    failed: int


class FlashcardProgress(BaseModel):
    total: int
    # due_at <= now at the moment this was computed (see service.py's `now` parameter).
    due: int
    # new/learning/mature partition `total` with no overlap — see
    # service.MATURE_INTERVAL_DAYS_THRESHOLD and _flashcard_progress's docstring for
    # exactly how a card is bucketed.
    new: int
    learning: int
    mature: int


class SubjectProgress(BaseModel):
    subject_id: uuid.UUID
    documents: DocumentStatusCounts
    flashcards: FlashcardProgress
    # Quizzes *generated* for this subject. Not score history — quiz attempts aren't
    # persisted anywhere yet (grading is client-side only, see quiz/schemas.py's
    # answer-key decision); tracking performance is a follow-up (would need a
    # QuizAttempt model + a submission endpoint), not done in this increment.
    quiz_count: int


class OverallProgress(BaseModel):
    subject_count: int
    documents: DocumentStatusCounts
    flashcards: FlashcardProgress
    quiz_count: int

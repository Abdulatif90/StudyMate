"""Request/response shapes for the flashcards API. `owner_id` is deliberately absent
from every read shape — never exposed over HTTP (same rule as everywhere else).

`FlashcardRead` includes both sides (`front`/`back`) always — unlike quiz's
answer-reveal question, a flashcard's whole point is to show the answer once the
learner has recalled it themselves; there's no "hide the back" step to design around
here, and the SM-2 state (`due_at`, `interval_days`, ...) is useful to show for
progress/debugging, not a secret.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.shared.language import DEFAULT_LANGUAGE


class FlashcardGenerateRequest(BaseModel):
    num_cards: int = Field(default=10, ge=1, le=50)
    # A code from app.shared.language.SUPPORTED_LANGUAGES; unknown codes fall back to
    # English in language_name rather than rejecting the request.
    language: str = Field(default=DEFAULT_LANGUAGE)


class ReviewRequest(BaseModel):
    # SuperMemo's 0-5 quality scale (see sm2.PASSING_GRADE) — bounded here so a bad
    # grade 422s at the HTTP boundary before it can reach sm2.review at all.
    grade: int = Field(ge=0, le=5)


class FlashcardRead(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    front: str
    back: str
    repetitions: int
    ease_factor: float
    interval_days: int
    due_at: datetime
    last_reviewed_at: datetime | None
    created_at: datetime

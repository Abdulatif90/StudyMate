"""Business logic for subjects. Every function takes `owner_id` and filters by it —
callers (the router) never get to see or touch another user's data."""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from app.modules.billing.service import ensure_can_create_subject
from app.modules.subjects.models import Subject
from app.modules.subjects.schemas import SubjectCreate

# NOT top-level: documents/quiz/ask.service all import subjects.service (get_subject /
# require_owned_subject) themselves, so a top-level import here would be a circular
# import (confirmed directly — `import app.modules.subjects.service` raises
# `ImportError: cannot import name 'get_subject' from partially initialized module`
# the moment any of these four is imported at module load time). Deferred into
# delete_subject's body instead, the standard fix for this shape of cycle: by the time
# a request handler actually calls delete_subject, every module has already finished
# its own top-level initialization, so the import succeeds.


def create_subject(session: Session, owner_id: str, data: SubjectCreate) -> Subject:
    # Plan-limit guard first, before any work — see billing.service. Raises
    # PlanLimitExceededError (-> 402, handled app-wide in main.py).
    ensure_can_create_subject(session, owner_id)

    subject = Subject(owner_id=owner_id, name=data.name)
    session.add(subject)
    session.commit()
    session.refresh(subject)
    return subject


def list_subjects(session: Session, owner_id: str) -> list[Subject]:
    return list(session.exec(select(Subject).where(Subject.owner_id == owner_id)))


def get_subject(session: Session, owner_id: str, subject_id: uuid.UUID) -> Subject | None:
    return session.exec(
        select(Subject).where(Subject.id == subject_id, Subject.owner_id == owner_id)
    ).first()


def delete_subject(session: Session, owner_id: str, subject_id: uuid.UUID) -> bool:
    """Delete a subject and everything it owns: its documents (+ their `DocumentChunk`
    rows + R2 objects), quizzes (+ questions), flashcards, and conversations (+ turns)
    — then the `Subject` row itself. Returns `False` (router → 404) if the subject
    doesn't exist or isn't owned by `owner_id`, same as `get_subject`.

    **Deliberately not a DB-level `ON DELETE CASCADE`.** This codebase has no ORM
    `relationship()`/cascade anywhere (every delete is ordered by hand, e.g.
    `documents.service.delete_document`'s chunk-flush-before-parent), and more
    importantly, a DB-level cascade would delete `Document` *rows* while leaving their
    R2 *objects* orphaned forever — Postgres has no idea an R2 bucket exists, let alone
    that a cascade just ran. So this reuses each module's own `delete_*` function
    (documents/quiz/flashcards/ask), which already know how to clean up their own
    child rows and, for documents, the R2 object too — rather than duplicating that
    logic here or, worse, only deleting DB rows and silently leaking R2 storage.

    Enumerating each owned child is **owner_id-scoped** (and `subject_id`-scoped where
    the listing function takes it: `list_documents`/`list_quizzes`/`list_flashcards`/
    `list_conversations_by_subject`), the same tenant-scoping discipline as every other
    query in this module — a cascade that read across owners would delete another
    user's data, which would make this the most dangerous cross-tenant leak in the
    codebase rather than the least.

    **One transaction, not four+N.** Each `delete_*` function normally commits its own
    work (they're written as top-level operations, invoked directly from their own
    router) — called as-is in a loop here, that would mean the subject's documents
    could get permanently deleted even if a later flashcard/conversation delete then
    raised, leaving a half-deleted subject. So every call below passes `commit=False`:
    each function still flushes its own deletes (so FK ordering within it still works
    exactly as before), but nothing actually commits until this function's own final
    `session.commit()` — one failure anywhere rolls the *entire* cascade back via the
    session's implicit rollback-on-close, not just the step that failed.

    **The one accepted exception to "one transaction," by design, not a bug**:
    `delete_document`'s R2 object deletion happens immediately (best-effort, its own
    exceptions already swallowed — see its docstring) regardless of `commit`, since R2
    has no transaction to roll back. If this function's overall transaction were to
    fail *after* some documents' R2 objects were already removed, the DB rollback would
    resurrect those `Document` rows while their R2 objects stay gone. This is the same
    tradeoff a single `commit=True` `delete_document` call already makes (a storage-cost
    cleanup debt, never a dangling DB reference nothing else points at), just visible at
    a larger scale here — not worth making R2 transactional to close.
    """
    # See the module-level comment above for why these aren't top-level imports.
    from app.modules.ask.service import delete_conversation, list_conversations_by_subject
    from app.modules.documents.service import delete_document, list_documents
    from app.modules.flashcards.service import delete_flashcard, list_flashcards
    from app.modules.quiz.service import delete_quiz, list_quizzes

    subject = get_subject(session, owner_id, subject_id)
    if subject is None:
        return False

    for document in list_documents(session, owner_id, subject_id):
        delete_document(session, owner_id, subject_id, document.id, commit=False)

    for quiz in list_quizzes(session, owner_id, subject_id):
        delete_quiz(session, owner_id, subject_id, quiz.id, commit=False)

    for flashcard in list_flashcards(session, owner_id, subject_id):
        delete_flashcard(session, owner_id, flashcard.id, commit=False)

    for conversation in list_conversations_by_subject(session, owner_id, subject_id):
        delete_conversation(session, owner_id, conversation.id, commit=False)

    session.delete(subject)
    session.commit()
    return True

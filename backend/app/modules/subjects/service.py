"""Business logic + authorization for subjects.

**This module is the single source of truth for who may read/write a subject.** Every
other read/write path in the codebase (documents, ask/RAG) routes its access decision
through the pure `can_read_subject` / `can_write_subject` predicates or the
`require_readable_subject` / `require_writable_subject` pair defined here — so the rule
is written exactly once and can't drift between call sites (the #1 requirement of the
org-sharing model: a bug here leaks one org's — or one user's — private material to
another).

Two subject kinds (see `models.Subject`):

- **Private** (`org_id is None`): readable/writable only by `owner_id`. Unchanged from
  before org sharing existed.
- **Org-owned / read-shared** (`org_id` set): readable by any caller whose *active*
  organization equals that `org_id`; writable by that org's teachers/admins (or the
  owner). "Active org" comes from the verified JWT (`OrgContext`), never "any org the
  user ever belonged to" — the session token only carries the active org, which is
  both the natural and the safe scope.
"""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from app.core.org import OrgContext, is_teacher_role
from app.modules.billing.service import ensure_can_create_subject
from app.modules.subjects.models import Subject
from app.modules.subjects.schemas import SubjectCreate

# NOT top-level: documents/quiz/ask.service all import this module themselves, so a
# top-level import of any of them here would be a circular import (confirmed directly —
# `import app.modules.subjects.service` raises `ImportError: cannot import name ...
# from partially initialized module` the moment any of these is imported at module load
# time). Deferred into delete_subject's body instead, the standard fix for this shape of
# cycle: by the time a request handler actually calls delete_subject, every module has
# already finished its own top-level initialization, so the import succeeds.


class SubjectNotFoundError(Exception):
    """Raised when the given subject doesn't exist OR the caller may not read it.

    Deliberately the SAME error (→ 404) for "doesn't exist" and "exists but you can't
    read it": a denied caller must not be able to tell an org subject exists vs. not.
    Defined here (its natural home) and re-exported from `documents.service` for the
    many call sites that already import it from there.
    """


class SubjectWriteForbiddenError(Exception):
    """Raised when the caller may *read* a subject but not *modify* it — e.g. a plain
    member (student) of the org that owns it. Distinct from `SubjectNotFoundError`
    because the caller already knows the subject exists (they can read it), so a 403 is
    honest here and leaks nothing; a would-be writer who can't even read it gets the
    same 404 as anyone else (see `require_writable_subject`)."""


# ---------------------------------------------------------------------------
# Authorization predicates (pure — no DB, no I/O — so they're exhaustively unit-tested
# in isolation). Every read/write path in the codebase decides access via these two.
# ---------------------------------------------------------------------------


def can_read_subject(subject: Subject, caller_id: str, active_org_id: str | None) -> bool:
    """True iff `caller_id` may READ `subject`.

    Owner always may. Otherwise, only if the subject is org-owned AND that org is the
    caller's *active* org. The `subject.org_id is not None` guard is load-bearing: it
    stops a `None == None` match when a private subject (`org_id is None`) is checked
    against a caller with no active org (`active_org_id is None`) — that must be denied,
    not allowed.
    """
    if subject.owner_id == caller_id:
        return True
    return subject.org_id is not None and subject.org_id == active_org_id


def can_write_subject(subject: Subject, caller_id: str, org_ctx: OrgContext) -> bool:
    """True iff `caller_id` (with active-org context `org_ctx`) may WRITE `subject`.

    Owner always may. Otherwise, only if the subject is org-owned, that org is the
    caller's active org, AND the caller holds the teacher/admin role in it — a plain
    member (student) can read org content but never modify it. Same `org_id is not None`
    guard reasoning as `can_read_subject`.
    """
    if subject.owner_id == caller_id:
        return True
    return (
        subject.org_id is not None
        and subject.org_id == org_ctx.org_id
        and is_teacher_role(org_ctx.org_role)
    )


def _get_subject_by_id(session: Session, subject_id: uuid.UUID) -> Subject | None:
    """Fetch by primary key with NO ownership/org filter — for the access-checked
    lookups below only. Never expose this directly to a request path; callers must run
    the result through `can_read_subject` / `can_write_subject`."""
    return session.exec(select(Subject).where(Subject.id == subject_id)).first()


def get_readable_subject(
    session: Session, caller_id: str, org_ctx: OrgContext, subject_id: uuid.UUID
) -> Subject | None:
    """The subject if `caller_id` may read it (owner, or member of its active org),
    else None. The single fetch every read path uses instead of the old owner-only
    `get_subject`."""
    subject = _get_subject_by_id(session, subject_id)
    if subject is None or not can_read_subject(subject, caller_id, org_ctx.org_id):
        return None
    return subject


def require_readable_subject(
    session: Session, caller_id: str, org_ctx: OrgContext, subject_id: uuid.UUID
) -> Subject:
    """Return the subject if readable, else raise `SubjectNotFoundError` (→ 404). Used
    by every read path (get subject, list/get documents, ask/search) so a denied caller
    can't distinguish "no such subject" from "not shared with you"."""
    subject = get_readable_subject(session, caller_id, org_ctx, subject_id)
    if subject is None:
        raise SubjectNotFoundError(subject_id)
    return subject


def require_writable_subject(
    session: Session, caller_id: str, org_ctx: OrgContext, subject_id: uuid.UUID
) -> Subject:
    """Return the subject if the caller may WRITE it, else raise:

    - `SubjectNotFoundError` (→ 404) if they can't even read it — a would-be writer must
      not learn a subject exists any more than a reader can.
    - `SubjectWriteForbiddenError` (→ 403) if they can read but not write it (a student
      member of the owning org) — honest, since they already know it exists.
    """
    subject = _get_subject_by_id(session, subject_id)
    if subject is None or not can_read_subject(subject, caller_id, org_ctx.org_id):
        raise SubjectNotFoundError(subject_id)
    if not can_write_subject(subject, caller_id, org_ctx):
        raise SubjectWriteForbiddenError(subject_id)
    return subject


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_subject(
    session: Session,
    owner_id: str,
    data: SubjectCreate,
    org_ctx: OrgContext | None = None,
) -> Subject:
    """Create a subject owned by `owner_id`.

    **Publishing rule**: when the caller has an active org AND is a teacher/admin of it,
    the new subject is org-owned (`org_id = active org`) and thereby read-shared with
    that org's members. In every other case — no active org, or a plain member — it's
    PRIVATE (`org_id = None`). A student must not be able to publish content to the whole
    org, so org-ownership requires the teacher/admin capability, not mere membership.
    `owner_id` is always the creating user either way.
    """
    # Plan-limit guard first, before any work — see billing.service. Raises
    # PlanLimitExceededError (-> 402, handled app-wide in main.py).
    ensure_can_create_subject(session, owner_id, org_ctx)

    org_id: str | None = None
    if org_ctx is not None and org_ctx.org_id is not None and is_teacher_role(org_ctx.org_role):
        org_id = org_ctx.org_id

    subject = Subject(owner_id=owner_id, name=data.name, org_id=org_id)
    session.add(subject)
    session.commit()
    session.refresh(subject)
    return subject


def list_subjects(
    session: Session, owner_id: str, active_org_id: str | None = None
) -> list[Subject]:
    """The caller's own subjects PLUS the subjects of their active org (deduped). With
    no active org this is exactly the legacy behavior — only the caller's own subjects.
    A subject the caller owns that also happens to be org-owned appears once."""
    condition = Subject.owner_id == owner_id
    if active_org_id is not None:
        condition = condition | (Subject.org_id == active_org_id)
    subjects = session.exec(select(Subject).where(condition)).all()
    # De-dupe by id (an owned subject that is also this org's subject matches both arms).
    return list({subject.id: subject for subject in subjects}.values())


def list_owned_subjects(session: Session, owner_id: str) -> list[Subject]:
    """The caller's OWN subjects, in a deterministic order (creation time, then id as a
    stable tiebreaker). Deliberately owner-only — no org sharing — because its one caller,
    the Telegram bot, has no active-org context (a Telegram chat carries only an
    `owner_id`), so it may only ever reach the user's own private subjects. The stable
    order lets the bot present a numbered picker whose numbers don't shift between the
    `/subjects` listing and a later `/subject <n>` selection."""
    return list(
        session.exec(
            select(Subject)
            .where(Subject.owner_id == owner_id)
            .order_by(Subject.created_at, Subject.id)
        )
    )


def get_subject(session: Session, owner_id: str, subject_id: uuid.UUID) -> Subject | None:
    """Owner-only lookup — unchanged. Still used where ownership (not mere readability)
    is the right scope: the `delete_subject` cascade enumerates the *owner's* own child
    rows. Read paths use `get_readable_subject` / `require_readable_subject` instead."""
    return session.exec(
        select(Subject).where(Subject.id == subject_id, Subject.owner_id == owner_id)
    ).first()


def delete_subject(
    session: Session, caller_id: str, org_ctx: OrgContext, subject_id: uuid.UUID
) -> bool:
    """Delete a subject and ALL content derived under it by EVERY member — documents (+
    `DocumentChunk` rows + R2 objects), quizzes (+ questions, + quiz attempts, + any
    assignments linking them), flashcards (+ every reviewer's `FlashcardReviewState` rows),
    conversations (+ turns), and the subject's assignments (+ their submissions) — then the
    `Subject` row itself. Returns `False` (router → 404) if the subject doesn't exist or
    the caller can't read it. Raises `SubjectWriteForbiddenError` (router → 403) if the
    caller can read but not write it (a student member of the owning org).

    **Authorization is `require_writable_subject`** (owner, or a teacher/admin of the
    org that owns it) — the same single-source-of-truth guard every write path uses.

    **The cascade enumerates ALL owners' children, not just the subject owner's.** On a
    shared org subject other members derive their own content (a student's own
    flashcards/quizzes/conversations, all `owner_id`-scoped to that student, plus their
    `FlashcardReviewState` rows over the teacher's shared cards). Because every child's
    `subject_id` (or `flashcard_id`) is a real FK, leaving another member's rows behind
    would make the final `session.delete(subject)` raise an FK violation. So each content
    module exposes a cascade-only `list_all_*_for_subject` enumerator (ALL owners, no
    access check), and this iterates those and calls the EXISTING owner-scoped `delete_*`
    with **each row's OWN `owner_id`** — reusing every module's child-row + R2 cleanup
    (delete_document → chunks + R2 object; delete_quiz → questions; delete_flashcard →
    that card's `FlashcardReviewState` rows for all reviewers; delete_conversation →
    turns). For a private subject (owner == caller) this is identical to before — there's
    only ever one owner's content.

    **Deliberately not a DB-level `ON DELETE CASCADE`** (same reasoning as before org
    sharing): a DB cascade would delete `Document` rows while leaving their R2 objects
    orphaned forever, so this reuses each module's own `delete_*` (which knows how to
    clean its child rows and, for documents, the R2 object). Each `delete_*` is called
    with `commit=False` so the whole cascade is one transaction — one failure rolls the
    entire thing back, never a half-deleted subject.
    """
    # See the module-level comment above for why these aren't top-level imports.
    from app.modules.ask.service import delete_conversation, list_all_conversations_for_subject
    from app.modules.assignments.service import delete_assignments_for_subject
    from app.modules.documents.service import delete_document, list_all_documents_for_subject
    from app.modules.flashcards.service import delete_flashcard, list_all_flashcards_for_subject
    from app.modules.quiz.service import delete_quiz, list_all_quizzes_for_subject

    subject = _get_subject_by_id(session, subject_id)
    if subject is None or not can_read_subject(subject, caller_id, org_ctx.org_id):
        return False
    if not can_write_subject(subject, caller_id, org_ctx):
        raise SubjectWriteForbiddenError(subject_id)

    # Enumerate EVERY member's children (not just the subject owner's) and delete each
    # with its OWN owner_id, so no member's rows are left to trip the subject-delete FK.
    for document in list_all_documents_for_subject(session, subject_id):
        delete_document(session, document.owner_id, subject_id, document.id, commit=False)

    for quiz in list_all_quizzes_for_subject(session, subject_id):
        delete_quiz(session, quiz.owner_id, subject_id, quiz.id, commit=False)

    for flashcard in list_all_flashcards_for_subject(session, subject_id):
        delete_flashcard(session, flashcard.owner_id, flashcard.id, commit=False)

    for conversation in list_all_conversations_for_subject(session, subject_id):
        delete_conversation(session, conversation.owner_id, conversation.id, commit=False)

    # Assignments (org-broadcast) reference the subject DIRECTLY via `assignments.subject_id`
    # (and their submissions hang off them). The quiz cascade above already removed any
    # assignment that LINKED a quiz; this sweeps the rest — an assignment over the subject
    # with no quiz link — so the final subject DELETE can't trip `assignments_subject_id_fkey`.
    delete_assignments_for_subject(session, subject_id)

    session.delete(subject)
    session.commit()
    return True

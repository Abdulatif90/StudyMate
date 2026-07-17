"""Business logic for plans + usage-limit enforcement.

**This module owns all quota counting.** Other modules never count usage themselves —
they call exactly one `ensure_can_*` guard at the start of their create path and one
`record_generation` on success. That keeps the caps in one place (change `LIMITS`, done)
instead of scattered across four services.

**Tenant scoping is the security crux here**, more than anywhere else in the codebase: a
usage count that read across owners would let one user's activity consume — or silently
bypass — another's quota. Every query below filters by `owner_id`, and each aggregated
table already carries its own denormalized `owner_id` column, so that's a plain equality
filter (same reasoning as `progress.service`), never a join that could go wrong.

**Provider-agnostic.** No Polar, no payment SDK, no secrets. This is the entitlement
layer; when Polar keys exist, its webhook upserts `UserPlan` and everything here keeps
working unchanged. There is deliberately no plan-*change* endpoint yet.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlmodel import Session, func, select

from app.modules.billing.models import GenerationKind, GenerationUsage, Plan, UserPlan
from app.modules.documents.models import Document
from app.modules.subjects.models import Subject


@dataclass(frozen=True)
class PlanLimits:
    """`None` means **unlimited** for that dimension (used by Business)."""

    max_subjects: int | None
    max_documents_per_subject: int | None
    max_generations_per_day: int | None


# THE config. Every cap in the product lives here and nowhere else — tuning a tier is a
# one-line change with no code to touch. `max_generations_per_day` is a *combined* cap
# across quiz + flashcard generations (i.e. "20 generations a day", not 20 of each).
LIMITS: dict[Plan, PlanLimits] = {
    Plan.FREE: PlanLimits(
        max_subjects=3,
        max_documents_per_subject=10,
        max_generations_per_day=20,
    ),
    Plan.PRO: PlanLimits(
        max_subjects=50,
        max_documents_per_subject=200,
        max_generations_per_day=200,
    ),
    # Business is "effectively unlimited" — None on every dimension rather than a huge
    # sentinel number, so the guards below skip the count query entirely.
    Plan.BUSINESS: PlanLimits(
        max_subjects=None,
        max_documents_per_subject=None,
        max_generations_per_day=None,
    ),
}


class LimitKind(StrEnum):
    SUBJECTS = "subjects"
    DOCUMENTS_PER_SUBJECT = "documents_per_subject"
    GENERATIONS_PER_DAY = "generations_per_day"


_LIMIT_DESCRIPTIONS: dict[LimitKind, str] = {
    LimitKind.SUBJECTS: "subjects",
    LimitKind.DOCUMENTS_PER_SUBJECT: "documents in this subject",
    LimitKind.GENERATIONS_PER_DAY: "quiz/flashcard generations today",
}


class PlanLimitExceededError(Exception):
    """Raised when an action would exceed the owner's plan cap. Carries which limit and
    what the cap was so the HTTP layer can name both (see main.py's handler) instead of
    returning a vague "quota exceeded"."""

    def __init__(self, limit: LimitKind, plan: Plan, cap: int) -> None:
        self.limit = limit
        self.plan = plan
        self.cap = cap
        super().__init__(f"{plan.value} plan allows at most {cap} {_LIMIT_DESCRIPTIONS[limit]}")

    @property
    def message(self) -> str:
        return (
            f"You've reached your {self.plan.value} plan limit of "
            f"{self.cap} {_LIMIT_DESCRIPTIONS[self.limit]}. Upgrade your plan to continue."
        )


def _utc_day(now: datetime | None) -> date:
    """The UTC calendar day `now` falls in. **UTC, never local time** — a local-time
    boundary would make the daily reset depend on server timezone and be untestable;
    this is deterministic and `now` is injectable everywhere it's used."""
    moment = now if now is not None else datetime.now(UTC)
    return moment.astimezone(UTC).date()


def get_plan(session: Session, owner_id: str) -> Plan:
    """The owner's plan. **No row means Free** — never an error: a brand-new user who
    has never touched billing still gets the Free entitlements."""
    user_plan = session.get(UserPlan, owner_id)
    return user_plan.plan if user_plan is not None else Plan.FREE


def get_limits(session: Session, owner_id: str) -> PlanLimits:
    return LIMITS[get_plan(session, owner_id)]


# --- Usage counts (all owner-scoped) ----------------------------------------


def count_subjects(session: Session, owner_id: str) -> int:
    return session.exec(
        select(func.count()).select_from(Subject).where(Subject.owner_id == owner_id)
    ).one()


def count_documents_in_subject(session: Session, owner_id: str, subject_id: uuid.UUID) -> int:
    # owner_id AND subject_id: the subject filter alone would be a cross-tenant read if
    # a subject_id ever leaked; owner_id alone would count the wrong subject's documents.
    return session.exec(
        select(func.count())
        .select_from(Document)
        .where(Document.owner_id == owner_id, Document.subject_id == subject_id)
    ).one()


def count_generations_today(session: Session, owner_id: str, now: datetime | None = None) -> int:
    """Today's generation count for this owner, summed across kinds (the cap is
    combined). `func.sum` returns NULL for no rows, hence the `or 0`."""
    total = session.exec(
        select(func.sum(GenerationUsage.count)).where(
            GenerationUsage.owner_id == owner_id,
            GenerationUsage.day == _utc_day(now),
        )
    ).one()
    return total or 0


# --- Guards — called at the START of each create path ------------------------
#
# Ordering contract (the reason these are `ensure_*` and run first): the check happens
# BEFORE any billable/side-effecting work — before an R2 upload, before a Claude call,
# before any row is written. A rejected request therefore costs nothing and persists
# nothing.


def ensure_can_create_subject(session: Session, owner_id: str) -> None:
    cap = get_limits(session, owner_id).max_subjects
    if cap is None:
        return
    if count_subjects(session, owner_id) >= cap:
        raise PlanLimitExceededError(LimitKind.SUBJECTS, get_plan(session, owner_id), cap)


def ensure_can_upload_document(session: Session, owner_id: str, subject_id: uuid.UUID) -> None:
    cap = get_limits(session, owner_id).max_documents_per_subject
    if cap is None:
        return
    if count_documents_in_subject(session, owner_id, subject_id) >= cap:
        raise PlanLimitExceededError(
            LimitKind.DOCUMENTS_PER_SUBJECT, get_plan(session, owner_id), cap
        )


def ensure_can_generate(session: Session, owner_id: str, now: datetime | None = None) -> None:
    cap = get_limits(session, owner_id).max_generations_per_day
    if cap is None:
        return
    if count_generations_today(session, owner_id, now) >= cap:
        raise PlanLimitExceededError(
            LimitKind.GENERATIONS_PER_DAY, get_plan(session, owner_id), cap
        )


def record_generation(
    session: Session,
    owner_id: str,
    kind: GenerationKind,
    now: datetime | None = None,
) -> None:
    """Count one generation event against today's allowance.

    **Does NOT commit** — it only stages the increment on `session`, so the caller's
    existing `session.commit()` persists the counter in the *same transaction* as the
    generated rows. Either both land or neither does; the counter can't drift from
    reality by committing separately and then having the create fail.

    **Ordering, decided:** callers `ensure_can_generate(...)` first (before the Claude
    call) and `record_generation(...)` only after generation *succeeds*. So a failed
    Claude call doesn't burn the user's daily quota — they got nothing for it.

    **Known, accepted limitation:** the check and this increment aren't atomic with
    respect to each other, so two concurrent requests sitting exactly at the cap can
    both pass the check and both proceed — a benign ±1 overshoot on a soft daily cap.
    Making it strict would need `SELECT ... FOR UPDATE` (or an atomic
    upsert-and-return) and the lock contention that comes with it; not worth it for a
    usage cap that exists to bound cost, not to gate correctness.
    """
    day = _utc_day(now)
    usage = session.exec(
        select(GenerationUsage).where(
            GenerationUsage.owner_id == owner_id,
            GenerationUsage.day == day,
            GenerationUsage.kind == kind,
        )
    ).first()

    if usage is None:
        usage = GenerationUsage(owner_id=owner_id, day=day, kind=kind, count=1)
    else:
        usage.count += 1
    session.add(usage)

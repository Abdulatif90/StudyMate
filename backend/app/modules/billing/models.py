"""Billing/entitlement tables — which plan an owner is on, and how much of their
daily generation allowance they've used.

**Provider-agnostic on purpose.** Nothing here knows about Polar (DECISIONS.md #7) or
any other payment provider: `UserPlan` is just "this owner is on this plan". When Polar
keys exist, its webhook becomes the thing that upserts `UserPlan` — the enforcement
layer built on top of these tables doesn't change at all.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import UniqueConstraint
from sqlmodel import Column, Field, SQLModel


class Plan(StrEnum):
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"
    # Team is the org/seat tier (Phase 5): an org admin subscribes the whole organization
    # (Polar "Team Plan", a recurring per-seat product), and every member of that org is
    # lifted to Team entitlements. It is never bought individually via /billing/checkout —
    # only via the org flow (create_team_checkout) — but it is a first-class Plan so the
    # same LIMITS table and webhook machinery apply to it unchanged.
    TEAM = "team"


class GenerationKind(StrEnum):
    QUIZ = "quiz"
    FLASHCARD = "flashcard"


# SQLAlchemy's Enum type stores a member's *name* ("FREE") by default, not its *value*
# ("free") — values_callable makes the DB labels match what the Python/JSON side uses.
# Same fix (and reason) as documents.models._status_column_type.
_plan_column_type = SAEnum(Plan, values_callable=lambda cls: [e.value for e in cls])
_generation_kind_column_type = SAEnum(
    GenerationKind, values_callable=lambda cls: [e.value for e in cls]
)


class UserPlan(SQLModel, table=True):
    """One row per owner who is on a *non-default* plan. **Absence of a row means Free**
    (see service.get_plan) — a brand-new user with no billing row is never an error, they
    just get the Free entitlements. `owner_id` is the primary key, so it's inherently
    tenant-scoped: there is exactly one plan per owner and no way to address another
    owner's row without their id.

    This is the row a future Polar webhook will upsert on subscribe/cancel.
    """

    __tablename__ = "user_plans"

    owner_id: str = Field(primary_key=True)
    plan: Plan = Field(sa_column=Column(_plan_column_type, nullable=False))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrgPlan(SQLModel, table=True):
    """One row per Clerk organization that is on a *non-default* plan — the org analogue
    of `UserPlan`. **Absence of a row means Free** (an org that has never subscribed lifts
    nobody), exactly like `UserPlan`. `org_id` (the Clerk organization id) is the primary
    key, so it's inherently scoped: exactly one plan per org and no way to address another
    org's row without its id.

    Additive, never a replacement for `UserPlan`: a member's effective entitlement is the
    HIGHER of their own `UserPlan` and their active org's `OrgPlan` (see
    service.effective_plan). An org on `Plan.TEAM` therefore lifts every member to Team,
    while a member with no active org behaves exactly as before.

    This is the row the Polar webhook upserts for an org (`external_id = "org:<org_id>"`)
    on subscribe/revoke — mirroring how it upserts `UserPlan` for an individual.
    """

    __tablename__ = "org_plans"

    org_id: str = Field(primary_key=True)
    plan: Plan = Field(sa_column=Column(_plan_column_type, nullable=False))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GenerationUsage(SQLModel, table=True):
    """Per-owner, per-UTC-day, per-kind count of *generation events*.

    Why a dedicated counter instead of counting existing rows by `created_at`: the cap
    is on generation **events**, and rows don't map to events 1:1. One `generate_quiz`
    makes exactly one `Quiz` row (countable), but one `generate_flashcards` makes *N*
    `Flashcard` rows — counting those would charge a single 10-card generation as 10
    against the daily cap. This table records what the limit actually means, and stays
    correct if either module's row-per-generation ratio ever changes.

    `day` is a **UTC** date (see service._utc_day) — never local time, so the reset
    boundary is deterministic and testable rather than dependent on server timezone.

    Bounded growth: at most one row per owner per day per kind (2/day/owner), not one
    row per generation.
    """

    __tablename__ = "generation_usage"
    __table_args__ = (UniqueConstraint("owner_id", "day", "kind", name="uq_generation_usage_slot"),)

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    day: date = Field(index=True)
    kind: GenerationKind = Field(sa_column=Column(_generation_kind_column_type, nullable=False))
    count: int = Field(default=0)

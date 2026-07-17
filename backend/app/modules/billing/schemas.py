"""Response shapes for the billing API. `owner_id` is never exposed (same rule as
everywhere else) — the caller's plan is implicitly their own."""

from __future__ import annotations

from pydantic import BaseModel

from app.modules.billing.models import Plan


class PlanLimitsRead(BaseModel):
    """`null` means unlimited for that dimension (Business)."""

    max_subjects: int | None
    max_documents_per_subject: int | None
    max_generations_per_day: int | None


class PlanUsageRead(BaseModel):
    """Current usage against the caps that are countable account-wide.

    `max_documents_per_subject` has no entry here on purpose — it's a *per-subject*
    cap, so there's no single account-wide number for it. The frontend gets the cap in
    `limits` (to state the rule) and the per-subject count from the existing
    `GET /subjects/{id}/progress` documents total.
    """

    subjects: int
    generations_today: int


class PlanRead(BaseModel):
    plan: Plan
    limits: PlanLimitsRead
    usage: PlanUsageRead

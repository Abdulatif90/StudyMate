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


class CheckoutCreateRequest(BaseModel):
    """Which plan to buy. The caller names a *plan*, never a Polar product id — product
    ids are server-side config (see config.polar_product_id_*), so a client can't point a
    checkout at an arbitrary product. There is no `owner_id` here either: it comes from
    the caller's verified token, so nobody can check out on someone else's behalf.
    """

    plan: Plan
    #: Where Polar sends the customer after paying. Optional: with no value Polar shows
    #: its own hosted confirmation page, which is correct until the billing frontend
    #: exists to receive the redirect.
    success_url: str | None = None


class TeamCheckoutCreateRequest(BaseModel):
    """Start a Team-Plan checkout for the caller's *active organization*. There is no
    `plan` field — this endpoint always buys Team — and no `org_id`: the org comes from
    the caller's verified token (and only a teacher/admin may reach the route), so a caller
    can neither pick another product nor subscribe an org they don't administer."""

    #: Where Polar sends the browser after paying. Optional (Polar's hosted confirmation
    #: page is shown when omitted), same as the individual checkout.
    success_url: str | None = None


class CheckoutCreateResponse(BaseModel):
    #: Polar-hosted checkout page to redirect the browser to.
    checkout_url: str


class WebhookResponse(BaseModel):
    """What the webhook reports back to Polar. `status` is one of `applied`,
    `ignored`, or `ignored_stale` — an accepted-but-not-actioned event is a 200 with an
    explicit outcome, not a silent success (rule 3)."""

    status: str

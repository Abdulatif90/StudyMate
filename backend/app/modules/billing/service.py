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

**The entitlement layer stays provider-agnostic.** Everything above the "Polar" section
at the bottom — `LIMITS`, the counts, the `ensure_can_*` guards, `record_generation` —
knows nothing about who takes the money. Polar's *only* job in this codebase is to upsert
one `UserPlan` row (DECISIONS.md #7); the enforcement built on that row is unchanged by
its arrival. There is still deliberately no plan-*change* endpoint: that's the payment
provider's job, and a self-serve "set my own plan" route would be an entitlement bypass.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from polar_sdk.models import CheckoutCreate, PolarError
from sqlmodel import Session, func, select

from app.core import polar_client
from app.core.config import get_settings
from app.modules.billing.models import GenerationKind, GenerationUsage, Plan, UserPlan
from app.modules.documents.models import Document
from app.modules.subjects.models import Subject

logger = logging.getLogger(__name__)


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


# --- Polar (payments) --------------------------------------------------------
#
# Polar's only job is to upsert `UserPlan` (DECISIONS.md #7). Everything above this line
# is unaware of it. The two halves are:
#   1. checkout  — authenticated; this is where the owner_id -> Polar customer link is
#      planted, because it's the only point in the flow where we know who the caller is.
#   2. webhook   — public/unauthenticated; resolves the owner back out of a *verified*
#      payload and writes the plan.


#: Plans that can actually be purchased. **Free is not sold**: Free is the *absence* of a
#: paid plan (no `UserPlan` row, or an explicit downgrade to it), so there is no product
#: to check out and no money to take. Checking out "free" would be a $0 no-op.
PURCHASABLE_PLANS: frozenset[Plan] = frozenset({Plan.PRO, Plan.BUSINESS})


class PlanNotPurchasableError(Exception):
    """Raised when a checkout is requested for a plan that isn't sold (i.e. Free)."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        super().__init__(f"The {plan.value} plan cannot be purchased.")


class PolarCheckoutError(Exception):
    """Raised when Polar rejects/fails a checkout creation. Deliberately distinct from
    `PolarConfigError` (a deploy mistake) — this one is an upstream failure, and the
    router maps the two to different statuses rather than swallowing either."""


def _product_id_for_plan(plan: Plan) -> str:
    settings = get_settings()
    product_ids: dict[Plan, tuple[str, str | None]] = {
        Plan.PRO: ("POLAR_PRODUCT_ID_PRO", settings.polar_product_id_pro),
        Plan.BUSINESS: ("POLAR_PRODUCT_ID_BUSINESS", settings.polar_product_id_business),
    }
    env_name, product_id = product_ids[plan]
    if not product_id:
        raise polar_client.PolarConfigError(
            f"Polar is not configured for the {plan.value} plan — missing {env_name}. "
            "Add it to backend/.env — see backend/.env.example."
        )
    return product_id


def plan_for_product_id(product_id: str) -> Plan | None:
    """Reverse of `_product_id_for_plan`: which plan a Polar product grants, or `None` if
    the product isn't one we sell. `None` is not an error — the org may sell products
    this app doesn't map (the caller decides what to do), and guessing a plan for an
    unknown product would hand out entitlements we never sold."""
    settings = get_settings()
    mapping = {
        settings.polar_product_id_pro: Plan.PRO,
        settings.polar_product_id_business: Plan.BUSINESS,
    }
    # A missing/unset id must never match an incoming product_id.
    mapping.pop(None, None)
    return mapping.get(product_id)


def create_checkout(owner_id: str, plan: Plan, success_url: str | None = None) -> str:
    """Create a Polar checkout for `plan` and return its URL.

    **This is where owner linkage is planted, and it's the crux of the whole flow.** The
    webhook arrives with no Clerk JWT, so it can only know whose plan to change if we
    record that link now — here, where the caller *is* authenticated and `owner_id` comes
    from their verified token. `external_customer_id` puts the Clerk owner_id on the Polar
    customer; the webhook reads it back out of a signature-verified payload
    (`subscription.customer.external_id`).

    It is deliberately NOT taken from anything the client sends: the caller cannot ask to
    upgrade somebody else, because they never get to name the owner at all.
    """
    if plan not in PURCHASABLE_PLANS:
        raise PlanNotPurchasableError(plan)

    product_id = _product_id_for_plan(plan)
    checkout = CheckoutCreate(
        products=[product_id],
        external_customer_id=owner_id,
    )
    if success_url is not None:
        checkout.success_url = success_url

    try:
        result = polar_client.get_client().checkouts.create(request=checkout)
    except PolarError as exc:
        # Wrapped, never swallowed (rule 3): the router turns this into a real error
        # status. Returning a 200 with no URL would strand the user on a dead button.
        raise PolarCheckoutError(f"Polar rejected the checkout request: {exc}") from exc
    return result.url


def _as_utc(moment: datetime) -> datetime:
    """Normalize a datetime to UTC-aware.

    Needed because the two sides of the ordering comparison below disagree: Polar's event
    timestamp is timezone-aware, but `UserPlan.updated_at` round-trips through a
    `TIMESTAMP WITHOUT TIME ZONE` column and comes back **naive**. Comparing the two
    directly raises `TypeError`. Values are always UTC by construction (`_utc_day`'s
    reasoning applies here too), so a naive value is simply tagged as UTC.
    """
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


#: Events that GRANT a plan. `subscription.active` covers a new paid subscription and a
#: recovered payment. `subscription.updated` covers a mid-period tier switch (Pro ->
#: Business), which fires no `active` event of its own — without it an upgrade would be
#: silently ignored. Both are re-checked against the subscription's *status* below, so an
#: `updated` that isn't actually an active subscription grants nothing.
_GRANTING_EVENTS = frozenset({"subscription.active", "subscription.updated"})

#: Events that REVOKE a plan back to Free. **`subscription.revoked` only, never
#: `subscription.canceled`** — a subtle but expensive distinction the SDK spells out:
#: `canceled` means "cancellation scheduled, the customer may still have access until the
#: end of the period they already paid for", while `revoked` means "access lost now"
#: (cancellation taking effect, or payment retries exhausted). Downgrading on `canceled`
#: would cut off a paying customer mid-period. `past_due` is likewise not here: payment
#: may still recover, and `revoked` fires if it doesn't.
_REVOKING_EVENTS = frozenset({"subscription.revoked"})

#: Subscription statuses that entitle the customer to their plan. `trialing` counts —
#: a trial is meant to grant access.
_ENTITLED_STATUSES = frozenset({"active", "trialing"})


def resolve_subscription_event(event: object) -> tuple[str, Plan, datetime] | None:
    """Map a **verified** Polar webhook event to `(owner_id, plan, event_at)`, or `None`
    if it's not an event that should change anybody's plan.

    `None` covers every "understood but not actionable" case — an event type we don't act
    on, a subscription that isn't entitled, a product we don't sell, or a customer with no
    `external_id` (e.g. a subscription created straight from the Polar dashboard rather
    than through our checkout). These are logged and reported, never silently dropped
    (rule 3), but they are not *errors*: failing them would only make Polar retry an
    event that will never succeed.
    """
    event_type = getattr(event, "TYPE", None)
    if event_type not in _GRANTING_EVENTS | _REVOKING_EVENTS:
        logger.info("Ignoring unhandled Polar event type %s", event_type)
        return None

    subscription = event.data  # type: ignore[attr-defined]

    # **Owner linkage, read only from the verified payload.** `external_id` is the Clerk
    # owner_id we planted server-side at checkout (see create_checkout). It is never read
    # from a client-supplied field on this request — the request body's authenticity is
    # exactly what the signature check established.
    owner_id = subscription.customer.external_id
    if not owner_id:
        logger.warning(
            "Polar %s event for subscription %s has no customer external_id — cannot "
            "resolve an owner, ignoring. (Was this subscription created outside our "
            "checkout?)",
            event_type,
            subscription.id,
        )
        return None

    event_at = event.timestamp  # type: ignore[attr-defined]

    if event_type in _REVOKING_EVENTS:
        return owner_id, Plan.FREE, event_at

    status = getattr(subscription.status, "value", subscription.status)
    if status not in _ENTITLED_STATUSES:
        logger.info(
            "Ignoring Polar %s event — subscription %s is %s, not an entitled status. "
            "(Loss of access arrives as subscription.revoked.)",
            event_type,
            subscription.id,
            status,
        )
        return None

    plan = plan_for_product_id(subscription.product_id)
    if plan is None:
        logger.warning(
            "Polar %s event references product %s, which maps to no plan — ignoring. "
            "Check POLAR_PRODUCT_ID_* against the products in the Polar dashboard.",
            event_type,
            subscription.product_id,
        )
        return None

    return owner_id, plan, event_at


def handle_webhook_event(session: Session, event: object) -> str:
    """Apply a **verified** Polar event. Returns a short outcome string for the response
    body/logs. The caller MUST have verified the signature first — this trusts `event`.
    """
    resolved = resolve_subscription_event(event)
    if resolved is None:
        return "ignored"

    owner_id, plan, event_at = resolved
    written = apply_subscription_event(session, owner_id, plan, event_at)
    return "applied" if written else "ignored_stale"


def apply_subscription_event(
    session: Session,
    owner_id: str,
    plan: Plan,
    event_at: datetime,
) -> bool:
    """Upsert exactly one owner's `UserPlan`. Returns True if the plan was written,
    False if the event was ignored as stale/duplicate.

    **Tenant scoping**: `owner_id` is the primary key, and it comes from the verified
    payload — this touches exactly one row and cannot reach another owner's plan.

    **Idempotency + ordering** (Polar retries, and can deliver out of order): the write is
    guarded on `event_at` vs the stored `updated_at`, and `updated_at` is set to the
    *event's* timestamp, not wall-clock time. That's what makes the comparison meaningful:
    if it stored processing time, a legitimately newer event that merely arrived a moment
    later would look older than the row and be dropped. A duplicate delivery has an
    equal timestamp and is skipped; a stale one is older and is skipped. Both are no-ops
    rather than errors — a retry that changes nothing is a success, not a failure.
    """
    event_at = _as_utc(event_at)
    user_plan = session.get(UserPlan, owner_id)

    if user_plan is None:
        session.add(UserPlan(owner_id=owner_id, plan=plan, updated_at=event_at))
        session.commit()
        return True

    if _as_utc(user_plan.updated_at) >= event_at:
        logger.info(
            "Ignoring stale/duplicate Polar event for owner (event_at=%s, updated_at=%s)",
            event_at,
            user_plan.updated_at,
        )
        return False

    # **Downgrade sets Plan.FREE rather than deleting the row**, even though "no row"
    # also means Free (models.UserPlan). Deleting would throw away `updated_at` — the
    # ordering guard above — so a stale `subscription.active` redelivered afterwards
    # would find no row, look fresh, and silently re-grant a paid plan for free. Keeping
    # the row costs one tiny row per ex-subscriber and keeps the guard intact.
    user_plan.plan = plan
    user_plan.updated_at = event_at
    session.add(user_plan)
    session.commit()
    return True

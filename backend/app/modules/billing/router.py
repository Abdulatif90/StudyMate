"""Billing HTTP routes — thin: auth/DB wiring only (all logic lives in service.py).

There is deliberately **no plan-change endpoint**: changing a plan is the payment
provider's job (Polar, DECISIONS.md #7), so the only ways a plan moves are a Polar
checkout the customer actually pays for and the webhook that follows. A "set my own plan"
route would be a self-serve entitlement bypass, and it stays absent on purpose.

**Two very different trust models live in this file**, which is the thing to keep straight
when editing it:
  - `GET /plan` and `POST /checkout` are authenticated — `get_current_user_id` gives a
    Clerk-verified owner_id.
  - `POST /webhook` is **public**: Polar calls it from the internet with no Clerk JWT.
    Its trust comes entirely from the signature check, which is why that check runs before
    anything else touches the payload or the DB.

`PlanLimitExceededError` -> 402 is handled application-wide in `app/main.py`, not here —
the mapping is identical for every guarded path, so it lives in one place rather than
being copy-pasted into four routers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from app.core import polar_client
from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.billing import service
from app.modules.billing.schemas import (
    CheckoutCreateRequest,
    CheckoutCreateResponse,
    PlanLimitsRead,
    PlanRead,
    PlanUsageRead,
    WebhookResponse,
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plan", response_model=PlanRead)
def get_plan(
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> PlanRead:
    plan = service.get_plan(session, owner_id)
    limits = service.LIMITS[plan]
    return PlanRead(
        plan=plan,
        limits=PlanLimitsRead(
            max_subjects=limits.max_subjects,
            max_documents_per_subject=limits.max_documents_per_subject,
            # Effective cap = plan cap + referral bonus, so the client's usage meter matches
            # exactly what `ensure_can_generate` enforces (not the raw plan cap).
            max_generations_per_day=service.effective_generations_per_day(session, owner_id),
        ),
        usage=PlanUsageRead(
            subjects=service.count_subjects(session, owner_id),
            generations_today=service.count_generations_today(session, owner_id),
        ),
    )


@router.post("/checkout", response_model=CheckoutCreateResponse)
def create_checkout(
    payload: CheckoutCreateRequest,
    owner_id: str = Depends(get_current_user_id),
) -> CheckoutCreateResponse:
    """Start a Polar checkout for a paid plan. Authenticated: `owner_id` comes from the
    caller's verified Clerk token and is what gets linked to the Polar customer, so a
    caller can only ever buy a plan for themselves."""
    try:
        url = service.create_checkout(owner_id, payload.plan, payload.success_url)
    except service.PlanNotPurchasableError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except polar_client.PolarConfigError as exc:
        # A deploy mistake, not the caller's fault — 500, and the message names the
        # missing env var (never its value).
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    except service.PolarCheckoutError as exc:
        # Upstream failed. Surfaced as a real error status, never a 200 with no URL.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't start checkout with our payment provider. Please try again.",
        ) from exc
    return CheckoutCreateResponse(checkout_url=url)


@router.post("/webhook", response_model=WebhookResponse)
async def polar_webhook(
    request: Request,
    session: Session = Depends(get_session),
) -> WebhookResponse:
    """Polar -> us. **Public endpoint, no Clerk auth** (Polar has no user token to send),
    so the signature IS the authentication.

    Order matters and is load-bearing:
      1. read the **raw** body — the signature covers those exact bytes, so parsing to
         JSON and re-serializing would change them and break verification;
      2. verify the signature;
      3. only then touch the payload or the DB.
    An unverified webhook would let anyone POST themselves onto Business for free, which
    is why there is no path to step 3 that skips step 2 — including when no secret is
    configured, which raises rather than defaulting to "accept".

    `async def` on purpose: `await request.body()` needs it, and it's the only way to get
    the raw bytes.
    """
    body = await request.body()

    try:
        event = polar_client.verify_webhook(body, dict(request.headers))
    except polar_client.WebhookVerificationError as exc:
        # Bad/missing signature, or a stale timestamp (replay). Reject, write nothing.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook signature."
        ) from exc
    except polar_client.WebhookUnknownTypeError:
        # Signature was VALID — Polar just sent an event type this SDK doesn't know.
        # Not a security problem and not retryable, so accept and ignore.
        return WebhookResponse(status="ignored")
    except polar_client.PolarConfigError as exc:
        # No secret configured. Fail loudly (500) rather than accepting unverified
        # events — see get_webhook_secret.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return WebhookResponse(status=service.handle_webhook_event(session, event))

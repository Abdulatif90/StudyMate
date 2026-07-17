"""Billing HTTP routes — thin: auth/DB wiring only (all logic lives in service.py).

Read-only for now. There is deliberately **no plan-change endpoint**: changing a plan is
the payment provider's job (Polar, DECISIONS.md #7), and its webhook will upsert
`UserPlan` once the user provides Polar keys. Exposing a "set my own plan" endpoint in
the meantime would be a self-serve entitlement bypass.

`PlanLimitExceededError` -> 402 is handled application-wide in `app/main.py`, not here —
the mapping is identical for every guarded path, so it lives in one place rather than
being copy-pasted into four routers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.billing import service
from app.modules.billing.schemas import PlanLimitsRead, PlanRead, PlanUsageRead

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
            max_generations_per_day=limits.max_generations_per_day,
        ),
        usage=PlanUsageRead(
            subjects=service.count_subjects(session, owner_id),
            generations_today=service.count_generations_today(session, owner_id),
        ),
    )

"""Referral HTTP routes — thin: auth/DB wiring + exception-to-status translation only
(all business logic + abuse guards live in service.py), mirroring the other routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.referral import service
from app.modules.referral.schemas import ReferralRead, ReferralRedeemRequest

router = APIRouter(prefix="/referral", tags=["referral"])


@router.get("", response_model=ReferralRead)
def get_referral(
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> ReferralRead:
    return service.get_referral_summary(session, owner_id)


@router.post("/redeem", status_code=status.HTTP_204_NO_CONTENT)
def redeem_referral(
    data: ReferralRedeemRequest,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> None:
    try:
        service.redeem(session, owner_id, data.code)
    except service.ReferralCodeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That referral code doesn't exist.") from exc
    except service.SelfReferralError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You can't redeem your own referral code."
        ) from exc
    except service.AlreadyAttributedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This account has already been referred."
        ) from exc

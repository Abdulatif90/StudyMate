"""Request/response shapes for the referral API — kept separate from `models` so the
DB structure (owner ids, table columns) is never exposed over HTTP."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReferralRead(BaseModel):
    """The caller's own referral code, how many people they've referred, and the reward
    those referrals have earned."""

    code: str
    referred_count: int
    #: Bonus daily quiz/flashcard generations earned from referrals
    #: (= referred_count * billing BONUS_PER_REFERRAL). Derived, not stored.
    bonus_generations_per_day: int


class ReferralRedeemRequest(BaseModel):
    # Length-bounded so an obviously-malformed value is rejected by validation (422)
    # before it ever reaches the service's lookup; the service normalizes/validates the
    # exact format itself.
    code: str = Field(min_length=1, max_length=64)

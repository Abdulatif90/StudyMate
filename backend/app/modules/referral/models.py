"""Referral attribution — the provider-agnostic "who referred whom" layer.

`owner_id` is the Clerk user id (JWT `sub` claim), the same tenant key every other
module scopes by. This module records attribution ONLY — it deliberately grants no
reward and knows nothing about billing/Polar; the reward model is a separate future
increment (see docs/PROGRESS.md "Referral reward grant").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ReferralCode(SQLModel, table=True):
    __tablename__ = "referral_codes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # One stable code per user — `owner_id` unique so a user can never end up with two
    # codes (the idempotency guarantee `service.get_or_create_code` relies on, backed by
    # the DB rather than only the read-then-write check).
    owner_id: str = Field(unique=True, index=True)
    # The human-shareable code itself, unique across all users so `redeem` can look a
    # referrer up by it alone.
    code: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReferralAttribution(SQLModel, table=True):
    __tablename__ = "referral_attributions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    referrer_owner_id: str = Field(index=True)
    # A given user can be attributed to a referrer at most once, EVER — enforced at the
    # DB level (unique), not just by the service's already-attributed check, so a race
    # between two concurrent redeems still can't create a second row.
    referred_owner_id: str = Field(unique=True, index=True)
    code: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

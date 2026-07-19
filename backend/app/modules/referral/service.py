"""Business logic for referrals — code issuance + attribution, with the abuse guards
enforced here (not the router). Every query is `owner_id`-scoped: a caller can only ever
read/create their own code and can only attribute *themselves* to someone else's code.

Attribution ONLY — no reward is granted here and nothing touches billing/Polar. The
reward model is a separate future increment (docs/PROGRESS.md "Referral reward grant").
"""

from __future__ import annotations

import secrets

from sqlmodel import Session, func, select

from app.modules.referral.models import ReferralAttribution, ReferralCode
from app.modules.referral.schemas import ReferralRead

# RFC 4648 base32 alphabet (A–Z, 2–7): case-insensitive on redeem, no 0/1/8/9 to confuse
# with O/I/B/g when a user reads a code off a screen. 8 chars = 32**8 ≈ 1.1e12 possible
# codes, so collisions are astronomically unlikely — the loop below is a correctness
# backstop, not a hot path.
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_CODE_LENGTH = 8
_MAX_GENERATION_ATTEMPTS = 8


class ReferralCodeNotFoundError(Exception):
    """Raised when a redeemed code matches no user's referral code (router -> 404)."""


class SelfReferralError(Exception):
    """Raised when a user tries to redeem their own code (router -> 400)."""


class AlreadyAttributedError(Exception):
    """Raised when the caller already has an attribution row (router -> 409). Redeem is
    a one-time, idempotent-no-op action: a second redeem never creates a duplicate."""


def _generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))


def get_or_create_code(session: Session, owner_id: str) -> ReferralCode:
    """Return this user's stable referral code, creating it on first request. Idempotent:
    a second call returns the SAME code (looked up by `owner_id`), never a new one."""
    existing = session.exec(select(ReferralCode).where(ReferralCode.owner_id == owner_id)).first()
    if existing is not None:
        return existing

    for _ in range(_MAX_GENERATION_ATTEMPTS):
        code = _generate_code()
        collision = session.exec(select(ReferralCode).where(ReferralCode.code == code)).first()
        if collision is None:
            referral_code = ReferralCode(owner_id=owner_id, code=code)
            session.add(referral_code)
            session.commit()
            session.refresh(referral_code)
            return referral_code

    # Never expected at 32**8 keyspace — fail loudly rather than silently returning a
    # colliding/None code (same loud-failure discipline as the rest of the codebase).
    raise RuntimeError("Could not generate a unique referral code after several attempts.")


def redeem(session: Session, owner_id: str, code: str) -> ReferralAttribution:
    """Attribute `owner_id` to the owner of `code`. Guards, in order:

    - unknown code            -> ReferralCodeNotFoundError (router 404)
    - the caller's own code   -> SelfReferralError         (router 400)
    - caller already referred -> AlreadyAttributedError    (router 409, no duplicate row)

    On success inserts exactly one `ReferralAttribution` and commits.
    """
    normalized = code.strip().upper()

    referral_code = session.exec(
        select(ReferralCode).where(ReferralCode.code == normalized)
    ).first()
    if referral_code is None:
        raise ReferralCodeNotFoundError(f"No referral code matches {normalized!r}.")

    if referral_code.owner_id == owner_id:
        raise SelfReferralError("You can't redeem your own referral code.")

    already = session.exec(
        select(ReferralAttribution).where(ReferralAttribution.referred_owner_id == owner_id)
    ).first()
    if already is not None:
        raise AlreadyAttributedError("This account has already been referred.")

    attribution = ReferralAttribution(
        referrer_owner_id=referral_code.owner_id,
        referred_owner_id=owner_id,
        code=normalized,
    )
    session.add(attribution)
    session.commit()
    session.refresh(attribution)
    return attribution


def count_referrals(session: Session, owner_id: str) -> int:
    """How many people this owner has referred — an owner-scoped COUNT of the
    `ReferralAttribution` rows where they are the referrer.

    Extracted so both `get_referral_summary` (surfacing the reward) and
    `billing.service.effective_generations_per_day` (granting it) read the referral count
    from ONE place, never a duplicated query that could drift. It is a pure function of the
    attribution rows — which the redeem/attribution layer already guards (self-referral
    blocked, one attribution per referee via a DB unique constraint, no referrer-switching)
    — so counting them needs no additional abuse guard of its own.
    """
    total = session.exec(
        select(func.count(ReferralAttribution.id)).where(
            ReferralAttribution.referrer_owner_id == owner_id
        )
    ).one()
    return int(total)


def get_referral_summary(session: Session, owner_id: str) -> ReferralRead:
    """The caller's code (created if needed), an owner-scoped count of people they've
    referred, and the reward those referrals have earned — everything `GET /referral`
    needs in one call.

    `bonus_generations_per_day` is DERIVED from `referred_count` (no stored reward row), so
    it inherits the attribution layer's abuse guards for free. It surfaces only the bonus
    the referrals earned, NOT the raw effective daily cap (that stays in billing)."""
    from app.modules.billing.service import BONUS_PER_REFERRAL

    code = get_or_create_code(session, owner_id).code
    referred_count = count_referrals(session, owner_id)
    return ReferralRead(
        code=code,
        referred_count=referred_count,
        bonus_generations_per_day=referred_count * BONUS_PER_REFERRAL,
    )

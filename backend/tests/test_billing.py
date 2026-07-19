"""Tests for the billing/entitlement module — plans, limits, and enforcement, against
an in-memory SQLite DB. Mirrors tests/test_progress.py's harness (no mocking needed:
this module touches no Claude/Cohere/R2/Inngest, it's plans + DB counts).

`now` is pinned wherever a daily boundary matters, so the UTC-day reset is asserted
deterministically rather than racing wall-clock time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.core.org import OrgContext
from app.main import app
from app.modules.billing import service as billing_service
from app.modules.billing.models import GenerationKind, GenerationUsage, OrgPlan, Plan, UserPlan
from app.modules.billing.service import (
    BONUS_PER_REFERRAL,
    LIMITS,
    LimitKind,
    PlanLimitExceededError,
    effective_generations_per_day,
    effective_plan,
    ensure_can_create_subject,
    ensure_can_generate,
    ensure_can_upload_document,
    get_plan,
    record_generation,
)
from app.modules.documents.models import Document, DocumentStatus
from app.modules.referral.models import ReferralAttribution
from app.modules.subjects.models import Subject

_TEST_USER = "user_test_123"
_OTHER_USER = "someone_else"
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _get_test_session():
    with Session(_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _isolated_db():
    SQLModel.metadata.create_all(_engine)
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER
    yield
    del app.dependency_overrides[get_session]
    del app.dependency_overrides[get_current_user_id]
    SQLModel.metadata.drop_all(_engine)


client = TestClient(app)


def _set_plan(owner_id: str, plan: Plan) -> None:
    with Session(_engine) as session:
        session.add(UserPlan(owner_id=owner_id, plan=plan))
        session.commit()


def _make_subjects(owner_id: str, count: int) -> list[uuid.UUID]:
    ids = []
    with Session(_engine) as session:
        for i in range(count):
            subject = Subject(owner_id=owner_id, name=f"Subject {i}")
            session.add(subject)
            session.commit()
            session.refresh(subject)
            ids.append(subject.id)
    return ids


def _make_documents(owner_id: str, subject_id: uuid.UUID, count: int) -> None:
    with Session(_engine) as session:
        for i in range(count):
            session.add(
                Document(
                    subject_id=subject_id,
                    owner_id=owner_id,
                    filename=f"doc{i}.txt",
                    content_type="text/plain",
                    status=DocumentStatus.READY,
                )
            )
        session.commit()


def _record_generations(owner_id: str, count: int, now: datetime = _NOW) -> None:
    with Session(_engine) as session:
        for _ in range(count):
            record_generation(session, owner_id, GenerationKind.QUIZ, now)
            session.commit()


def _make_referrals(referrer_owner_id: str, count: int) -> None:
    """Create `count` genuine attributions crediting `referrer_owner_id` — each from a
    distinct referred user, as the DB unique constraint on `referred_owner_id` requires."""
    with Session(_engine) as session:
        for i in range(count):
            session.add(
                ReferralAttribution(
                    referrer_owner_id=referrer_owner_id,
                    referred_owner_id=f"referred_{referrer_owner_id}_{i}",
                    code="ABCD2345",
                )
            )
        session.commit()


# --- get_plan ----------------------------------------------------------------


def test_get_plan_defaults_to_free_when_no_row():
    # a brand-new user with no billing row is never an error — they get Free
    with Session(_engine) as session:
        assert get_plan(session, "never_seen_before") == Plan.FREE


@pytest.mark.parametrize("plan", [Plan.FREE, Plan.PRO, Plan.BUSINESS])
def test_get_plan_returns_the_stored_plan(plan):
    _set_plan(_TEST_USER, plan)
    with Session(_engine) as session:
        assert get_plan(session, _TEST_USER) == plan


# --- Subject cap -------------------------------------------------------------


def test_subject_cap_allows_up_to_the_limit_then_raises():
    cap = LIMITS[Plan.FREE].max_subjects
    _make_subjects(_TEST_USER, cap - 1)

    with Session(_engine) as session:
        ensure_can_create_subject(session, _TEST_USER)  # the Nth is allowed

    _make_subjects(_TEST_USER, 1)  # now exactly at the cap

    with Session(_engine) as session, pytest.raises(PlanLimitExceededError) as exc:
        ensure_can_create_subject(session, _TEST_USER)  # the N+1th is not
    assert exc.value.limit == LimitKind.SUBJECTS
    assert exc.value.plan == Plan.FREE
    assert exc.value.cap == cap


def test_pro_plan_lifts_the_subject_cap():
    _set_plan(_TEST_USER, Plan.PRO)
    # well past Free's cap of 3, still under Pro's
    _make_subjects(_TEST_USER, LIMITS[Plan.FREE].max_subjects + 2)

    with Session(_engine) as session:
        ensure_can_create_subject(session, _TEST_USER)  # does not raise


def test_business_plan_is_unlimited_for_subjects():
    _set_plan(_TEST_USER, Plan.BUSINESS)
    _make_subjects(_TEST_USER, LIMITS[Plan.PRO].max_subjects + 1)

    with Session(_engine) as session:
        ensure_can_create_subject(session, _TEST_USER)  # no cap at all


def test_subject_cap_is_tenant_isolated():
    # the other owner is way over the Free cap...
    _make_subjects(_OTHER_USER, LIMITS[Plan.FREE].max_subjects + 5)

    # ...which must not consume _TEST_USER's allowance
    with Session(_engine) as session:
        ensure_can_create_subject(session, _TEST_USER)


# --- Documents-per-subject cap ----------------------------------------------


def test_document_cap_allows_up_to_the_limit_then_raises():
    cap = LIMITS[Plan.FREE].max_documents_per_subject
    subject_id = _make_subjects(_TEST_USER, 1)[0]
    _make_documents(_TEST_USER, subject_id, cap - 1)

    with Session(_engine) as session:
        ensure_can_upload_document(session, _TEST_USER, subject_id)  # Nth allowed

    _make_documents(_TEST_USER, subject_id, 1)  # at the cap

    with Session(_engine) as session, pytest.raises(PlanLimitExceededError) as exc:
        ensure_can_upload_document(session, _TEST_USER, subject_id)
    assert exc.value.limit == LimitKind.DOCUMENTS_PER_SUBJECT
    assert exc.value.cap == cap


def test_document_cap_is_per_subject_not_per_account():
    cap = LIMITS[Plan.FREE].max_documents_per_subject
    subject_a, subject_b = _make_subjects(_TEST_USER, 2)
    _make_documents(_TEST_USER, subject_a, cap)  # subject A is full

    # subject B has its own allowance — the cap is per-subject
    with Session(_engine) as session:
        ensure_can_upload_document(session, _TEST_USER, subject_b)


def test_document_cap_is_tenant_isolated():
    cap = LIMITS[Plan.FREE].max_documents_per_subject
    subject_id = _make_subjects(_TEST_USER, 1)[0]
    # another owner's documents somehow tagged to the same subject_id must not count
    # against this owner (owner_id is filtered, not just subject_id)
    _make_documents(_OTHER_USER, subject_id, cap + 5)

    with Session(_engine) as session:
        ensure_can_upload_document(session, _TEST_USER, subject_id)


# --- Daily generation cap ----------------------------------------------------


def test_generation_cap_allows_up_to_the_limit_then_raises():
    cap = LIMITS[Plan.FREE].max_generations_per_day
    _record_generations(_TEST_USER, cap - 1)

    with Session(_engine) as session:
        ensure_can_generate(session, _TEST_USER, _NOW)  # Nth allowed

    _record_generations(_TEST_USER, 1)  # at the cap

    with Session(_engine) as session, pytest.raises(PlanLimitExceededError) as exc:
        ensure_can_generate(session, _TEST_USER, _NOW)
    assert exc.value.limit == LimitKind.GENERATIONS_PER_DAY
    assert exc.value.cap == cap


def test_generation_cap_counts_quiz_and_flashcards_together():
    # the cap is combined ("20 generations/day"), not 20 of each
    cap = LIMITS[Plan.FREE].max_generations_per_day
    with Session(_engine) as session:
        for _ in range(cap // 2):
            record_generation(session, _TEST_USER, GenerationKind.QUIZ, _NOW)
        for _ in range(cap - cap // 2):
            record_generation(session, _TEST_USER, GenerationKind.FLASHCARD, _NOW)
        session.commit()

    with Session(_engine) as session:
        assert billing_service.count_generations_today(session, _TEST_USER, _NOW) == cap
        with pytest.raises(PlanLimitExceededError):
            ensure_can_generate(session, _TEST_USER, _NOW)


def test_generation_cap_resets_at_the_utc_day_boundary():
    cap = LIMITS[Plan.FREE].max_generations_per_day
    _record_generations(_TEST_USER, cap, now=_NOW)

    with Session(_engine) as session:
        with pytest.raises(PlanLimitExceededError):
            ensure_can_generate(session, _TEST_USER, _NOW)  # exhausted today

        # one second past midnight UTC the next day: a fresh allowance
        next_day = datetime(2026, 6, 2, 0, 0, 1, tzinfo=UTC)
        ensure_can_generate(session, _TEST_USER, next_day)
        assert billing_service.count_generations_today(session, _TEST_USER, next_day) == 0


def test_generation_cap_counts_the_whole_utc_day_not_a_rolling_window():
    cap = LIMITS[Plan.FREE].max_generations_per_day
    # recorded just before midnight UTC...
    _record_generations(_TEST_USER, cap, now=datetime(2026, 6, 1, 23, 59, tzinfo=UTC))

    with Session(_engine) as session:
        # ...still counts against that same UTC day one minute earlier
        with pytest.raises(PlanLimitExceededError):
            ensure_can_generate(session, _TEST_USER, datetime(2026, 6, 1, 0, 1, tzinfo=UTC))


def test_generation_cap_is_tenant_isolated():
    cap = LIMITS[Plan.FREE].max_generations_per_day
    _record_generations(_OTHER_USER, cap + 5)

    with Session(_engine) as session:
        ensure_can_generate(session, _TEST_USER, _NOW)  # other owner's usage isn't mine
        assert billing_service.count_generations_today(session, _TEST_USER, _NOW) == 0


def test_business_plan_is_unlimited_for_generations():
    _set_plan(_TEST_USER, Plan.BUSINESS)
    _record_generations(_TEST_USER, LIMITS[Plan.PRO].max_generations_per_day + 1)

    with Session(_engine) as session:
        ensure_can_generate(session, _TEST_USER, _NOW)


# --- Referral reward: bonus daily generations --------------------------------


def test_zero_referrals_effective_cap_equals_plan_cap():
    # Pins the pre-reward behavior: no referrals -> effective cap is exactly the plan cap.
    plan_cap = LIMITS[Plan.FREE].max_generations_per_day
    with Session(_engine) as session:
        assert effective_generations_per_day(session, _TEST_USER) == plan_cap

    _record_generations(_TEST_USER, plan_cap)
    with Session(_engine) as session, pytest.raises(PlanLimitExceededError):
        ensure_can_generate(session, _TEST_USER, _NOW)


def test_referral_bonus_raises_the_effective_generation_cap():
    referrals = 3
    plan_cap = LIMITS[Plan.FREE].max_generations_per_day
    bonused = plan_cap + referrals * BONUS_PER_REFERRAL
    _make_referrals(_TEST_USER, referrals)

    with Session(_engine) as session:
        assert effective_generations_per_day(session, _TEST_USER) == bonused

    # Past the base plan cap but under the bonused cap -> still allowed.
    _record_generations(_TEST_USER, bonused - 1)
    with Session(_engine) as session:
        ensure_can_generate(session, _TEST_USER, _NOW)

    # At the bonused cap -> blocked, and the error names the raised cap.
    _record_generations(_TEST_USER, 1)
    with Session(_engine) as session, pytest.raises(PlanLimitExceededError) as exc:
        ensure_can_generate(session, _TEST_USER, _NOW)
    assert exc.value.cap == bonused


def test_referral_bonus_does_not_apply_to_business_unlimited():
    _set_plan(_TEST_USER, Plan.BUSINESS)
    _make_referrals(_TEST_USER, 5)

    with Session(_engine) as session:
        # Unlimited stays unlimited — a bonus on None is meaningless.
        assert effective_generations_per_day(session, _TEST_USER) is None
        ensure_can_generate(session, _TEST_USER, _NOW)


def test_referral_bonus_is_tenant_isolated():
    # Another owner's attributions must not inflate this owner's cap.
    _make_referrals(_OTHER_USER, 10)
    plan_cap = LIMITS[Plan.FREE].max_generations_per_day

    with Session(_engine) as session:
        assert effective_generations_per_day(session, _TEST_USER) == plan_cap

    _record_generations(_TEST_USER, plan_cap)
    with Session(_engine) as session, pytest.raises(PlanLimitExceededError):
        ensure_can_generate(session, _TEST_USER, _NOW)


def test_get_plan_endpoint_surfaces_the_bonused_cap():
    referrals = 2
    _make_referrals(_TEST_USER, referrals)

    body = client.get("/billing/plan").json()

    expected = LIMITS[Plan.FREE].max_generations_per_day + referrals * BONUS_PER_REFERRAL
    assert body["limits"]["max_generations_per_day"] == expected


# --- record_generation -------------------------------------------------------


def test_record_generation_creates_then_increments_one_row_per_slot():
    with Session(_engine) as session:
        record_generation(session, _TEST_USER, GenerationKind.QUIZ, _NOW)
        record_generation(session, _TEST_USER, GenerationKind.QUIZ, _NOW)
        session.commit()

    with Session(_engine) as session:
        rows = session.exec(select(GenerationUsage)).all()
        # one row per (owner, day, kind) slot, counting up — not one row per event
        assert len(rows) == 1
        assert rows[0].count == 2


def test_record_generation_does_not_commit_on_its_own():
    # it only stages the increment, so the caller's commit persists counter + created
    # rows atomically (see billing.service.record_generation's docstring)
    with Session(_engine) as session:
        record_generation(session, _TEST_USER, GenerationKind.QUIZ, _NOW)
        session.rollback()  # caller's transaction failed -> the counter must roll back too

    with Session(_engine) as session:
        assert billing_service.count_generations_today(session, _TEST_USER, _NOW) == 0


def test_record_generation_separates_days():
    _record_generations(_TEST_USER, 2, now=_NOW)
    _record_generations(_TEST_USER, 3, now=_NOW + timedelta(days=1))

    with Session(_engine) as session:
        assert billing_service.count_generations_today(session, _TEST_USER, _NOW) == 2
        assert (
            billing_service.count_generations_today(session, _TEST_USER, _NOW + timedelta(days=1))
            == 3
        )


# --- GET /billing/plan -------------------------------------------------------


def test_get_plan_endpoint_reports_free_plan_limits_and_usage():
    _make_subjects(_TEST_USER, 2)
    _record_generations(_TEST_USER, 4, now=datetime.now(UTC))

    response = client.get("/billing/plan")

    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "free"
    assert body["limits"] == {
        "max_subjects": LIMITS[Plan.FREE].max_subjects,
        "max_documents_per_subject": LIMITS[Plan.FREE].max_documents_per_subject,
        "max_generations_per_day": LIMITS[Plan.FREE].max_generations_per_day,
    }
    assert body["usage"] == {"subjects": 2, "generations_today": 4}
    assert "owner_id" not in body


def test_get_plan_endpoint_reports_business_unlimited_as_null():
    _set_plan(_TEST_USER, Plan.BUSINESS)

    body = client.get("/billing/plan").json()

    assert body["plan"] == "business"
    assert body["limits"] == {
        "max_subjects": None,
        "max_documents_per_subject": None,
        "max_generations_per_day": None,
    }


def test_get_plan_endpoint_usage_is_owner_scoped():
    _make_subjects(_OTHER_USER, 3)  # another owner's subjects

    body = client.get("/billing/plan").json()

    assert body["usage"]["subjects"] == 0  # never counts someone else's


# --- HTTP enforcement (the app-wide 402 handler) -----------------------------


def test_creating_a_subject_over_the_free_cap_returns_402():
    cap = LIMITS[Plan.FREE].max_subjects
    for i in range(cap):
        assert client.post("/subjects", json={"name": f"Subject {i}"}).status_code == 201

    response = client.post("/subjects", json={"name": "One too many"})

    assert response.status_code == 402
    body = response.json()
    assert body["limit"] == "subjects"
    assert body["plan"] == "free"
    assert body["cap"] == cap
    assert "upgrade" in body["detail"].lower()  # names the limit + suggests an upgrade
    assert str(cap) in body["detail"]


def test_a_rejected_create_persists_nothing():
    cap = LIMITS[Plan.FREE].max_subjects
    for i in range(cap):
        client.post("/subjects", json={"name": f"Subject {i}"})

    client.post("/subjects", json={"name": "Rejected"})

    # the guard runs before any work — the over-cap subject was never written
    names = [s["name"] for s in client.get("/subjects").json()]
    assert "Rejected" not in names
    assert len(names) == cap


def test_upgrading_the_plan_lifts_the_http_cap():
    cap = LIMITS[Plan.FREE].max_subjects
    for i in range(cap):
        client.post("/subjects", json={"name": f"Subject {i}"})
    assert client.post("/subjects", json={"name": "Blocked"}).status_code == 402

    _set_plan(_TEST_USER, Plan.PRO)  # what a future Polar webhook will do

    assert client.post("/subjects", json={"name": "Now allowed"}).status_code == 201


# --- Org/team entitlements (effective_plan) ----------------------------------

_TEST_ORG = "org_test_abc"
_OTHER_ORG = "org_other_xyz"


def _set_org_plan(org_id: str, plan: Plan) -> None:
    with Session(_engine) as session:
        session.add(OrgPlan(org_id=org_id, plan=plan))
        session.commit()


def _org(org_id: str | None, role: str = "member") -> OrgContext:
    return OrgContext(org_id=org_id, org_role=role)


def test_effective_plan_with_no_org_is_the_individual_plan():
    _set_plan(_TEST_USER, Plan.PRO)
    with Session(_engine) as session:
        # no org_ctx, and an org_ctx with no active org, both resolve to the own plan
        assert effective_plan(session, _TEST_USER) is Plan.PRO
        assert effective_plan(session, _TEST_USER, _org(None)) is Plan.PRO


def test_org_team_lifts_a_free_member_to_team():
    """A member on a Free UserPlan whose active org is on Team gets Team."""
    _set_org_plan(_TEST_ORG, Plan.TEAM)
    with Session(_engine) as session:
        assert effective_plan(session, _TEST_USER, _org(_TEST_ORG)) is Plan.TEAM


def test_effective_plan_takes_the_higher_of_own_and_org():
    """The max of the two, both directions: own Business beats an org still on Free; org
    Team beats own Pro."""
    _set_plan(_TEST_USER, Plan.BUSINESS)
    with Session(_engine) as session:
        assert effective_plan(session, _TEST_USER, _org(_TEST_ORG)) is Plan.BUSINESS

    _set_org_plan(_TEST_ORG, Plan.TEAM)
    with Session(_engine) as session:
        # Team out-ranks Business -> the org lifts even a Business user to Team
        assert effective_plan(session, _TEST_USER, _org(_TEST_ORG)) is Plan.TEAM


def test_org_team_gives_a_member_unlimited_limits_over_the_free_cap():
    """The whole point: a Free member of a Team org sails past the Free subject cap."""
    _set_org_plan(_TEST_ORG, Plan.TEAM)
    org = _org(_TEST_ORG)
    _make_subjects(_TEST_USER, LIMITS[Plan.FREE].max_subjects)  # at the Free cap

    with Session(_engine) as session:
        # Free alone would raise here; the Team org lifts the cap to unlimited
        ensure_can_create_subject(session, _TEST_USER, org)

    # ...and the generation guard is unlimited too
    _record_generations(_TEST_USER, LIMITS[Plan.FREE].max_generations_per_day)
    with Session(_engine) as session:
        assert effective_generations_per_day(session, _TEST_USER, org) is None
        ensure_can_generate(session, _TEST_USER, _NOW, org)


def test_org_plan_is_scoped_to_its_own_org():
    """A member whose active org is Free is unaffected by *another* org being on Team."""
    _set_org_plan(_OTHER_ORG, Plan.TEAM)
    with Session(_engine) as session:
        # the caller's active org (_TEST_ORG) has no plan -> still Free
        assert effective_plan(session, _TEST_USER, _org(_TEST_ORG)) is Plan.FREE


def test_referral_bonus_still_applies_under_an_org_where_cap_is_not_unlimited():
    """A Free member of an org that is only on Pro (a finite cap) still gets their own
    referral bonus on top of the effective Pro cap."""
    _set_org_plan(_TEST_ORG, Plan.PRO)
    referrals = 2
    _make_referrals(_TEST_USER, referrals)
    org = _org(_TEST_ORG)

    expected = LIMITS[Plan.PRO].max_generations_per_day + referrals * BONUS_PER_REFERRAL
    with Session(_engine) as session:
        assert effective_generations_per_day(session, _TEST_USER, org) == expected


def test_over_cap_error_names_the_effective_plan():
    """When an org lifts the caller, a limit error (from a finite org tier) names the
    effective plan, not the caller's own Free plan."""
    _set_org_plan(_TEST_ORG, Plan.PRO)
    org = _org(_TEST_ORG)
    _make_subjects(_TEST_USER, LIMITS[Plan.PRO].max_subjects)  # at the Pro cap

    with Session(_engine) as session, pytest.raises(PlanLimitExceededError) as exc:
        ensure_can_create_subject(session, _TEST_USER, org)
    assert exc.value.plan is Plan.PRO

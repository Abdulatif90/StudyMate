"""Tests for the referral module — router + service, against an in-memory SQLite DB.

Same isolation pattern as test_subjects.py: `get_session`/`get_current_user_id` are
overridden per-test (set up/torn down by a fixture, not at import time) so nothing leaks
into other test modules sharing the same `app` instance. Fully offline — the referral
module has no external dependency (no Cohere/Claude/R2), so no mocks are needed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.main import app
from app.modules.referral import service as referral_service
from app.modules.referral.models import ReferralAttribution, ReferralCode

_USER_A = "user_referrer_a"
_USER_B = "user_referred_b"
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _get_test_session():
    with Session(_engine) as session:
        yield session


def _as_user(user_id: str) -> None:
    app.dependency_overrides[get_current_user_id] = lambda: user_id


@pytest.fixture(autouse=True)
def _isolated_db():
    SQLModel.metadata.create_all(_engine)
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_current_user_id] = lambda: _USER_A
    yield
    del app.dependency_overrides[get_session]
    del app.dependency_overrides[get_current_user_id]
    SQLModel.metadata.drop_all(_engine)


client = TestClient(app)


# --- code issuance ---------------------------------------------------------------


def test_get_referral_returns_a_code_and_zero_count():
    response = client.get("/referral")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["code"], str)
    assert len(body["code"]) == 8
    assert body["referred_count"] == 0


def test_code_is_idempotent_same_code_every_time():
    first = client.get("/referral").json()["code"]
    second = client.get("/referral").json()["code"]
    assert first == second

    # And only one row exists in the DB for this owner — not a new one per request.
    with Session(_engine) as session:
        codes = session.exec(select(ReferralCode).where(ReferralCode.owner_id == _USER_A)).all()
    assert len(codes) == 1


def test_get_or_create_code_is_idempotent_at_the_service_layer():
    with Session(_engine) as session:
        one = referral_service.get_or_create_code(session, _USER_A)
        two = referral_service.get_or_create_code(session, _USER_A)
        assert one.id == two.id
        assert one.code == two.code


# --- redeem happy path -----------------------------------------------------------


def test_redeem_happy_path_creates_exactly_one_attribution():
    code = client.get("/referral").json()["code"]  # A's code

    _as_user(_USER_B)
    response = client.post("/referral/redeem", json={"code": code})
    assert response.status_code == 204

    with Session(_engine) as session:
        rows = session.exec(select(ReferralAttribution)).all()
    assert len(rows) == 1
    assert rows[0].referrer_owner_id == _USER_A
    assert rows[0].referred_owner_id == _USER_B
    assert rows[0].code == code


def test_redeem_is_case_insensitive():
    code = client.get("/referral").json()["code"]  # A's code (uppercase)

    _as_user(_USER_B)
    response = client.post("/referral/redeem", json={"code": code.lower()})
    assert response.status_code == 204

    with Session(_engine) as session:
        rows = session.exec(select(ReferralAttribution)).all()
    assert len(rows) == 1
    assert rows[0].referred_owner_id == _USER_B


def test_referred_count_reflects_attributions():
    code = client.get("/referral").json()["code"]  # A's code

    for referred in ("user_c", "user_d"):
        _as_user(referred)
        assert client.post("/referral/redeem", json={"code": code}).status_code == 204

    _as_user(_USER_A)
    assert client.get("/referral").json()["referred_count"] == 2


# --- abuse guards ----------------------------------------------------------------


def test_self_referral_is_rejected_400():
    code = client.get("/referral").json()["code"]  # A's own code, still acting as A
    response = client.post("/referral/redeem", json={"code": code})
    assert response.status_code == 400

    with Session(_engine) as session:
        assert session.exec(select(ReferralAttribution)).all() == []


def test_unknown_code_is_404():
    response = client.post("/referral/redeem", json={"code": "ZZZZZZZZ"})
    assert response.status_code == 404


def test_double_redeem_by_same_referee_is_409_and_keeps_one_row():
    code = client.get("/referral").json()["code"]  # A's code

    _as_user(_USER_B)
    assert client.post("/referral/redeem", json={"code": code}).status_code == 204
    # Second attempt (even with a different valid referrer's code) must be rejected —
    # a user can be attributed at most once, ever.
    second = client.post("/referral/redeem", json={"code": code})
    assert second.status_code == 409

    with Session(_engine) as session:
        rows = session.exec(select(ReferralAttribution)).all()
    assert len(rows) == 1


def test_already_attributed_referee_cannot_switch_referrer():
    a_code = client.get("/referral").json()["code"]

    _as_user("user_other_referrer")
    other_code = client.get("/referral").json()["code"]

    _as_user(_USER_B)
    assert client.post("/referral/redeem", json={"code": a_code}).status_code == 204
    # Trying a *different* valid referrer's code afterward is still a 409, not a switch.
    assert client.post("/referral/redeem", json={"code": other_code}).status_code == 409

    with Session(_engine) as session:
        rows = session.exec(select(ReferralAttribution)).all()
    assert len(rows) == 1
    assert rows[0].referrer_owner_id == _USER_A


# --- cross-tenant scoping --------------------------------------------------------


def test_code_is_owner_scoped_each_user_gets_their_own():
    a_code = client.get("/referral").json()["code"]

    _as_user(_USER_B)
    b_code = client.get("/referral").json()["code"]

    assert a_code != b_code


def test_referred_count_is_owner_scoped():
    # A refers B. A sees 1 referral; an unrelated user C sees 0 — A's count never leaks
    # into anyone else's summary.
    code = client.get("/referral").json()["code"]
    _as_user(_USER_B)
    client.post("/referral/redeem", json={"code": code})

    _as_user("user_unrelated_c")
    assert client.get("/referral").json()["referred_count"] == 0

    _as_user(_USER_A)
    assert client.get("/referral").json()["referred_count"] == 1

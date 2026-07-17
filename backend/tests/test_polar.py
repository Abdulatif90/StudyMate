"""Tests for the Polar billing integration — checkout + webhook.

**Network-free by default**: the Polar *client* is mocked (same pattern as
test_r2_client.py / test_llm.py), so no test here talks to Polar's API.

**Signatures are NOT mocked, though.** The webhook tests sign their payloads with real
HMAC via the same Standard Webhooks library the verifier uses, and post real bytes at the
real endpoint. That's deliberate: the signature check is the only thing standing between
the public internet and a free Business plan, so a test that stubbed it out would prove
nothing. A payload is built here field-by-field to match the shape Polar actually sends
(verified against the SDK's own models — it's parsed by the real `validate_event`).
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from math import floor
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from polar_sdk.models import PolarError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from standardwebhooks.webhooks import Webhook

from app.core import polar_client
from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.modules.billing import service as billing_service
from app.modules.billing.models import Plan, UserPlan

_TEST_USER = "user_test_123"
_OTHER_USER = "someone_else"

_SECRET = "whsec_test_secret_value"
_PRO_PRODUCT = "prod_pro_id"
_BUSINESS_PRODUCT = "prod_business_id"

_NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)

#: The real lru_cache-wrapped function, captured before any test can monkeypatch the
#: attribute away — the fixture's teardown needs `.cache_clear()` to still exist even in
#: tests that replaced `polar_client.get_client` with a plain fake.
_real_get_client = polar_client.get_client


def _polar_error(message: str = "boom") -> PolarError:
    """PolarError is an HTTP error type — it requires a real response object."""
    return PolarError(message, httpx.Response(500))


def _get_test_session():
    with Session(_engine) as session:
        yield session


def _fake_settings(**overrides):
    values = {
        "polar_access_token": "polar_oat_test",
        "polar_webhook_secret": _SECRET,
        "polar_server": "sandbox",
        "polar_product_id_pro": _PRO_PRODUCT,
        "polar_product_id_business": _BUSINESS_PRODUCT,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    SQLModel.metadata.create_all(_engine)
    app.dependency_overrides[get_session] = _get_test_session
    app.dependency_overrides[get_current_user_id] = lambda: _TEST_USER
    # Both modules import get_settings into their own namespace, so both are patched.
    monkeypatch.setattr(polar_client, "get_settings", _fake_settings)
    monkeypatch.setattr(billing_service, "get_settings", _fake_settings)
    _real_get_client.cache_clear()
    yield
    del app.dependency_overrides[get_session]
    del app.dependency_overrides[get_current_user_id]
    SQLModel.metadata.drop_all(_engine)
    _real_get_client.cache_clear()


client = TestClient(app)


# --- Payload building + real signing -----------------------------------------


def _subscription_event(
    event_type: str = "subscription.active",
    *,
    external_id: str | None = _TEST_USER,
    product_id: str = _PRO_PRODUCT,
    status: str = "active",
    timestamp: datetime = _NOW,
) -> dict:
    """A Polar webhook event with the same shape the real API sends."""
    ts = timestamp.isoformat().replace("+00:00", "Z")
    customer = {
        "id": "cus_1",
        "created_at": ts,
        "modified_at": None,
        "metadata": {},
        "email_verified": True,
        "type": "individual",
        "name": "Test Customer",
        "billing_name": None,
        "billing_address": None,
        "tax_id": None,
        "organization_id": "org_1",
        "deleted_at": None,
        "avatar_url": "https://example.com/avatar.png",
        "external_id": external_id,
        "email": "test@example.com",
    }
    product = {
        "id": product_id,
        "created_at": ts,
        "modified_at": None,
        "trial_interval": None,
        "trial_interval_count": None,
        "name": "Pro",
        "description": None,
        "visibility": "public",
        "recurring_interval": "month",
        "recurring_interval_count": 1,
        "is_recurring": True,
        "is_archived": False,
        "organization_id": "org_1",
        "metadata": {},
        "prices": [],
        "benefits": [],
        "medias": [],
        "attached_custom_fields": [],
    }
    subscription = {
        "created_at": ts,
        "modified_at": None,
        "id": "sub_1",
        "amount": 2000,
        "currency": "usd",
        "recurring_interval": "month",
        "recurring_interval_count": 1,
        "status": status,
        "current_period_start": ts,
        "current_period_end": ts,
        "trial_start": None,
        "trial_end": None,
        "cancel_at_period_end": False,
        "canceled_at": None,
        "started_at": ts,
        "ends_at": None,
        "ended_at": None,
        "customer_id": "cus_1",
        "product_id": product_id,
        "discount_id": None,
        "checkout_id": None,
        "customer_cancellation_reason": None,
        "customer_cancellation_comment": None,
        "metadata": {},
        "customer": customer,
        "product": product,
        "discount": None,
        "prices": [],
        "meters": [],
        "pending_update": None,
    }
    return {"type": event_type, "timestamp": ts, "data": subscription}


def _signed_headers(body: bytes, secret: str = _SECRET, msg_id: str = "msg_1") -> dict:
    """Sign `body` exactly the way Polar does: Standard Webhooks over the raw bytes,
    with the secret base64-encoded first (what the SDK's validate_event expects)."""
    # The signed timestamp must be *now*: the verifier enforces a freshness window, so a
    # payload dated _NOW (a fixed date) would be rejected as a replay if used here.
    sent_at = datetime.now(UTC)
    webhook = Webhook(base64.b64encode(secret.encode()).decode())
    signature = webhook.sign(msg_id=msg_id, timestamp=sent_at, data=body.decode())
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": str(floor(sent_at.timestamp())),
        "webhook-signature": signature,
        "content-type": "application/json",
    }


def _post_webhook(event: dict, *, secret: str = _SECRET, msg_id: str = "msg_1"):
    body = json.dumps(event).encode()
    return client.post(
        "/billing/webhook", content=body, headers=_signed_headers(body, secret, msg_id)
    )


def _plan_row(owner_id: str) -> UserPlan | None:
    with Session(_engine) as session:
        return session.get(UserPlan, owner_id)


# --- polar_client: config + loud failures -------------------------------------


def test_get_client_raises_when_access_token_missing(monkeypatch):
    monkeypatch.setattr(
        polar_client, "get_settings", lambda: _fake_settings(polar_access_token=None)
    )
    _real_get_client.cache_clear()
    with pytest.raises(polar_client.PolarConfigError, match="POLAR_ACCESS_TOKEN"):
        polar_client.get_client()


def test_get_client_rejects_unknown_server(monkeypatch):
    monkeypatch.setattr(
        polar_client, "get_settings", lambda: _fake_settings(polar_server="staging")
    )
    _real_get_client.cache_clear()
    with pytest.raises(polar_client.PolarConfigError, match="POLAR_SERVER"):
        polar_client.get_client()


def test_get_webhook_secret_raises_when_missing(monkeypatch):
    """A missing secret must fail loudly — never fall back to accepting unsigned events."""
    monkeypatch.setattr(
        polar_client, "get_settings", lambda: _fake_settings(polar_webhook_secret=None)
    )
    with pytest.raises(polar_client.PolarConfigError, match="POLAR_WEBHOOK_SECRET"):
        polar_client.get_webhook_secret()


def test_config_errors_never_leak_the_secret_value(monkeypatch):
    """Rule 5: errors name the env var, never its value."""
    monkeypatch.setattr(
        polar_client, "get_settings", lambda: _fake_settings(polar_access_token=None)
    )
    _real_get_client.cache_clear()
    with pytest.raises(polar_client.PolarConfigError) as exc:
        polar_client.get_client()
    assert _SECRET not in str(exc.value)
    assert "polar_oat_test" not in str(exc.value)


# --- Checkout -----------------------------------------------------------------


def _fake_polar(capture: dict, *, url: str = "https://polar.sh/checkout/abc", error=None):
    def create(request):
        capture["request"] = request
        if error is not None:
            raise error
        return SimpleNamespace(url=url)

    return SimpleNamespace(checkouts=SimpleNamespace(create=create))


def test_checkout_passes_owner_id_and_product_to_polar(monkeypatch):
    """The owner-linkage crux: the Clerk owner_id must reach Polar as
    external_customer_id, or the webhook can never resolve whose plan to change."""
    capture: dict = {}
    monkeypatch.setattr(polar_client, "get_client", lambda: _fake_polar(capture))

    url = billing_service.create_checkout(_TEST_USER, Plan.PRO)

    assert url == "https://polar.sh/checkout/abc"
    request = capture["request"]
    assert request.external_customer_id == _TEST_USER
    assert request.products == [_PRO_PRODUCT]


def test_checkout_uses_the_business_product_for_business(monkeypatch):
    capture: dict = {}
    monkeypatch.setattr(polar_client, "get_client", lambda: _fake_polar(capture))
    billing_service.create_checkout(_TEST_USER, Plan.BUSINESS)
    assert capture["request"].products == [_BUSINESS_PRODUCT]


def test_checkout_forwards_success_url_when_given(monkeypatch):
    capture: dict = {}
    monkeypatch.setattr(polar_client, "get_client", lambda: _fake_polar(capture))
    billing_service.create_checkout(_TEST_USER, Plan.PRO, "https://app.example.com/done")
    assert capture["request"].success_url == "https://app.example.com/done"


def test_checkout_rejects_the_free_plan(monkeypatch):
    """Free isn't sold — it's the absence of a paid plan."""
    monkeypatch.setattr(polar_client, "get_client", lambda: _fake_polar({}))
    with pytest.raises(billing_service.PlanNotPurchasableError):
        billing_service.create_checkout(_TEST_USER, Plan.FREE)


def test_checkout_raises_config_error_when_product_id_unset(monkeypatch):
    monkeypatch.setattr(
        billing_service, "get_settings", lambda: _fake_settings(polar_product_id_pro=None)
    )
    with pytest.raises(polar_client.PolarConfigError, match="POLAR_PRODUCT_ID_PRO"):
        billing_service.create_checkout(_TEST_USER, Plan.PRO)


def test_checkout_wraps_polar_failure(monkeypatch):
    """Rule 3: an upstream failure surfaces, never a silent success."""
    monkeypatch.setattr(polar_client, "get_client", lambda: _fake_polar({}, error=_polar_error()))
    with pytest.raises(billing_service.PolarCheckoutError):
        billing_service.create_checkout(_TEST_USER, Plan.PRO)


def test_checkout_endpoint_returns_url(monkeypatch):
    capture: dict = {}
    monkeypatch.setattr(polar_client, "get_client", lambda: _fake_polar(capture))
    response = client.post("/billing/checkout", json={"plan": "pro"})
    assert response.status_code == 200
    assert response.json() == {"checkout_url": "https://polar.sh/checkout/abc"}
    # even over HTTP, the owner comes from the token — not from the request body
    assert capture["request"].external_customer_id == _TEST_USER


def test_checkout_endpoint_ignores_any_client_supplied_owner(monkeypatch):
    """A caller must not be able to buy a plan for someone else."""
    capture: dict = {}
    monkeypatch.setattr(polar_client, "get_client", lambda: _fake_polar(capture))
    response = client.post("/billing/checkout", json={"plan": "pro", "owner_id": _OTHER_USER})
    assert response.status_code == 200
    assert capture["request"].external_customer_id == _TEST_USER


def test_checkout_endpoint_rejects_free_with_400(monkeypatch):
    monkeypatch.setattr(polar_client, "get_client", lambda: _fake_polar({}))
    assert client.post("/billing/checkout", json={"plan": "free"}).status_code == 400


def test_checkout_endpoint_maps_polar_failure_to_502(monkeypatch):
    monkeypatch.setattr(
        polar_client, "get_client", lambda: _fake_polar({}, error=_polar_error("down"))
    )
    assert client.post("/billing/checkout", json={"plan": "pro"}).status_code == 502


# --- Webhook: signature verification (the security crux) ----------------------


def test_valid_signature_upserts_the_plan():
    response = _post_webhook(_subscription_event())
    assert response.status_code == 200
    assert response.json() == {"status": "applied"}
    row = _plan_row(_TEST_USER)
    assert row is not None
    assert row.plan is Plan.PRO


def test_invalid_signature_is_rejected_and_writes_nothing():
    """Anyone can POST here. A wrong secret must not move a plan."""
    response = _post_webhook(_subscription_event(), secret="whsec_attacker_guess")
    assert response.status_code == 403
    assert _plan_row(_TEST_USER) is None


def test_unsigned_request_is_rejected_and_writes_nothing():
    body = json.dumps(_subscription_event()).encode()
    response = client.post("/billing/webhook", content=body)
    assert response.status_code == 403
    assert _plan_row(_TEST_USER) is None


def test_tampered_body_is_rejected():
    """The signature covers the exact bytes: swapping the product after signing must fail."""
    event = _subscription_event()
    body = json.dumps(event).encode()
    headers = _signed_headers(body)
    event["data"]["product_id"] = _BUSINESS_PRODUCT
    tampered = json.dumps(event).encode()

    response = client.post("/billing/webhook", content=tampered, headers=headers)
    assert response.status_code == 403
    assert _plan_row(_TEST_USER) is None


def test_missing_secret_fails_loudly_and_writes_nothing(monkeypatch):
    monkeypatch.setattr(
        polar_client, "get_settings", lambda: _fake_settings(polar_webhook_secret=None)
    )
    response = _post_webhook(_subscription_event())
    assert response.status_code == 500
    assert _plan_row(_TEST_USER) is None


# --- Webhook: grant / revoke semantics ---------------------------------------


def test_business_subscription_grants_business():
    _post_webhook(_subscription_event(product_id=_BUSINESS_PRODUCT))
    assert _plan_row(_TEST_USER).plan is Plan.BUSINESS


def test_trialing_subscription_still_grants_the_plan():
    _post_webhook(_subscription_event(status="trialing"))
    assert _plan_row(_TEST_USER).plan is Plan.PRO


def test_revoked_downgrades_to_free():
    _post_webhook(_subscription_event(timestamp=_NOW))
    assert _plan_row(_TEST_USER).plan is Plan.PRO

    response = _post_webhook(
        _subscription_event(
            "subscription.revoked", status="canceled", timestamp=_NOW + timedelta(hours=1)
        ),
        msg_id="msg_2",
    )
    assert response.json() == {"status": "applied"}
    assert _plan_row(_TEST_USER).plan is Plan.FREE


def test_revoked_keeps_the_row_rather_than_deleting_it():
    """Downgrade must preserve updated_at — it's the ordering guard that stops a stale
    `active` redelivery from silently re-granting a paid plan."""
    _post_webhook(_subscription_event(timestamp=_NOW))
    _post_webhook(
        _subscription_event("subscription.revoked", timestamp=_NOW + timedelta(hours=1)),
        msg_id="msg_2",
    )
    row = _plan_row(_TEST_USER)
    assert row is not None
    assert row.plan is Plan.FREE


def test_canceled_does_not_downgrade():
    """`subscription.canceled` means "cancellation scheduled" — the customer keeps access
    until the period they paid for ends. Downgrading here would cut off a paying user.
    Loss of access arrives separately, as subscription.revoked."""
    _post_webhook(_subscription_event(timestamp=_NOW))
    response = _post_webhook(
        _subscription_event(
            "subscription.canceled", status="active", timestamp=_NOW + timedelta(hours=1)
        ),
        msg_id="msg_2",
    )
    assert response.json() == {"status": "ignored"}
    assert _plan_row(_TEST_USER).plan is Plan.PRO


def test_past_due_does_not_downgrade():
    """Payment may still recover; revoked fires if it doesn't."""
    _post_webhook(_subscription_event(timestamp=_NOW))
    _post_webhook(
        _subscription_event(
            "subscription.updated", status="past_due", timestamp=_NOW + timedelta(hours=1)
        ),
        msg_id="msg_2",
    )
    assert _plan_row(_TEST_USER).plan is Plan.PRO


def test_updated_event_applies_a_tier_switch():
    """Pro -> Business mid-period fires `updated`, not `active`."""
    _post_webhook(_subscription_event(timestamp=_NOW))
    assert _plan_row(_TEST_USER).plan is Plan.PRO

    _post_webhook(
        _subscription_event(
            "subscription.updated",
            product_id=_BUSINESS_PRODUCT,
            timestamp=_NOW + timedelta(hours=1),
        ),
        msg_id="msg_2",
    )
    assert _plan_row(_TEST_USER).plan is Plan.BUSINESS


def test_unknown_product_grants_nothing():
    """Never guess a plan for a product we don't sell."""
    response = _post_webhook(_subscription_event(product_id="prod_something_else"))
    assert response.json() == {"status": "ignored"}
    assert _plan_row(_TEST_USER) is None


def test_event_without_external_id_is_ignored():
    """A subscription created outside our checkout has no owner link — it must not
    guess, and must not error (Polar would retry an event that can never succeed)."""
    response = _post_webhook(_subscription_event(external_id=None))
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert _plan_row(_TEST_USER) is None


def test_unhandled_event_type_is_ignored():
    response = _post_webhook(_subscription_event("subscription.created"))
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


# --- Webhook: idempotency + ordering ------------------------------------------


def test_duplicate_delivery_is_idempotent():
    """Polar retries. The same event twice must not double-apply or error."""
    first = _post_webhook(_subscription_event(timestamp=_NOW))
    second = _post_webhook(_subscription_event(timestamp=_NOW), msg_id="msg_2")

    assert first.json() == {"status": "applied"}
    assert second.json() == {"status": "ignored_stale"}
    assert _plan_row(_TEST_USER).plan is Plan.PRO


def test_stale_revoked_cannot_overwrite_a_newer_active():
    """Out-of-order delivery: an OLD revoke arriving after a NEW subscribe must not
    downgrade a customer who is currently paying."""
    _post_webhook(_subscription_event(timestamp=_NOW))

    response = _post_webhook(
        _subscription_event("subscription.revoked", timestamp=_NOW - timedelta(hours=1)),
        msg_id="msg_2",
    )
    assert response.json() == {"status": "ignored_stale"}
    assert _plan_row(_TEST_USER).plan is Plan.PRO


def test_stale_active_cannot_resurrect_a_revoked_plan():
    """The mirror case, and the reason revoke keeps the row: a stale `active` arriving
    after a revoke must not silently hand back a paid plan for free."""
    _post_webhook(_subscription_event(timestamp=_NOW))
    _post_webhook(
        _subscription_event("subscription.revoked", timestamp=_NOW + timedelta(hours=2)),
        msg_id="msg_2",
    )
    assert _plan_row(_TEST_USER).plan is Plan.FREE

    response = _post_webhook(
        _subscription_event(timestamp=_NOW + timedelta(hours=1)), msg_id="msg_3"
    )
    assert response.json() == {"status": "ignored_stale"}
    assert _plan_row(_TEST_USER).plan is Plan.FREE


# --- Webhook: tenant scoping --------------------------------------------------


def test_webhook_touches_only_the_named_owner():
    """Rule 2: the webhook writes exactly one owner's row and can never reach another's."""
    with Session(_engine) as session:
        session.add(UserPlan(owner_id=_OTHER_USER, plan=Plan.BUSINESS, updated_at=_NOW))
        session.commit()

    _post_webhook(_subscription_event(external_id=_TEST_USER, timestamp=_NOW))

    assert _plan_row(_TEST_USER).plan is Plan.PRO
    # the bystander is untouched
    assert _plan_row(_OTHER_USER).plan is Plan.BUSINESS


def test_revoke_for_one_owner_leaves_another_subscribed():
    with Session(_engine) as session:
        session.add(UserPlan(owner_id=_OTHER_USER, plan=Plan.PRO, updated_at=_NOW))
        session.commit()

    _post_webhook(
        _subscription_event("subscription.revoked", external_id=_TEST_USER, timestamp=_NOW)
    )

    assert _plan_row(_TEST_USER).plan is Plan.FREE
    assert _plan_row(_OTHER_USER).plan is Plan.PRO


# --- The whole point: a webhook actually lifts the caps -----------------------


def test_subscribing_lifts_the_subject_cap_immediately():
    """End-to-end over HTTP: exhaust the Free cap, deliver a real signed webhook, and the
    request that just 402'd succeeds — with nothing but the webhook in between."""
    for i in range(3):  # Free cap is 3 subjects
        assert client.post("/subjects", json={"name": f"Subject {i}"}).status_code == 201

    blocked = client.post("/subjects", json={"name": "Fourth"})
    assert blocked.status_code == 402
    assert blocked.json()["plan"] == "free"

    assert _post_webhook(_subscription_event()).json() == {"status": "applied"}

    assert client.post("/subjects", json={"name": "Fourth"}).status_code == 201


def test_revoking_reinstates_the_free_cap():
    _post_webhook(_subscription_event(timestamp=_NOW))
    for i in range(4):  # comfortably past the Free cap of 3
        assert client.post("/subjects", json={"name": f"Subject {i}"}).status_code == 201

    _post_webhook(
        _subscription_event("subscription.revoked", timestamp=_NOW + timedelta(hours=1)),
        msg_id="msg_2",
    )

    blocked = client.post("/subjects", json={"name": "One too many"})
    assert blocked.status_code == 402
    assert blocked.json()["plan"] == "free"


def test_plan_endpoint_reflects_a_webhook_upgrade():
    assert client.get("/billing/plan").json()["plan"] == "free"
    _post_webhook(_subscription_event())
    body = client.get("/billing/plan").json()
    assert body["plan"] == "pro"
    assert body["limits"]["max_subjects"] == 50


# --- Live (opt-in): real sandbox API ------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(
    not get_settings().polar_access_token,
    reason="POLAR_ACCESS_TOKEN not configured",
)
def test_live_checkout_against_real_sandbox(monkeypatch):
    """Creates a REAL checkout in the Polar sandbox with a throwaway owner id, then reads
    it back from the real API to prove the owner linkage actually persisted upstream —
    the thing the webhook later depends on to know whose plan to change.

    Throwaway owner id, so no real account's data is involved.
    """
    monkeypatch.undo()  # use the real settings/.env, not the fakes above
    _real_get_client.cache_clear()

    throwaway_owner = f"live_test_owner_{uuid.uuid4()}"
    url = billing_service.create_checkout(throwaway_owner, Plan.PRO)
    assert url.startswith("https://")

    # Find the checkout we just created and confirm Polar really stored our owner id on
    # it. Matched by URL, not by `list(external_customer_id=...)`: that filter resolves
    # through the *customer* relation, and an unpaid checkout has no customer yet
    # (customer_id is None until payment), so it would find nothing here. Verified
    # against the real sandbox API.
    listed = polar_client.get_client().checkouts.list()
    mine = [c for c in listed.result.items if c.url == url]
    assert len(mine) == 1, "the checkout we just created should be listed"
    assert mine[0].external_customer_id == throwaway_owner
    assert mine[0].product_id == get_settings().polar_product_id_pro
    _real_get_client.cache_clear()

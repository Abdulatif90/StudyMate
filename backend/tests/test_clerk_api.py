"""Clerk Backend API client tests — offline, network-free.

`clerk_api` is the one place the backend calls Clerk's REST API. We never hit real Clerk
here (same discipline as the rest of the suite): the missing-key gate is proven by
overriding settings to have NO key (it must raise BEFORE any network), and pagination /
user-id extraction are proven against a fake transport so no real request leaves the box.
"""

from __future__ import annotations

import httpx
import pytest

from app.core import clerk_api


class _FakeSettings:
    def __init__(self, clerk_secret_key):
        self.clerk_secret_key = clerk_secret_key


def test_missing_key_raises_config_error_before_any_network(monkeypatch):
    # No key configured → ClerkConfigError, and crucially it raises before httpx is touched
    # (if it tried the network this offline test would hang/fail, not raise cleanly).
    monkeypatch.setattr(clerk_api, "get_settings", lambda: _FakeSettings(None))

    def _no_network(*args, **kwargs):
        raise AssertionError("no network call may happen when the key is missing")

    monkeypatch.setattr(httpx, "Client", _no_network)
    with pytest.raises(clerk_api.ClerkConfigError):
        clerk_api.list_organization_member_ids("org_whatever")


def _mock_transport(pages: list[dict]) -> httpx.MockTransport:
    """A transport that serves the given response bodies in order, one per request."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        # Assert the verified contract is honored on the wire.
        assert request.url.path == "/v1/organizations/org_x/memberships"
        assert request.headers["Authorization"] == "Bearer sk_test_fake"
        body = pages[calls["n"]]
        calls["n"] += 1
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def _patch(monkeypatch, transport: httpx.MockTransport) -> None:
    monkeypatch.setattr(clerk_api, "get_settings", lambda: _FakeSettings("sk_test_fake"))
    real_client = httpx.Client

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _client)


def test_extracts_user_ids_single_page(monkeypatch):
    body = {
        "data": [
            {"public_user_data": {"user_id": "user_A"}},
            {"public_user_data": {"user_id": "user_B"}},
        ],
        "total_count": 2,
    }
    _patch(monkeypatch, _mock_transport([body]))
    assert clerk_api.list_organization_member_ids("org_x") == ["user_A", "user_B"]


def test_follows_pagination_across_pages(monkeypatch):
    # total_count 3 across two pages → the client must request the second page and stop.
    page1 = {
        "data": [
            {"public_user_data": {"user_id": "user_A"}},
            {"public_user_data": {"user_id": "user_B"}},
        ],
        "total_count": 3,
    }
    page2 = {"data": [{"public_user_data": {"user_id": "user_C"}}], "total_count": 3}
    _patch(monkeypatch, _mock_transport([page1, page2]))
    assert clerk_api.list_organization_member_ids("org_x") == ["user_A", "user_B", "user_C"]


def test_non_200_raises_api_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"errors": []})

    _patch(monkeypatch, httpx.MockTransport(handler))
    with pytest.raises(clerk_api.ClerkAPIError):
        clerk_api.list_organization_member_ids("org_x")

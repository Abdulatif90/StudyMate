"""Tests for app.core.auth — Clerk JWT verification against a local RSA key.

No network calls: we generate a throwaway RSA keypair, sign a token
ourselves, and hand `decode_clerk_token` a fake JWKS client, so this never
needs Clerk's real JWKS endpoint.
"""

from types import SimpleNamespace
from unittest.mock import create_autospec

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import PyJWKClient

from app.core import auth

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_ISSUER = "https://test.clerk.accounts.dev"


def _make_token(**claims) -> str:
    return jwt.encode(claims, _private_key, algorithm="RS256", headers={"kid": "test-key"})


def _make_fake_jwks_client():
    """A fake spec'd against the real PyJWKClient class.

    `create_autospec` raises AttributeError on any method name that isn't
    actually on `PyJWKClient` — so if `decode_clerk_token` ever calls a
    method that doesn't exist on the real client, this test fails instead
    of silently passing against a fake that drifted from reality (as
    happened when this test used a hand-rolled `get_signing_key_from_kid`,
    a method PyJWT never had — see docs/WORKLOG.md).
    """
    fake = create_autospec(PyJWKClient, instance=True)
    fake.get_signing_key.return_value = SimpleNamespace(key=_public_key)
    return fake


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(clerk_issuer=_ISSUER))


def test_decode_clerk_token_returns_claims_for_valid_token():
    token = _make_token(sub="user_123", iss=_ISSUER)
    claims = auth.decode_clerk_token(token, _make_fake_jwks_client())
    assert claims["sub"] == "user_123"


def test_decode_clerk_token_rejects_wrong_issuer():
    token = _make_token(sub="user_123", iss="https://someone-else.clerk.accounts.dev")
    with pytest.raises(jwt.InvalidIssuerError):
        auth.decode_clerk_token(token, _make_fake_jwks_client())


def test_get_current_user_id_returns_sub_for_valid_token():
    token = _make_token(sub="user_123", iss=_ISSUER)
    credentials = SimpleNamespace(credentials=token)
    jwks_client = _make_fake_jwks_client()
    user_id = auth.get_current_user_id(credentials=credentials, jwks_client=jwks_client)
    assert user_id == "user_123"


def test_get_current_user_id_rejects_missing_credentials():
    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user_id(credentials=None, jwks_client=_make_fake_jwks_client())
    assert exc_info.value.status_code == 401


def test_get_current_user_id_rejects_invalid_token():
    token = _make_token(sub="user_123", iss="https://wrong-issuer")
    credentials = SimpleNamespace(credentials=token)
    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user_id(credentials=credentials, jwks_client=_make_fake_jwks_client())
    assert exc_info.value.status_code == 401


# --- Organization context (Phase 5 foundation, Clerk Organizations) ------------
# Same local-RSA-keypair pattern as above: we mint Clerk-shaped tokens WITH and
# WITHOUT org claims and assert the org-context dependency extracts them. No network,
# no live Clerk. Covers both session-token claim shapes Clerk can emit (flat v1 and
# nested v2) plus the pure role helpers.

from app.core.org import (  # noqa: E402  (grouped with the org tests, not module top)
    OrgContext,
    extract_org_context,
    is_teacher_role,
    org_capability,
)


def test_extract_org_context_reads_flat_v1_claims():
    ctx = extract_org_context({"sub": "user_1", "org_id": "org_abc", "org_role": "org:admin"})
    assert ctx == OrgContext(org_id="org_abc", org_role="org:admin")


def test_extract_org_context_reads_nested_v2_claims():
    # v2 session token: org info under the nested `o` object (o.id / o.rol).
    ctx = extract_org_context(
        {"sub": "user_1", "v": 2, "o": {"id": "org_xyz", "rol": "org:member"}}
    )
    assert ctx == OrgContext(org_id="org_xyz", org_role="org:member")


def test_extract_org_context_none_when_no_active_org():
    # Personal workspace / Organizations not enabled: no org claims at all.
    ctx = extract_org_context({"sub": "user_1", "iss": _ISSUER})
    assert ctx == OrgContext(org_id=None, org_role=None)


def test_get_org_context_returns_org_for_token_with_org_claims():
    token = _make_token(sub="user_1", iss=_ISSUER, org_id="org_abc", org_role="org:admin")
    credentials = SimpleNamespace(credentials=token)
    ctx = auth.get_org_context(credentials=credentials, jwks_client=_make_fake_jwks_client())
    assert ctx == OrgContext(org_id="org_abc", org_role="org:admin")


def test_get_org_context_returns_none_for_token_without_org_claims():
    token = _make_token(sub="user_1", iss=_ISSUER)
    credentials = SimpleNamespace(credentials=token)
    ctx = auth.get_org_context(credentials=credentials, jwks_client=_make_fake_jwks_client())
    assert ctx == OrgContext(org_id=None, org_role=None)


def test_get_org_context_rejects_missing_credentials():
    with pytest.raises(HTTPException) as exc_info:
        auth.get_org_context(credentials=None, jwks_client=_make_fake_jwks_client())
    assert exc_info.value.status_code == 401


def test_get_org_context_rejects_invalid_token():
    token = _make_token(sub="user_1", iss="https://wrong-issuer")
    credentials = SimpleNamespace(credentials=token)
    with pytest.raises(HTTPException) as exc_info:
        auth.get_org_context(credentials=credentials, jwks_client=_make_fake_jwks_client())
    assert exc_info.value.status_code == 401


def test_role_helpers_map_admin_to_teacher_and_member_to_student():
    assert is_teacher_role("org:admin") is True
    assert is_teacher_role("org:member") is False
    assert is_teacher_role(None) is False
    assert org_capability("org:admin") == "teacher"
    assert org_capability("org:member") == "student"
    assert org_capability(None) == "student"


def test_require_teacher_allows_teacher_role():
    org = OrgContext(org_id="org_abc", org_role="org:admin")
    assert auth.require_teacher(org=org) is org


def test_require_teacher_rejects_student_role():
    org = OrgContext(org_id="org_abc", org_role="org:member")
    with pytest.raises(HTTPException) as exc_info:
        auth.require_teacher(org=org)
    assert exc_info.value.status_code == 403


def test_require_teacher_rejects_no_active_org():
    with pytest.raises(HTTPException) as exc_info:
        auth.require_teacher(org=OrgContext(org_id=None, org_role=None))
    assert exc_info.value.status_code == 403
